#!/bin/sh
#
# The API container's startup sequence. Refuse, migrate, serve -- in that order,
# and the order is the whole point.
#
# `check --deploy --fail-level WARNING` is a gate rather than a log line. Every
# Django deploy warning becomes a non-zero exit, the container never starts, and
# Container Apps holds the previous revision serving traffic while the new one
# fails health checks. That is the correct outcome for the class of fault these
# warnings describe: each one is a misconfiguration that a running application
# does not report. `DJANGO_BEHIND_PROXY` unset is the example that prompted
# this -- it takes members' money and activates no membership, and every page
# and every log looks healthy while it does (design/conflict.md C31).
#
# **The check needs a reachable database, which is not obvious and is not
# Django's usual behaviour.** On MySQL, working out a UUIDField's column type
# calls `has_native_uuid_field`, which asks the server whether it is MariaDB,
# which opens a connection. Every primary key in this project is a UUID, so
# `manage.py check` connects on this backend where on SQLite it would not. The
# wait below therefore comes first: without it, a container starting a few
# seconds before its database is reachable fails the gate for a reason that has
# nothing to do with configuration.
#
# `set -e` is what makes any of this a gate. Without it the script would run on
# to uvicorn after a failed check and serve the misconfiguration it caught.
set -eu

wait_for_database() {
    # Bounded, and the bound matters: an unreachable database has to end as a
    # failed revision rather than a container that retries forever and reports
    # nothing. Azure MySQL is reachable in seconds from inside the same region;
    # a minute is generous and still fails visibly.
    attempts=30
    while [ "$attempts" -gt 0 ]; do
        if python -c "
import django
django.setup()
from django.db import connection
connection.ensure_connection()
" >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 2
    done

    echo "entrypoint: the database was not reachable after 60 seconds." >&2
    echo "entrypoint: check DJANGO_DB_HOST, the MySQL firewall rules, and" >&2
    echo "entrypoint: whether DJANGO_DB_SSL_CA points at a bundle in the image." >&2
    return 1
}

start_worker() {
    echo "entrypoint: starting the celery worker for the scheduled queue"
    # `-Q scheduled`, and **the queue name is not optional**. Without it
    # this worker consumes the default queue only, which since sends moved
    # onto the broker is `scheduled` by configuration -- so it would still
    # work, and would keep working right up until somebody changed
    # CELERY_TASK_DEFAULT_QUEUE. Naming it here means this process and the
    # `mail-worker` below each say which half of the broker they are for,
    # and neither can quietly start eating the other's work.
    #
    # `--concurrency 1`, deliberately. There are three tasks a day, each a long
    # database pass, and the schedule staggers them so they never overlap. A
    # second process would hold a second set of database connections open all
    # day for work that never arrives -- and it would allow two purges at once,
    # which is the one arrangement the schedule was written to avoid.
    #
    # `--without-gossip --without-mingle` because there is one worker per
    # queue. Both exist so that workers can discover each other; with
    # single nodes they are chatter on the broker and a slower start-up.
    # Drop them if a second replica of either is ever added.
    exec celery -A f2c worker \
        --queues scheduled \
        --loglevel "${CELERY_LOG_LEVEL:-info}" \
        --concurrency 1 \
        --without-gossip \
        --without-mingle
}

start_mail_worker() {
    echo "entrypoint: starting the celery worker for the mail queue"
    # **A separate process from the one above, and the reason is a login
    # outage.** Both workers run one task at a time; the purges are long
    # delete passes with a twenty-five-minute ceiling that run at 01:00 and
    # 01:20. On a shared queue a sign-in code requested at 01:05 waits
    # behind them, and that is not a slow email -- it is a member who
    # cannot get in, on the one sign-in path that works for an account with
    # no passkey yet.
    #
    # `--concurrency ${CELERY_MAIL_CONCURRENCY:-4}`. Unlike the scheduled
    # queue this one has genuine bursts -- a batch of suspensions out of the
    # admin -- and its work is a blocking socket read rather than a database
    # pass, so one process waiting out a mail server should not be stopping
    # three others from sending. Four is a starting point sized against one
    # provider and one small club; the variable is there so it can be
    # raised without a code change when the send volume says so.
    exec celery -A f2c worker \
        --queues mail \
        --loglevel "${CELERY_LOG_LEVEL:-info}" \
        --concurrency "${CELERY_MAIL_CONCURRENCY:-4}" \
        --without-gossip \
        --without-mingle
}

start_beat() {
    echo "entrypoint: starting celery beat"
    # The schedule file holds the last-run time for each entry, so a restart
    # does not re-fire a job that already ran this period. Under /tmp because
    # that is the writable path a Container Apps replica can count on, and
    # because losing it costs at most one duplicate run of an idempotent job --
    # a smaller price than a volume to administer.
    exec celery -A f2c beat \
        --loglevel "${CELERY_LOG_LEVEL:-info}" \
        --schedule /tmp/celerybeat-schedule
}

case "${1:-serve}" in
    serve)
        wait_for_database

        # The gate. Anything Django or this project considers wrong about a
        # deployed configuration stops the container here.
        echo "entrypoint: running deployment checks"
        python manage.py check --deploy --fail-level WARNING

        # Migrations run here rather than in a separate job because this
        # deployment has one API container and Container Apps starts a new
        # revision before retiring the old one. That is a real constraint on
        # what may go in a migration -- a schema change has to be readable by
        # the revision still serving traffic -- and it is the trade taken
        # knowingly: a separate migration job is a second deployment artefact
        # and a second thing to forget. Revisit it when there is more than one
        # replica starting at once.
        echo "entrypoint: applying migrations"
        python manage.py migrate --noinput

        echo "entrypoint: starting uvicorn"
        # One worker per replica: Container Apps scales by adding replicas, and
        # a second worker inside one replica would only split the throttle
        # counters again -- the fault Block 0 P3 exists to fix.
        # **No `--proxy-headers`, deliberately.** It looks like the obvious
        # flag for a container behind ingress, and it would quietly break two
        # things. uvicorn would rewrite the client address from X-Forwarded-For
        # before Django ever saw it, so REMOTE_ADDR would already be the
        # caller's -- which means `notification_source_ip` would return the
        # right answer with DJANGO_BEHIND_PROXY unset, `payments.W001` would
        # warn about a deployment that worked, and the header would be trusted
        # by a component with no opinion on whether the edge overwrites it.
        # One place in this application interprets X-Forwarded-For, it is
        # opt-in, and it is tested. The scheme is a separate matter and
        # SECURE_PROXY_SSL_HEADER handles it.
        exec uvicorn f2c.asgi:application \
            --host 0.0.0.0 \
            --port "${PORT:-8000}" \
            --workers 1
        ;;

    worker)
        # The Celery worker for the `scheduled` queue. Three scheduled jobs
        # run through it -- see CELERY_BEAT_SCHEDULE in `f2c/settings.py` --
        # and the first of them, `lapse_memberships`, is what withdraws
        # access from a membership that has stopped paying.
        #
        # **Email does not run here.** It has its own queue and its own
        # container: `mail-worker` below.
        #
        # **The gate runs here too, and that is the reason the worker is in this
        # script** rather than given its own command line in the platform's
        # configuration. This process reads the same settings the API reads and
        # is wrong in the same ways, so it has to refuse to start for the same
        # reasons -- and it is the process that changes member access with
        # nobody watching, which makes booting on a misconfiguration worse here
        # than anywhere else.
        #
        # **No migrations.** The API container applies them; a worker that also
        # ran `migrate` would be a second process racing the first through the
        # same schema change on every deployment.
        wait_for_database
        echo "entrypoint: running deployment checks"
        python manage.py check --deploy --fail-level WARNING
        start_worker
        ;;

    mail-worker)
        # The Celery worker for the `mail` queue, which is every email this
        # platform sends. **This container is on the sign-in path**: with it
        # down, `EmailDispatch` rows pile up on `queued`, no code is
        # delivered, and no member without a passkey can get in. Nothing
        # else in the stack will report that -- the API answers normally,
        # because answering normally is what moving the send off the request
        # path bought. `EmailDispatch.objects.pending()` is the query that
        # shows it, and it is the one worth alerting on.
        #
        # The gate and the no-migrations rule are the `worker` case's, for
        # the same two reasons.
        wait_for_database
        echo "entrypoint: running deployment checks"
        python manage.py check --deploy --fail-level WARNING
        start_mail_worker
        ;;

    beat)
        # The scheduler, and **it must be a singleton.** Beat publishes on a
        # timer with no coordination between instances, so two of these means
        # every job published twice -- two lapse runs against the same
        # subscriptions, two purges deleting the same rows. Nothing is corrupted,
        # because all three tasks are idempotent, but each duplicate writes its
        # own `ScheduledRun` row and the history stops being readable. Whatever
        # runs this must be capped at one replica.
        #
        # It holds no database connection of its own in normal operation -- it
        # publishes task names to Redis and nothing else -- but the gate below
        # needs one, for the reason given at the top of this file.
        wait_for_database
        echo "entrypoint: running deployment checks"
        python manage.py check --deploy --fail-level WARNING
        start_beat
        ;;

    dev-worker)
        # The worker for the compose stack, and the same trade the `dev` case
        # below makes for the API: the gate cannot pass with DJANGO_DEBUG on, so
        # this branch does not run it. Nothing ships this -- the image's CMD is
        # `serve`, and only compose.yaml asks for `dev-worker`.
        wait_for_database
        start_worker
        ;;

    dev-mail-worker)
        # The mail worker for the compose stack. Same reason as
        # `dev-worker`, and it is the one the local sign-in needs running:
        # with the compose Redis up, sends are published rather than eager.
        wait_for_database
        start_mail_worker
        ;;

    dev-beat)
        # Beat for the compose stack. Same reason as `dev-worker`.
        wait_for_database
        start_beat
        ;;

    check)
        # The gate on its own, for a pipeline that wants to fail a deployment
        # before it reaches the platform.
        wait_for_database
        exec python manage.py check --deploy --fail-level WARNING
        ;;

    dev)
        # The local stack in compose.yaml, and nothing else. It exists because
        # the gate above cannot pass here, and the alternative was to weaken it.
        #
        # `check --deploy --fail-level WARNING` fails on DJANGO_DEBUG=1:
        # security.W018 says DEBUG must not be on in a deployment, and it is
        # right. But a local stack with DEBUG off is worse than useless -- over
        # plain HTTP, SESSION_COOKIE_SECURE and CSRF_COOKIE_SECURE are both on,
        # so no cookie is ever stored and nobody can sign in. The choice is
        # therefore between a gate that does not run and a stack nobody can log
        # into, and this is the one that does not run the gate. Nothing here
        # ships: the image's CMD is still `serve`, and only compose.yaml asks
        # for `dev`.
        #
        # `runserver` rather than uvicorn. This used to be forced:
        # `django.contrib.staticfiles` serves /static/ under DEBUG by
        # overriding the runserver command rather than by adding a URL, so
        # uvicorn rendered the admin with no stylesheets at all. WhiteNoise now
        # serves /static/ in every process, runserver included -- see
        # MIDDLEWARE and `whitenoise.runserver_nostatic` in f2c/settings.py --
        # so the choice is only the usual local one: autoreload. Media is a
        # real urlpattern and works either way. Anything touching async views,
        # streaming or long-lived connections still needs uvicorn -- see README
        # "Running" -- and is not what this container is for.
        wait_for_database

        # WhiteNoise needs STATIC_ROOT populated, and the image's own
        # `collectstatic` does not reach here: compose.yaml mounts a named
        # volume over /app/staticfiles, which keeps whatever the last run left
        # there. Cheap, and it keeps the local admin styled after an edit to
        # static/cc_admin/.
        echo "entrypoint: collecting static files"
        python manage.py collectstatic --noinput

        echo "entrypoint: applying migrations"
        python manage.py migrate --noinput

        echo "entrypoint: starting the development server"
        exec python manage.py runserver "0.0.0.0:${PORT:-8000}"
        ;;

    *)
        # Anything else is a management command, which is how any one-off
        # maintenance runs: `... lapse_memberships`, `... purge_email_dispatches
        # --dry-run`. This used to be described as the Function App's fallback;
        # there is no Function App, the schedule is Celery beat above, and these
        # are the same three jobs by hand.
        exec python manage.py "$@"
        ;;
esac

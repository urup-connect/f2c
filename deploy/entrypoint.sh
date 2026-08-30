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

    check)
        # The gate on its own, for a pipeline that wants to fail a deployment
        # before it reaches the platform.
        wait_for_database
        exec python manage.py check --deploy --fail-level WARNING
        ;;

    *)
        # Anything else is a management command, which is how the Function App's
        # fallback and any one-off maintenance run: `... lapse_memberships`.
        exec python manage.py "$@"
        ;;
esac

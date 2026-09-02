"""The two things this app hands to a worker: sending an email, and forgetting one.

Unrelated jobs on the same table, sitting here together because this app owns
both. Everything else about them differs -- which queue they run on, what a
failure means, whether a person scheduled them -- so they are described apart.

``deliver_email`` -- **the send half of every email this platform sends.**
    Event-driven, on the ``mail`` queue, and the busy one: one task per message,
    published by ``mail.send_storefront_email`` the moment the row it reads has
    committed. ``mail`` carries the argument for why a send happens here at all
    rather than in the request that composed it -- in short, a mail server is
    not ours, and a ten-second SMTP timeout was sitting inside the sign-in path.

    It writes no ``ScheduledRun``, and that is deliberate. ``ScheduledRun`` is
    the record of a *timed* job, sized for three rows a day, and every fact it
    would hold about a send -- when it started, how it ended, what it touched --
    is already on the ``EmailDispatch`` row, per message, with the member's name
    beside it. A second audit trail could only ever disagree with the first.

``purge_email_dispatch_records`` -- **the retention half.**
    Scheduled, nightly, on the ``scheduled`` queue. **A retention policy nobody
    runs is a retention policy nobody has**, and this is what runs it:
    ``EMAIL_DISPATCH_RETENTION_DAYS`` is a number in a settings file until
    something deletes by it. ``retention.py`` carries the POPIA argument and
    does the work; this schedules it and records that it ran, which is the
    evidence the policy needs in order to be a policy.

    No ``days`` argument and no ``dry_run``. Both exist on the management
    command, where a person is deciding something; a nightly job that could be
    scheduled with a different window than the deployment configured is a second
    place for the retention period to live.

**Two queues, and the reason is a login outage.** One worker runs one task at a
time -- ``CELERY_WORKER_PREFETCH_MULTIPLIER`` is 1 and the concurrency is 1 --
and the purges are long delete passes bounded at twenty-five minutes. Sharing a
queue would mean a sign-in code published at 01:05 waiting behind the night's
housekeeping, which is a member who cannot sign in. ``CELERY_TASK_ROUTES`` in
``settings.py`` splits them, and the deployment runs a worker for each.

**Task names are written out rather than derived.** Celery's default would be
the import path, and this project has already moved every app once, under
``core``/``commerce``/``club`` in Block 0.5. A name that followed the package
path would make the next such move rename a queue key, a route, a beat schedule
entry and every historical row in ``ScheduledRun``. The explicit label is the
same decision, and the same reason, as ``AppConfig.label``.
"""
import logging

from celery import shared_task
from django.conf import settings

from app.core.scheduling.models import ScheduledTask
from app.core.scheduling.runs import record

from .mail import deliver, transient
from .models import EmailDispatch
from .retention import purge_email_dispatches

__all__ = ['deliver_email', 'purge_email_dispatch_records']

logger = logging.getLogger(__name__)

#: The send task's name, written out. See the module docstring. Named here
#: rather than inline because ``CELERY_TASK_ROUTES`` has to route it and a
#: route keyed on a string that does not match a registered task fails by
#: silently sending the task to the default queue.
DELIVER_EMAIL = 'storefronts.deliver_email'

#: How many times a transport failure is tried again before the row is failed
#: for good, and how the wait between attempts grows. Defaults rather than bare
#: constants so a deployment can flatten them, and so a test can switch retries
#: off without patching Celery.
DEFAULT_MAX_RETRIES = 5
DEFAULT_BACKOFF_SECONDS = 30
DEFAULT_BACKOFF_CEILING_SECONDS = 600


def _retry_policy():
    """``(max_retries, base, ceiling)``, from settings.

    Read per call rather than captured at import, because the decorator's own
    ``max_retries`` is fixed at registration and this has to be overridable: a
    suite that exercised the real five attempts against a backend which always
    refuses would run every failure path six times for no extra assurance.
    """
    return (
        getattr(settings, 'EMAIL_SEND_MAX_RETRIES', DEFAULT_MAX_RETRIES),
        getattr(
            settings, 'EMAIL_SEND_BACKOFF_SECONDS', DEFAULT_BACKOFF_SECONDS
        ),
        getattr(
            settings,
            'EMAIL_SEND_BACKOFF_CEILING_SECONDS',
            DEFAULT_BACKOFF_CEILING_SECONDS,
        ),
    )


def _countdown(retries, base, ceiling):
    """How long to wait before attempt ``retries + 2``, in seconds.

    Exponential and capped: 30s, 60s, 120s, 240s, 480s against the defaults,
    which spans about fifteen minutes over five retries. Long enough to outlast
    the ordinary faults -- a provider restarting, a rate limit resetting, a
    network blip -- and short enough that a sign-in code still arrives while the
    member is plausibly still at the screen waiting for it.

    **No jitter, deliberately.** Jitter exists to stop a fleet retrying in
    lockstep, and this queue is one worker sending one message at a time against
    per-message failures. Adding randomness would only make the arrival time of
    a sign-in code harder to account for in a support call.
    """
    return min(base * (2 ** retries), ceiling)


@shared_task(
    bind=True,
    name=DELIVER_EMAIL,
    # **`acks_late` off, against the global default, and this is the one setting
    # here that must not be copied from the other tasks in this project.** The
    # `CELERY_TASK_ACKS_LATE = True` in settings is justified there by every
    # scheduled job being idempotent -- lapsing is computed from `paid_until`,
    # the purges are keyed on a cutoff -- and it says in as many words that a
    # task which is not idempotent must not be added without revisiting the
    # line. Sending an email is that task. Acknowledging late means a worker
    # killed mid-hand-over has its message redelivered, and a member receiving
    # two sign-in codes, or two suspension notices, is a worse outcome than one
    # that was lost: the loss leaves a row on `queued` saying so, while the
    # duplicate leaves two rows that both look correct.
    acks_late=False,
    # Bounded well inside the 20/25-minute global limits, which were sized for a
    # nightly delete pass over a whole table. A hand-over is one SMTP
    # conversation against a ten-second socket timeout; anything past a minute
    # is a wedged connection, and holding the single worker slot for twenty
    # minutes over one message would stall every send behind it.
    soft_time_limit=60,
    time_limit=90,
)
def deliver_email(self, dispatch_id):
    """Hand the message recorded as ``dispatch_id`` to a mail server.

    :param dispatch_id: the ``EmailDispatch`` primary key, as a string. An id
        rather than the message itself, because a task argument sits in Redis in
        cleartext and the body holds a sign-in code -- ``EmailDispatch.body``
        carries that argument -- and because a serialised row is a copy of one
        that may have moved on.
    :returns: the row's ``send_status`` after the attempt, which is what shows
        in a worker log line, or ``None`` where there was no row left to send.

    **A missing row is not an error.** The retention purge deletes send records
    past their window, and a task that outlived its own row -- a queue that
    backed up for a year, or a row deleted by hand out of the admin -- has
    nothing to send and nothing to record. Retrying would only rediscover that.

    **Retries are for transport failures only**, and ``mail.transient`` decides
    which those are. The count and the backoff come from settings; on the last
    attempt the row is marked ``failed`` rather than left waiting for one that
    is never coming, which is what ``final`` is for.
    """
    dispatch = (
        EmailDispatch.objects.select_related('recipient')
        .filter(pk=dispatch_id)
        .first()
    )
    if dispatch is None:
        # `info` rather than `warning`: on a platform that purges send records
        # nightly this is an ordinary consequence of the retention window, not
        # a fault worth anybody's attention.
        logger.info(
            'storefronts.deliver_email: dispatch %s no longer exists; nothing '
            'to send. Most likely purged by the retention window.',
            dispatch_id,
        )
        return None

    max_retries, base, ceiling = _retry_policy()

    # `request.retries` is how many retries have already happened, so this is
    # true on the attempt after the last retry was scheduled -- the one with
    # nothing behind it.
    final = self.request.retries >= max_retries

    try:
        deliver(dispatch, final=final)
    except Exception as error:
        if final or not transient(error):
            # The row already says `failed` and why -- `mail.deliver` wrote it
            # before re-raising. Letting the exception out of here as well would
            # mark the task failed in the worker log for a message nothing is
            # going to send again, and this project's record of a send is the
            # row rather than a Celery result: `CELERY_TASK_IGNORE_RESULT`.
            logger.error(
                'storefronts.deliver_email: dispatch %s failed permanently '
                'after %s attempt(s): %s',
                dispatch.pk,
                dispatch.attempts,
                error,
            )
            return dispatch.send_status

        raise self.retry(
            exc=error,
            countdown=_countdown(self.request.retries, base, ceiling),
            max_retries=max_retries,
        )

    return dispatch.send_status


@shared_task(name=ScheduledTask.PURGE_EMAIL_DISPATCHES.value)
def purge_email_dispatch_records():
    """Delete send records past ``EMAIL_DISPATCH_RETENTION_DAYS``.

    Named for what it does to records rather than after the module function it
    calls, because ``from .retention import purge_email_dispatches`` and a task
    of the same name in the same file would be one import away from calling
    itself.

    :returns: how many send records were deleted.
    """
    with record(ScheduledTask.PURGE_EMAIL_DISPATCHES) as run:
        result = purge_email_dispatches()
        # Zero either way, and the two are different facts: nothing had expired,
        # or retention is switched off and nothing ever will. `affected` cannot
        # carry that distinction, so the second one says so in `detail` -- which
        # is otherwise a failure column, and is the only place in this project
        # where it is used for anything else. A run that deleted nothing for a
        # reason is worth more in the admin than a silent zero.
        run.affected = result.count
        if result.disabled:
            run.detail = (
                'Retention is set to 0 days, which keeps every record. '
                'Nothing was deleted.'
            )

    return run.affected

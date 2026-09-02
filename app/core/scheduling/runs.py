"""The one way a scheduled job records that it ran.

Every task in this project is three lines around :func:`record`, and the point
of that is uniformity: a reader of the admin sees the same four facts for every
job -- started, finished, outcome, count -- because no task decides for itself
what to write.

**The record is not in the job's transaction, and cannot be.** ``lapse_overdue``
opens one ``atomic`` block per membership and the purges delete in a single
statement; none of them wraps the whole run. If the audit row shared a
transaction with the work, the rollback that a failure causes would take the
evidence of the failure with it, and this table would hold nothing but
successes -- an audit trail that is wrong in exactly the case it exists for. So
the row is created before the work starts and updated after it, in autocommit,
and a caller that wraps ``record`` in ``atomic`` has broken that. Nothing in the
code does.

**A failure is re-raised, always.** The record is a side effect and never a
substitute: Celery has to see the exception to log the traceback, count the
failure and apply the task's retry policy. Swallowing it here would produce a
job that reports itself broken in a table nobody is watching and healthy to the
only system that is.
"""
import logging
from contextlib import contextmanager

from django.utils import timezone

from .models import DETAIL_LENGTH, Outcome, ScheduledRun

logger = logging.getLogger(__name__)

__all__ = ['record']


@contextmanager
def record(task):
    """Record one run of ``task``, yielding the row so the body can count.

    Used as::

        with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
            run.affected = services.lapse_overdue()

    Setting ``run.affected`` is the body's whole responsibility. Leaving it
    alone is legitimate and means zero -- a job that ran and found nothing to do.

    :param task: a :class:`~app.core.scheduling.models.ScheduledTask` value, or
        the task name as a string.
    :returns: a context manager yielding an unsaved-since-creation
        :class:`~app.core.scheduling.models.ScheduledRun`.
    """
    run = ScheduledRun.objects.create(task=task)
    logger.info('%s started (run %s)', task, run.id)

    try:
        yield run
    except Exception as exc:
        # The class and the message, not the traceback. The traceback is on the
        # logger below, where a developer reads it; what a ticket quotes is one
        # line, and a `longtext` column full of frames is read by nobody.
        run.outcome = Outcome.FAILED
        run.detail = f'{type(exc).__name__}: {exc}'[:DETAIL_LENGTH]
        run.finished_at = timezone.now()
        run.save(update_fields=['outcome', 'detail', 'finished_at', 'affected'])

        # `exception` rather than `error`: this is the only place the traceback
        # is captured, because the caller re-raises into Celery, which logs it
        # again at its own level. Two copies of a scheduled job's failure is the
        # right number.
        logger.exception('%s failed (run %s)', task, run.id)
        raise

    run.outcome = Outcome.SUCCEEDED
    run.finished_at = timezone.now()
    # `detail` is in the list on this path too. It is normally the failure
    # column and normally blank here, but a body is allowed to leave a note --
    # `storefronts.tasks` does, to say that a zero was retention being switched
    # off rather than nothing having expired. Omitting it would silently discard
    # anything the body wrote.
    run.save(update_fields=['outcome', 'finished_at', 'affected', 'detail'])

    logger.info(
        '%s finished (run %s): %s row(s) in %s',
        task, run.id, run.affected, run.duration,
    )

"""Withdrawing access from memberships that have stopped paying, on a timer.

This is the half of the payment lifecycle Payfast does not tell us about. A
cancelled mandate and a card that stopped working both end the same way -- the
paid-up date passes and no money arrives -- and neither sends a notification
saying "this member should now be switched off". So it is computed rather than
driven by an event, and it has to be *run*.

**This is the thing that runs it.** Until it existed, an unpaid membership kept
its access indefinitely: ``design/features/payments.md`` risk table, Block 0 P2.
The schedule is ``CELERY_BEAT_SCHEDULE`` in ``f2c/settings.py`` and the run
leaves a row in ``scheduling.ScheduledRun``.

Nothing here erases anything, and nothing here signs anybody out of the
platform. ``services.lapse_overdue`` lapses the *membership* and leaves the
account alone -- a club subscription that stopped paying must not lock a member
out of the produce market, and must not lock them out of the one screen that
fixes it. A payment reverses the lapse. See C27.

**The task name is written out rather than derived.** Celery's default would be
``app.core.payments.tasks.lapse_memberships`` -- the import path -- and this
project has already moved every app once, under ``core``/``commerce``/``club``
in Block 0.5. A name that follows the package path would make the next such move
rename a queue key, a beat schedule entry and every historical row in
``ScheduledRun``. The explicit label is the same decision, and the same reason,
as ``AppConfig.label``.
"""
from celery import shared_task

from app.core.scheduling.models import ScheduledTask
from app.core.scheduling.runs import record

from . import services

__all__ = ['lapse_memberships']


@shared_task(name=ScheduledTask.LAPSE_MEMBERSHIPS.value)
def lapse_memberships():
    """Lapse every subscription whose paid-up date has passed.

    :returns: how many memberships lapsed, which is what the run records.
    """
    with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
        # No `today` argument. The service defaults to `gateway.billing_date()`,
        # which is the date the gateway is billing in -- and reading it here
        # instead would put a second answer to "what day is it" in a second
        # timezone next to the first. There is nothing for the schedule to pass.
        run.affected = services.lapse_overdue()

    return run.affected

"""Enforcing the campaign-touch retention window, on a timer.

The same job ``storefronts.tasks`` does, for the table that says which campaign
brought a member. ``retention.py`` carries the POPIA argument -- including why
deleting a touch leaves the member and takes only the label -- and this
schedules it nightly and records that it ran.

No ``days`` and no ``dry_run``, for the reason given in ``storefronts.tasks``.
"""
from celery import shared_task

from app.core.scheduling.models import ScheduledTask
from app.core.scheduling.runs import record

from .retention import purge_campaign_touches

__all__ = ['purge_touches']


@shared_task(name=ScheduledTask.PURGE_CAMPAIGN_TOUCHES.value)
def purge_touches():
    """Delete campaign touches past ``CAMPAIGN_TOUCH_RETENTION_DAYS``.

    :returns: how many touches were deleted.
    """
    with record(ScheduledTask.PURGE_CAMPAIGN_TOUCHES) as run:
        result = purge_campaign_touches()
        run.affected = result.count
        if result.disabled:
            run.detail = (
                'Retention is set to 0 days, which keeps every campaign '
                'touch. Nothing was deleted.'
            )

    return run.affected

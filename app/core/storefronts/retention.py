"""Enforcing ``EMAIL_DISPATCH_RETENTION_DAYS``.

**A retention policy nobody runs is a retention policy nobody has.** POPIA's
retention principle is that personal information is kept no longer than the
purpose needs, and ``EmailDispatch`` holds a member's correspondence history --
which of the club's letters they were sent, and when. The purpose has a shelf
life: a sign-in code nobody remembers asking for is this week's support call,
and a suspension notice is at most a year's worth of dispute. So the window is
declared in ``EMAIL_DISPATCH_RETENTION_DAYS`` and this is what enforces it.

Called from two places and they do the same thing differently: the nightly
Celery task in ``tasks.py``, which is what actually holds the window, and
``manage.py purge_email_dispatches``, which is the same run by hand. The logic
is here rather than in either so that a run by hand and a run on the timer
cannot diverge -- and so that the timer's own record of it, in
``scheduling.ScheduledRun``, counts the same rows the operator would have seen.

Safe to run by hand or twice in a row. Nothing here is reversible, which is why
``dry_run`` exists.
"""
from django.conf import settings

from app.core.common import retention

from .models import EmailDispatch

__all__ = ['purge_email_dispatches', 'window']

#: The window a deployment has not overridden. Twelve months, because the
#: longest-lived question a send record answers is a membership dispute over a
#: suspension notice, which is annual.
DEFAULT_DAYS = 365


def window(days=None):
    """Resolve the window in days, and refuse a negative one.

    Separate from the purge so a caller can refuse a bad window before it
    records anything -- see ``common.retention``.

    :raises ValueError: on a negative window.
    """
    return retention.window(
        days,
        default_days=getattr(
            settings, 'EMAIL_DISPATCH_RETENTION_DAYS', DEFAULT_DAYS
        ),
    )


def purge_email_dispatches(*, days=None, dry_run=False):
    """Delete send records older than the window.

    :param days: override the window for this run, in days. ``None`` uses
        ``EMAIL_DISPATCH_RETENTION_DAYS``.
    :param dry_run: count and delete nothing.
    :returns: an :class:`~app.core.common.retention.Purge`.
    :raises ValueError: on a negative window.
    """
    return retention.purge(
        # By `queued_at`, not by `sent_at`: the age of a record is when the
        # platform tried, and a row that never got past `queued` has an age
        # too. Keying on `sent_at` would leave every failed and every
        # interrupted send behind forever, which is exactly the set an operator
        # is least likely to notice.
        EmailDispatch.objects.queued_before,
        days=window(days),
        dry_run=dry_run,
    )

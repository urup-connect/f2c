"""One retention window, applied the same way twice.

Two tables on this platform expire: ``storefronts.EmailDispatch`` after
``EMAIL_DISPATCH_RETENTION_DAYS`` and ``attribution.CampaignTouch`` after
``CAMPAIGN_TOUCH_RETENTION_DAYS``. The windows differ and the columns they are
measured on differ, and **nothing else about them does** -- so the arithmetic,
the refusal and the meaning of zero live here rather than once per app.

That is not tidiness. Both are POPIA retention enforcement, so the answer to
"what does a window of zero mean?" has to be the same for both: it means *keep
everything, deliberately*, and it is reported as a run that did nothing on
purpose rather than as a no-op dressed up as a success. Two implementations of
that would eventually give two answers, and the one that drifted would be the
one nobody was reading.

**Resolving the window and applying it are two functions on purpose.** A
management command has to be able to refuse a bad ``--days`` *before* the run is
recorded -- otherwise a typo writes a failed run into
``scheduling.ScheduledRun`` and a traceback into the worker's log, and an audit
trail that fills up with operator typos is one nobody reads. So callers resolve
first and apply second, and :func:`purge` takes a window that has already been
checked.

:func:`purge` takes a callable rather than a queryset, because the cutoff does
not exist until the window has been resolved -- and because which column carries
a row's age is the one genuine difference between the two tables.
``EmailDispatch`` ages on ``queued_at`` and not ``sent_at``; ``CampaignTouch``
ages on ``recorded_at`` and not ``seen_at``. Each of those is a decision with a
reason, and each reason is written where the queryset method is.
"""
from datetime import timedelta
from typing import NamedTuple

from django.utils import timezone

__all__ = ['Purge', 'purge', 'window']


class Purge(NamedTuple):
    """What one application of a retention window did.

    ``count`` is what was deleted, or what would have been for a dry run. The
    two are told apart by ``deleted``, which is what stops a caller reporting a
    dry run's count as a deletion.
    """

    #: The window that was applied, in days.
    days: int
    #: The moment rows older than which expired. ``None`` when the window is
    #: disabled, because there is no cutoff to name.
    cutoff: object
    #: How many rows were, or would have been, deleted.
    count: int
    #: Whether the deletion actually ran.
    deleted: bool

    @property
    def disabled(self):
        """Whether retention is switched off -- a window of zero days."""
        return self.days == 0


def window(days, *, default_days):
    """Resolve a retention window in days, and refuse an impossible one.

    :param days: the window asked for, or ``None`` to take the configured one.
        An explicit override is how an operator applies a shorter window once
        without editing the deployment's configuration.
    :param default_days: the configured window, from settings.
    :raises ValueError: on a negative window. Framework-free on purpose -- the
        management commands turn this into a ``CommandError`` and the tasks
        never pass a window at all, and neither behaviour belongs in here.
    """
    if days is None:
        days = default_days

    if days < 0:
        raise ValueError(
            'A retention window cannot be negative. Use 0 to keep '
            'everything, or a number of days.'
        )

    return days


def purge(select, *, days, dry_run=False):
    """Delete what has aged past ``days``, or report what would go.

    :param select: called with the cutoff, returns the queryset of rows that
        have expired. See the module docstring for why this is a callable.
    :param days: the window, already resolved and checked by :func:`window`.
    :param dry_run: count and change nothing.
    """
    if days == 0:
        # Not an error, and not a no-op reported as success: zero is the
        # deployment that has decided to keep everything, and it should hear
        # that its schedule ran and deliberately did nothing.
        return Purge(days=0, cutoff=None, count=0, deleted=False)

    cutoff = timezone.now() - timedelta(days=days)
    stale = select(cutoff)

    # Counted before the delete rather than read off its return value.
    # `QuerySet.delete()` reports rows removed per model including cascades, and
    # what both callers publish is "how many records expired" -- one number, for
    # the table the window is about. Counting first says that plainly.
    count = stale.count()

    if dry_run:
        return Purge(days=days, cutoff=cutoff, count=count, deleted=False)

    stale.delete()
    return Purge(days=days, cutoff=cutoff, count=count, deleted=True)

"""Enforcing ``CAMPAIGN_TOUCH_RETENTION_DAYS``.

**A retention policy nobody runs is a retention policy nobody has.** The same
argument ``storefronts.retention`` makes, applied to a table that holds less: a
touch carries campaign labels, a referring site and a landing path, and no
identifier of its own. What makes it personal information is the member pointing
at it, and POPIA's retention principle applies to the pair.

The purpose has a shelf life, and it is longer than an email's. "Which channel
brought our members" is asked year on year, so the window is two years by
default -- long enough to compare a spring campaign against the previous one,
and short enough that a member is not still described by an advert nobody
remembers buying. It is declared in ``CAMPAIGN_TOUCH_RETENTION_DAYS`` and this
is what enforces it.

**Deleting a touch does not delete the member.** ``Attributed`` points here with
``SET_NULL``, so what the purge takes is the label and what it leaves is the
record -- the member's attribution goes back to "not known", which is where
every untagged member already sits.

Called from the nightly Celery task in ``tasks.py`` and from
``manage.py purge_campaign_touches``; the logic is here so the two cannot
diverge. Safe to run by hand or twice in a row, and irreversible, which is why
``dry_run`` exists.
"""
from django.conf import settings

from app.core.common import retention

from .models import CampaignTouch

__all__ = ['purge_campaign_touches', 'window']

#: The window a deployment has not overridden. Two years, because "which
#: channel brought our members" is asked year on year and the comparison needs
#: two springs in the table.
DEFAULT_DAYS = 730


def window(days=None):
    """Resolve the window in days, and refuse a negative one.

    Separate from the purge so a caller can refuse a bad window before it
    records anything -- see ``common.retention``.

    :raises ValueError: on a negative window.
    """
    return retention.window(
        days,
        default_days=getattr(
            settings, 'CAMPAIGN_TOUCH_RETENTION_DAYS', DEFAULT_DAYS
        ),
    )


def purge_campaign_touches(*, days=None, dry_run=False):
    """Delete campaign touches older than the window.

    :param days: override the window for this run, in days. ``None`` uses
        ``CAMPAIGN_TOUCH_RETENTION_DAYS``.
    :param dry_run: count and delete nothing.
    :returns: an :class:`~app.core.common.retention.Purge`.
    :raises ValueError: on a negative window.
    """
    return retention.purge(
        # Keyed on `recorded_at`, not `seen_at`: the age of a row is when it was
        # written, and `seen_at` is both browser-asserted and frequently null --
        # so a window measured on it would leave exactly the rows nobody would
        # think to check.
        CampaignTouch.objects.recorded_before,
        days=window(days),
        dry_run=dry_run,
    )

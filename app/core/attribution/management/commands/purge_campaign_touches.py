"""Delete campaign touches older than the retention window.

**A retention policy nobody runs is a retention policy nobody has.** The same
argument ``purge_email_dispatches`` makes, applied to a table that holds less: a
touch carries campaign labels, a referring site and a landing path, and no
identifier of its own. What makes it personal information is the member pointing
at it, and POPIA's retention principle applies to the pair.

The purpose has a shelf life, and it is longer than an email's. "Which channel
brought our members" is asked year on year, so the window is two years by
default -- long enough to compare a spring campaign against the previous one, and
short enough that a member is not still described by an advert nobody remembers
buying. It is declared in ``CAMPAIGN_TOUCH_RETENTION_DAYS`` and this is what
enforces it.

Deleting a touch does not delete the member. ``Attributed`` points here with
``SET_NULL``, so what the purge takes is the label and what it leaves is the
record -- the member's attribution goes back to "not known", which is where every
untagged member already sits.

Meant for a timer, safe to run by hand or twice in a row, and irreversible, which
is why ``--dry-run`` exists and why the default output is a count.

Keyed on ``recorded_at``, not ``seen_at``: the age of a row is when it was
written, and ``seen_at`` is both browser-asserted and frequently null -- so a
window measured on it would leave exactly the rows nobody would think to check.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.core.attribution.models import CampaignTouch


class Command(BaseCommand):
    help = (
        'Delete campaign touches older than CAMPAIGN_TOUCH_RETENTION_DAYS. '
        'Intended to run on a schedule.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help=(
                'Override the retention window for this run. Defaults to '
                'CAMPAIGN_TOUCH_RETENTION_DAYS.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be deleted and delete nothing.',
        )

    def handle(self, *args, **options):
        days = options['days']
        if days is None:
            days = getattr(settings, 'CAMPAIGN_TOUCH_RETENTION_DAYS', 730)

        if days < 0:
            raise CommandError(
                'A retention window cannot be negative. Use 0 to keep '
                'everything, or a number of days.'
            )

        if days == 0:
            # Not an error, and not a no-op reported as success: zero is the
            # deployment that has decided to keep everything, and it should hear
            # that its schedule ran and deliberately did nothing.
            self.stdout.write(
                'Retention is set to 0 days, which keeps every campaign '
                'touch. Nothing was deleted.'
            )
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale = CampaignTouch.objects.recorded_before(cutoff)
        count = stale.count()

        if options['dry_run']:
            self.stdout.write(
                f'{count} campaign touch(es) recorded before '
                f'{cutoff:%Y-%m-%d %H:%M} would be deleted. Nothing was '
                f'changed.'
            )
            return

        stale.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'{count} campaign touch(es) older than {days} day(s) '
                f'deleted. The records that pointed at them keep everything '
                f'else and now show no campaign.'
            )
        )

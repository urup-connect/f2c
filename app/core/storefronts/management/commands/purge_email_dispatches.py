"""Delete send records older than the retention window.

**A retention policy nobody runs is a retention policy nobody has.** POPIA's
retention principle is that personal information is kept no longer than the
purpose needs, and ``EmailDispatch`` holds a member's correspondence history --
which of the club's letters they were sent, and when. The purpose has a shelf
life: a sign-in code nobody remembers asking for is this week's support call,
and a suspension notice is at most a year's worth of dispute. So the window is
declared in ``EMAIL_DISPATCH_RETENTION_DAYS`` and this is what enforces it.

Meant for a timer -- the same nightly slot as any other housekeeping job -- and
safe to run by hand or twice in a row. Nothing here is reversible, which is why
``--dry-run`` exists and why the default is a count rather than a silent delete.

Deletes by ``queued_at``, not by ``sent_at``: the age of a record is when the
platform tried, and a row that never got past ``queued`` has an age too. Keying
on ``sent_at`` would leave every failed and every interrupted send behind
forever, which is exactly the set an operator is least likely to notice.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from app.core.storefronts.models import EmailDispatch


class Command(BaseCommand):
    help = (
        'Delete email send records older than EMAIL_DISPATCH_RETENTION_DAYS. '
        'Intended to run on a schedule.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help=(
                'Override the retention window for this run. Defaults to '
                'EMAIL_DISPATCH_RETENTION_DAYS.'
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
            days = getattr(settings, 'EMAIL_DISPATCH_RETENTION_DAYS', 365)

        if days < 0:
            raise CommandError(
                'A retention window cannot be negative. Use 0 to keep '
                'everything, or a number of days.'
            )

        if days == 0:
            # Not an error and not a no-op reported as success: zero is the
            # deployment that has decided to keep everything, and it should hear
            # that its schedule ran and deliberately did nothing.
            self.stdout.write(
                'Retention is set to 0 days, which keeps every record. '
                'Nothing was deleted.'
            )
            return

        cutoff = timezone.now() - timedelta(days=days)
        stale = EmailDispatch.objects.queued_before(cutoff)
        count = stale.count()

        if options['dry_run']:
            self.stdout.write(
                f'{count} send record(s) queued before {cutoff:%Y-%m-%d %H:%M} '
                f'would be deleted. Nothing was changed.'
            )
            return

        stale.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f'{count} send record(s) older than {days} day(s) deleted. '
                f'Records queued before {cutoff:%Y-%m-%d %H:%M} are gone.'
            )
        )

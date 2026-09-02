"""Delete campaign touches older than the retention window, by hand.

The window, why it is two years, why deleting a touch leaves the member, and why
age is measured on ``recorded_at`` rather than ``seen_at`` are all in
``attribution/retention.py``, which does the work. This is the operator's way
in.

**What holds the window is the nightly Celery task**, in
``app/core/attribution/tasks.py``. This command is the same job run by hand,
plus ``--days`` and ``--dry-run`` -- the two things a person needs and a
schedule must not have.

A real run is recorded in ``scheduling.ScheduledRun`` exactly as the nightly one
is, for the reason ``purge_email_dispatches`` gives.
"""
from django.core.management.base import BaseCommand, CommandError

from app.core.attribution import retention
from app.core.scheduling.models import ScheduledTask
from app.core.scheduling.runs import record


class Command(BaseCommand):
    help = (
        'Delete campaign touches older than CAMPAIGN_TOUCH_RETENTION_DAYS. '
        'Runs nightly on Celery beat; this is the same job by hand.'
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
        dry_run = options['dry_run']

        # Resolved and checked here, before anything is recorded. A bad
        # `--days` is a usage mistake, and a usage mistake must not leave a
        # failed run in `ScheduledRun` and a traceback in the log -- an audit
        # trail that fills up with operator typos is one nobody reads.
        try:
            days = retention.window(options['days'])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if dry_run:
            # Outside `record`, and no row: a dry run changed nothing.
            result = retention.purge_campaign_touches(days=days, dry_run=True)
        else:
            with record(ScheduledTask.PURGE_CAMPAIGN_TOUCHES) as run:
                result = retention.purge_campaign_touches(days=days, dry_run=False)
                run.affected = result.count
                if result.disabled:
                    run.detail = (
                        'Retention is set to 0 days, which keeps every '
                        'campaign touch. Nothing was deleted.'
                    )

        if result.disabled:
            self.stdout.write(
                'Retention is set to 0 days, which keeps every campaign '
                'touch. Nothing was deleted.'
            )
            return

        if dry_run:
            self.stdout.write(
                f'{result.count} campaign touch(es) recorded before '
                f'{result.cutoff:%Y-%m-%d %H:%M} would be deleted. Nothing was '
                f'changed.'
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'{result.count} campaign touch(es) older than {result.days} '
                f'day(s) deleted. The records that pointed at them keep '
                f'everything else and now show no campaign.'
            )
        )

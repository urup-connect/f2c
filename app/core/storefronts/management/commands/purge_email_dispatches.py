"""Delete send records older than the retention window, by hand.

The window, why it is a year, and why age is measured on ``queued_at`` rather
than ``sent_at`` are all in ``storefronts/retention.py``, which does the work.
This is the operator's way in.

**What holds the window is the nightly Celery task**, in
``app/core/storefronts/tasks.py``. This command is the same job run by hand,
plus the two things a person needs and a schedule must not have: ``--days``, to
apply a shorter window once without editing the deployment's configuration, and
``--dry-run``, because nothing here is reversible.

A real run is recorded in ``scheduling.ScheduledRun`` exactly as the nightly one
is. That record is the evidence that a declared retention period is an enforced
one, and a deletion of personal information by hand needs it at least as much as
a deletion on a timer does.
"""
from django.core.management.base import BaseCommand, CommandError

from app.core.scheduling.models import ScheduledTask
from app.core.scheduling.runs import record
from app.core.storefronts import retention


class Command(BaseCommand):
    help = (
        'Delete email send records older than EMAIL_DISPATCH_RETENTION_DAYS. '
        'Runs nightly on Celery beat; this is the same job by hand.'
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
            result = retention.purge_email_dispatches(days=days, dry_run=True)
        else:
            with record(ScheduledTask.PURGE_EMAIL_DISPATCHES) as run:
                result = retention.purge_email_dispatches(days=days, dry_run=False)
                run.affected = result.count
                if result.disabled:
                    run.detail = (
                        'Retention is set to 0 days, which keeps every record. '
                        'Nothing was deleted.'
                    )

        if result.disabled:
            self.stdout.write(
                'Retention is set to 0 days, which keeps every record. '
                'Nothing was deleted.'
            )
            return

        if dry_run:
            self.stdout.write(
                f'{result.count} send record(s) queued before '
                f'{result.cutoff:%Y-%m-%d %H:%M} would be deleted. Nothing was '
                f'changed.'
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'{result.count} send record(s) older than {result.days} '
                f'day(s) deleted. Records queued before '
                f'{result.cutoff:%Y-%m-%d %H:%M} are gone.'
            )
        )

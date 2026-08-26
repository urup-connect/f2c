"""Load a filled-in stock template.

``cultivator-stock-upload.md``, and `todo.md` Block 3: "Excel batch upload
against a published template", plus "batch upload validation and an error report
a cultivator can act on". This is both, and the report is the reason the command
exists in this shape rather than as a bare import.

**Run it with ``--dry-run`` first.** Nothing is written unless every row is
valid, so a real run against a bad file does exactly what a dry run does and says
so -- but a dry run makes that explicit rather than something to infer from the
exit code.

The all-or-nothing rule is the service's, and its docstring argues it: a
five-hundred-row upload that loads four hundred and eighty leaves a cultivator
working out which, and a second upload that either duplicates or skips.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.plant.services import upload_plants
from app.plant.spreadsheet import SheetError

from ._cultivator import resolve_cultivator

#: Errors printed in full before the rest are summarised. A cultivator with a
#: column formatted as text has one mistake repeated on every row, and a wall of
#: nine hundred identical lines buries the one thing they need to read.
ERROR_LIMIT = 40


class Command(BaseCommand):
    help = 'Load a cultivator\'s plant stock from a filled-in Excel template.'

    def add_arguments(self, parser):
        parser.add_argument('file', help='Path to the filled-in .xlsx template.')
        parser.add_argument(
            '--cultivator',
            required=True,
            help=(
                'The cultivator the stock belongs to, by email address or '
                'nickname. Never read from the file: a column naming the '
                'cultivator is a column one could fill in with another\'s name.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate and report. Write nothing.',
        )

    def handle(self, *args, **options):
        cultivator = resolve_cultivator(options['cultivator'])

        source = Path(options['file'])
        if not source.is_file():
            raise CommandError(f'{source} is not a file.')

        try:
            report = upload_plants(
                cultivator, source, dry_run=options['dry_run']
            )
        except SheetError as error:
            # The workbook is the wrong shape, so no row was looked at. Raised
            # rather than reported per row: a missing column is not something a
            # cultivator fixes row by row.
            raise CommandError(str(error)) from error

        if report.errors:
            self._write_errors(report)
            raise CommandError(report.summary())

        if report.dry_run:
            self.stdout.write(self.style.SUCCESS(report.summary()))
            self.stdout.write(
                'Run again without --dry-run to load them.'
            )
            return

        self.stdout.write(self.style.SUCCESS(report.summary()))
        if report.batches:
            self.stdout.write(f'Batches: {", ".join(report.batches)}')
        if report.created:
            first = report.created[0].serial
            last = report.created[-1].serial
            # Contiguous, because the whole upload takes one allocation from the
            # counter. Printing the range rather than every serial keeps a
            # five-hundred-plant load to one line while still naming what to
            # search for.
            self.stdout.write(f'Serials: {first} to {last}')

    def _write_errors(self, report):
        self.stderr.write(self.style.ERROR(
            f'{report.error_count} problem(s) found. Nothing was loaded.'
        ))
        for error in report.errors[:ERROR_LIMIT]:
            self.stderr.write(f'  {error}')

        remaining = report.error_count - ERROR_LIMIT
        if remaining > 0:
            # Said out loud rather than truncated silently. A report that stops
            # without saying it stopped reads as a complete list.
            self.stderr.write(self.style.WARNING(
                f'  ... and {remaining} more, not shown. Fix these first — they '
                'are often the same mistake repeated.'
            ))

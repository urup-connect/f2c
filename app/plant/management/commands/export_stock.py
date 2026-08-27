"""Write a cultivator's stock on hand to a spreadsheet.

``drawio``, cultivator story v1: "Manage inventory — harvest update, add/remove,
upload, **SOH imports and exports**". The import is `upload_plants`; this is the
export, and the two are deliberately not the same file. Every plant in an export
already exists, so uploading one back is refused by the duplicate check — the
template is for stock that is new, and it carries none of the platform-generated
columns an export leads with.

The scopes are the two inventory screens the same story names — "My inventory for
sale" and "My member-owned inventory" — and the default is the first, because
that is what stock on hand means.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.plant.services import (
    SCOPE_FOR_SALE,
    SCOPES,
    build_stock_export,
    stock_for_export,
)

from ._cultivator import resolve_cultivator


class Command(BaseCommand):
    help = "Export a cultivator's stock on hand to an .xlsx file."

    def add_arguments(self, parser):
        parser.add_argument(
            'cultivator', help='The cultivator, by email address or nickname.'
        )
        parser.add_argument(
            '--scope',
            choices=sorted(SCOPES),
            default=SCOPE_FOR_SALE,
            help=(
                'Which inventory to export. "for-sale" is unsold stock and is '
                'the default; "member-owned" is what members have bought and '
                'this cultivator is still growing; "all" is both.'
            ),
        )
        parser.add_argument(
            '--output',
            help=(
                'Where to write the .xlsx. Defaults to '
                'stock-<nickname>-<scope>.xlsx in the working directory.'
            ),
        )

    def handle(self, *args, **options):
        cultivator = resolve_cultivator(options['cultivator'])
        scope = options['scope']

        plants = stock_for_export(cultivator, scope)

        destination = Path(
            options['output']
            or f'stock-{cultivator.display_name}-{scope}.xlsx'.replace(' ', '-')
        )
        if destination.is_dir():
            raise CommandError(f'{destination} is a directory.')

        workbook = build_stock_export(plants, scope_label=SCOPES[scope])
        try:
            workbook.save(destination)
        except OSError as error:
            raise CommandError(f'Could not write {destination}: {error}') from error

        count = plants.count()
        if not count:
            # Not an error, and said out loud rather than left to be discovered
            # on opening the file. A cultivator whose whole crop has sold has an
            # empty for-sale export and needs to know that is what happened
            # rather than that the export failed.
            self.stderr.write(self.style.WARNING(
                f'{cultivator.display_name} has no plants in scope '
                f'"{scope}" — {destination} has headings and no rows.'
            ))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Wrote {destination}: {count} plant(s), '
            f'{SCOPES[scope].lower()}.'
        ))

"""Write the stock-upload template for one cultivator.

``cultivator-stock-upload.md`` calls for "an excel template". This generates it
per cultivator rather than publishing one static file, because the useful half of
a template is the part that stops a mistake being made: the Strain column is a
dropdown of the cultivator's own listed strains, and the Reference sheet says
what each of them will be delivered as. A generic template would have somebody
typing strain names from memory into a column that refuses anything it does not
recognise.

`GET /api/stock/template` serves the same workbook to a cultivator who may load
stock for the farm, so this is no longer the only way to get one. It stays
because it writes a file to a path: staff producing a template for somebody who
is not yet appointed, and anything scripted, have no session to present.
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from app.club.plant.services import template_reference
from app.club.plant.spreadsheet import build_template

from ._cultivator import resolve_cultivator


class Command(BaseCommand):
    help = "Write the plant stock-upload template for a cultivator."

    def add_arguments(self, parser):
        parser.add_argument(
            'cultivator',
            help='The cultivator, by email address or nickname.',
        )
        parser.add_argument(
            '--output',
            help=(
                'Where to write the .xlsx. Defaults to '
                'stock-template-<nickname>.xlsx in the working directory.'
            ),
        )

    def handle(self, *args, **options):
        cultivator = resolve_cultivator(options['cultivator'])
        reference = template_reference(cultivator)

        if not reference:
            # Not an error. A cultivator who has been appointed but has no
            # published listings yet is a normal state, and a template with no
            # dropdown is still the right shape to fill in -- but they need to
            # know why the Reference sheet is empty, because that is exactly what
            # will make the upload refuse every row.
            self.stderr.write(self.style.WARNING(
                f'{cultivator.pseudonym} has no listed strain offerings, so '
                'the template has no strain list and an upload against it would '
                'refuse every row. Publish a listing first.'
            ))

        destination = Path(
            options['output']
            or f'stock-template-{cultivator.pseudonym}.xlsx'.replace(' ', '-')
        )
        if destination.is_dir():
            raise CommandError(f'{destination} is a directory.')

        workbook = build_template(reference)
        try:
            workbook.save(destination)
        except OSError as error:
            raise CommandError(f'Could not write {destination}: {error}') from error

        self.stdout.write(self.style.SUCCESS(
            f'Wrote {destination} with {len(reference)} strain(s) '
            f'for {cultivator.pseudonym}.'
        ))

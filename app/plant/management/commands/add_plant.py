"""Capture one plant.

``cultivator-stock-upload.md``: "Cultivators can load individual plants or batch
upload multiple plants using an excel template." This is the first half, and
``upload_plants`` is the second. They share their validation and their write --
``services.capture_plant`` and ``services.upload_plants`` differ only in where the
values came from.

The arguments are the brief's own field list, minus the two things that are not a
cultivator's to supply: the cultivator (an option, never data -- see
``spreadsheet``'s docstring) and everything the platform generates, which is the
serial, the leaf rating, the status and the day counts.

For more than a handful of plants, use the template. This exists for the one
correction that does not justify a spreadsheet.
"""
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from app.plant.services import capture_plant
from app.plant.spreadsheet import HEADINGS

from ._cultivator import resolve_cultivator


class Command(BaseCommand):
    help = 'Capture a single plant for a cultivator.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cultivator',
            required=True,
            help='The cultivator the plant belongs to, by email or nickname.',
        )
        parser.add_argument(
            '--plant-id',
            required=True,
            dest='cultivator_plant_id',
            help='Your own identifier for the plant, as it is labelled on the pot.',
        )
        parser.add_argument(
            '--strain', required=True,
            help='A strain you have a listed offering for.',
        )
        parser.add_argument(
            '--grow-price', required=True,
            help='What a member pays to have it grown, in Rand.',
        )
        parser.add_argument(
            '--planting-date', required=True, help='YYYY-MM-DD.'
        )
        parser.add_argument(
            '--bloom-date', required=True, dest='estimated_bloom_date',
            help='Estimated bloom date, YYYY-MM-DD.',
        )
        parser.add_argument(
            '--harvest-date', required=True, dest='estimated_harvest_date',
            help='Estimated harvest date, YYYY-MM-DD.',
        )
        parser.add_argument(
            '--minimum-yield', required=True, dest='minimum_yield_grams',
            help='The least dry weight undertaken, in grams.',
        )
        parser.add_argument(
            '--product-types', default='', dest='finished_product_types',
            help=(
                'Optional, comma-separated. Leave it out and the plant offers '
                'whatever the strain listing offers; give it and it must match '
                'that listing.'
            ),
        )
        parser.add_argument(
            '--batch', default='',
            help='Optional crop or batch number. Reuse one to group plants.',
        )

    def handle(self, *args, **options):
        cultivator = resolve_cultivator(options['cultivator'])

        raw = {key: options[key] for key in HEADINGS if key in options}

        try:
            plant = capture_plant(cultivator, **raw)
        except ValidationError as invalid:
            # The service reports per field, keyed by the internal name, so this
            # renders the heading a cultivator would recognise from the template
            # rather than a Python attribute.
            self.stderr.write(self.style.ERROR('That plant was not loaded:'))
            for key, messages in invalid.message_dict.items():
                heading = HEADINGS.get(key, key)
                for message in messages:
                    self.stderr.write(f'  {heading}: {message}')
            raise CommandError('Nothing was loaded.') from invalid

        self.stdout.write(self.style.SUCCESS(
            f'Loaded {plant.serial} — {plant.strain.name} for '
            f'{plant.cultivator_pseudonym}, leaf rating {plant.leaf_rating}.'
        ))

"""Turning a workbook into stock, and refusing to.

``test_spreadsheet.py`` covers what the file says; this covers whether it is
true, and what gets written when it is. Four things here are the ones worth
having:

**Nothing is written unless every row is valid.** The test that matters is not
that a bad row is reported — it is that a *good* row in the same file is not
loaded. A partial load leaves a cultivator working out which of five hundred
plants arrived.

**The cultivator cannot come from the file.** There is no column for it, and the
test asserting that lives here as well as in the reader, because this is the
layer that would have to trust it.

**C18 confirms and never overrides.** A blank product-type column inherits from
the listing. A filled-in one that names something the listing does not offer is
an error pointing at the listing, which is the one place that list is edited.

**Serials come out contiguous and the leaf rating is derived.** Both are
properties of how the write is done — one allocation for the batch, and
``create`` rather than ``bulk_create`` — and both would break silently.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from openpyxl import Workbook

from app.club.finished_product.models import FinishedProductType
from app.club.strains.models import (
    CultivatorStrainListing,
    ListingStatus,
    Strain,
    StrainStatus,
    StrainType,
)

from ..models import Batch, Plant, PlantStatus, SerialCounter
from ..services import template_reference, upload_plants
from ..spreadsheet import COLUMNS, HEADINGS, PLANTS_SHEET, SheetError
from .support import PlantTestCase

KEYS = [key for key, _, _ in COLUMNS]

BASE = {
    'cultivator_plant_id': 'POT-1',
    'strain': 'OG Kush',
    'grow_price': 950,
    'planting_date': date(2026, 3, 1),
    'estimated_bloom_date': date(2026, 4, 30),
    'estimated_harvest_date': date(2026, 6, 29),
    'minimum_yield_grams': 30,
    'finished_product_types': None,
    'batch': None,
}


def sheet_of(rows):
    book = Workbook()
    sheet = book.active
    sheet.title = PLANTS_SHEET
    sheet.append([HEADINGS[key] for key in KEYS])
    for row in rows:
        sheet.append([row.get(key) for key in KEYS])

    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


def row(**overrides):
    return BASE | overrides


class UploadTests(PlantTestCase):
    def test_a_valid_file_loads_stock(self):
        report = upload_plants(self.cultivator, sheet_of([row()]))

        self.assertTrue(report.ok)
        self.assertEqual(len(report.created), 1)
        plant = report.created[0]
        self.assertEqual(plant.cultivator_plant_id, 'POT-1')
        self.assertEqual(plant.listing, self.listing)
        self.assertEqual(plant.grow_price, Decimal('950.00'))
        self.assertEqual(plant.planting_date, date(2026, 3, 1))

    def test_a_loaded_plant_starts_as_the_cultivators_unsold_stock(self):
        report = upload_plants(self.cultivator, sheet_of([row()]))

        plant = report.created[0]
        self.assertEqual(plant.status, PlantStatus.PREFLOWERING)
        self.assertIsNone(plant.owner_id)
        self.assertTrue(plant.is_available)

    def test_the_leaf_rating_is_derived_on_the_way_in(self):
        """The reason the write is `create` per row and not `bulk_create`:
        `bulk_create` skips `save`, and `save` is the only thing deriving this.
        Uniquely among the derived columns here it has no check constraint to
        catch the omission, so a bulk write would load five hundred plants with
        no swap value and nothing would say so."""
        report = upload_plants(self.cultivator, sheet_of([
            row(grow_price=1650), row(cultivator_plant_id='POT-2', grow_price=500),
        ]))

        self.assertEqual(
            [plant.leaf_rating for plant in report.created],
            [Decimal('1.5'), Decimal('0.5')],
        )

    def test_serials_are_allocated_contiguously_for_the_whole_upload(self):
        """One allocation per upload, so the plants in a crop come out in a
        block somebody can quote as a range."""
        report = upload_plants(self.cultivator, sheet_of([
            row(cultivator_plant_id=f'POT-{n}') for n in range(1, 6)
        ]))

        serials = [plant.serial for plant in report.created]
        self.assertEqual(serials, sorted(serials))
        self.assertEqual(len(set(serials)), 5)
        self.assertEqual(SerialCounter.objects.get(name='plant').next_value, 6)

    def test_the_product_types_are_inherited_from_the_listing(self):
        """C18. Nothing is written per plant."""
        report = upload_plants(self.cultivator, sheet_of([row()]))

        self.assertEqual(
            list(report.created[0].finished_product_types), [self.pre_roll]
        )

    def test_a_dry_run_writes_nothing_and_says_so(self):
        report = upload_plants(self.cultivator, sheet_of([row()]), dry_run=True)

        self.assertTrue(report.ok)
        self.assertTrue(report.dry_run)
        self.assertEqual(report.created, [])
        self.assertEqual(Plant.objects.count(), 0)
        self.assertIn('Nothing was loaded', report.summary())

    def test_a_dry_run_counts_what_would_load(self):
        report = upload_plants(self.cultivator, sheet_of([
            row(), row(cultivator_plant_id='POT-2'),
        ]), dry_run=True)

        self.assertEqual(report.rows_read, 2)

    def test_the_count_includes_rows_that_failed_to_parse(self):
        """Otherwise a single unparseable row reports "1 problem in 0 rows",
        which reads like a bug in the report rather than in the file."""
        report = upload_plants(self.cultivator, sheet_of([row(grow_price='free')]))

        self.assertEqual(report.rows_read, 1)
        self.assertIn('1 problem(s) in 1 row(s)', report.summary())


class AllOrNothingTests(PlantTestCase):
    def test_one_bad_row_stops_the_whole_file(self):
        """The test that matters. A partial load leaves a cultivator working out
        which of five hundred plants arrived, and a second upload that either
        duplicates or skips."""
        report = upload_plants(self.cultivator, sheet_of([
            row(cultivator_plant_id='POT-1'),
            row(cultivator_plant_id='POT-2', grow_price='free'),
            row(cultivator_plant_id='POT-3'),
        ]))

        self.assertFalse(report.ok)
        self.assertEqual(report.created, [])
        self.assertEqual(Plant.objects.count(), 0)

    def test_no_serials_are_consumed_by_a_refused_upload(self):
        """Otherwise a cultivator fixing and re-uploading burns a block of
        serials per attempt, and the numbering has gaps nobody can explain."""
        upload_plants(self.cultivator, sheet_of([row(grow_price='free')]))

        self.assertEqual(SerialCounter.objects.get(name='plant').next_value, 1)

    def test_no_batch_is_created_by_a_refused_upload(self):
        upload_plants(self.cultivator, sheet_of([
            row(batch='2026-01', grow_price='free')
        ]))

        self.assertEqual(Batch.objects.count(), 0)

    def test_the_errors_are_sorted_by_row(self):
        """A report in the file's own order is one somebody can work down."""
        report = upload_plants(self.cultivator, sheet_of([
            row(cultivator_plant_id='POT-1', grow_price='free'),
            row(cultivator_plant_id='POT-2'),
            row(cultivator_plant_id='POT-3', strain='Nonesuch'),
        ]))

        self.assertEqual([error.row for error in report.errors], [2, 4])


class StrainResolutionTests(PlantTestCase):
    def test_a_strain_the_cultivator_has_no_listing_for_is_refused(self):
        Strain.objects.create(
            name='Durban Poison',
            strain_type=StrainType.SATIVA,
            status=StrainStatus.ACTIVE,
        )

        report = upload_plants(
            self.cultivator, sheet_of([row(strain='Durban Poison')])
        )

        self.assertFalse(report.ok)
        self.assertIn('no listed offering', report.errors[0].message)

    def test_a_draft_listing_is_not_enough(self):
        """Loading stock against a listing a member cannot buy from puts plants
        behind a wall."""
        self.listing.status = ListingStatus.DRAFT
        self.listing.save(update_fields=['status'])

        report = upload_plants(self.cultivator, sheet_of([row()]))

        self.assertFalse(report.ok)
        self.assertIn('draft', report.errors[0].message)

    def test_the_strain_name_is_matched_case_insensitively(self):
        """Typing `og kush` into a column whose dropdown says `OG Kush` is not a
        mistake worth refusing, and the catalogue is already unique
        case-insensitively so the fold cannot make two strains collide."""
        report = upload_plants(self.cultivator, sheet_of([row(strain='og kush')]))

        self.assertTrue(report.ok)

    def test_another_cultivators_listing_is_invisible(self):
        """The security property. There is no column for the cultivator and no
        path by which a file loads stock into somebody else's inventory."""
        _other_grower, other = self.another_cultivator()
        CultivatorStrainListing.objects.create(
            cultivator=other,
            strain=self.strain,
            status=ListingStatus.LISTED,
            short_description='Theirs.',
            default_grow_price=Decimal('900.00'),
            minimum_yield_grams=Decimal('25.00'),
        )

        report = upload_plants(other, sheet_of([row()]))

        self.assertTrue(report.ok)
        self.assertEqual(report.created[0].listing.cultivator, other)
        # And the original cultivator's stock is untouched.
        self.assertEqual(
            Plant.objects.available_from(self.cultivator).count(), 0
        )


class ProductTypeConfirmationTests(PlantTestCase):
    """The C18 column: optional, and a confirmation rather than an override."""

    def test_a_blank_column_inherits_from_the_listing(self):
        report = upload_plants(self.cultivator, sheet_of([
            row(finished_product_types=None)
        ]))

        self.assertTrue(report.ok)
        self.assertEqual(
            list(report.created[0].finished_product_types), [self.pre_roll]
        )

    def test_naming_what_the_listing_offers_is_accepted(self):
        report = upload_plants(self.cultivator, sheet_of([
            row(finished_product_types='Pre-rolls')
        ]))

        self.assertTrue(report.ok)

    def test_a_code_is_accepted_as_well_as_a_name(self):
        """An export shows codes; the Reference sheet shows names. A cultivator
        pasting either back in is doing something reasonable."""
        report = upload_plants(self.cultivator, sheet_of([
            row(finished_product_types='pre-roll')
        ]))

        self.assertTrue(report.ok)

    def test_naming_something_the_listing_does_not_offer_points_at_the_listing(self):
        """Not at the plant. The listing is the one place that list is edited."""
        FinishedProductType.objects.create(code='loose', name='Loose')

        report = upload_plants(self.cultivator, sheet_of([
            row(finished_product_types='Loose')
        ]))

        self.assertFalse(report.ok)
        self.assertIn('does not offer that', report.errors[0].message)
        self.assertIn('Add it to the listing', report.errors[0].message)

    def test_a_type_that_does_not_exist_is_reported_as_a_typo(self):
        """Checked for existence before it is checked against the listing, so a
        misspelling is reported as one."""
        report = upload_plants(self.cultivator, sheet_of([
            row(finished_product_types='Pre rolls')
        ]))

        self.assertFalse(report.ok)
        self.assertIn('No such finished product type', report.errors[0].message)

    def test_a_withdrawn_type_cannot_be_named(self):
        FinishedProductType.objects.create(
            code='edible', name='Edibles', is_available=False
        )

        report = upload_plants(self.cultivator, sheet_of([
            row(finished_product_types='Edibles')
        ]))

        self.assertFalse(report.ok)


class DuplicateAgainstExistingStockTests(PlantTestCase):
    def test_a_plant_id_already_loaded_is_refused(self):
        """The likelier mistake: a cultivator re-uploading a file they have
        already used."""
        upload_plants(self.cultivator, sheet_of([row()]))

        report = upload_plants(self.cultivator, sheet_of([row()]))

        self.assertFalse(report.ok)
        self.assertIn('already loaded', report.errors[0].message)

    def test_the_check_ignores_case(self):
        upload_plants(self.cultivator, sheet_of([row(cultivator_plant_id='POT-1')]))

        report = upload_plants(
            self.cultivator, sheet_of([row(cultivator_plant_id='pot-1')])
        )

        self.assertFalse(report.ok)

    def test_it_is_reported_before_anything_is_inserted(self):
        """The unique constraint would catch it too — on the insert, partway
        through a transaction, with a message naming an index."""
        upload_plants(self.cultivator, sheet_of([row()]))

        report = upload_plants(self.cultivator, sheet_of([
            row(), row(cultivator_plant_id='POT-2'),
        ]))

        self.assertEqual(Plant.objects.count(), 1)
        self.assertEqual(report.errors[0].column, HEADINGS['cultivator_plant_id'])


class BatchTests(PlantTestCase):
    def test_rows_sharing_a_reference_land_in_one_batch(self):
        report = upload_plants(self.cultivator, sheet_of([
            row(cultivator_plant_id='POT-1', batch='2026-01'),
            row(cultivator_plant_id='POT-2', batch='2026-01'),
            row(cultivator_plant_id='POT-3', batch='2026-02'),
        ]))

        self.assertEqual(Batch.objects.count(), 2)
        self.assertEqual(report.batches, ['2026-01', '2026-02'])
        first, second, third = report.created
        self.assertEqual(first.batch, second.batch)
        self.assertNotEqual(second.batch, third.batch)

    def test_a_blank_reference_leaves_the_plant_unbatched(self):
        """`cultivator-stock-upload.md` makes it optional."""
        report = upload_plants(self.cultivator, sheet_of([row(batch=None)]))

        self.assertIsNone(report.created[0].batch_id)
        self.assertEqual(Batch.objects.count(), 0)

    def test_a_second_upload_joins_the_existing_batch(self):
        """A cultivator loading the second half of a crop names the same batch."""
        upload_plants(self.cultivator, sheet_of([
            row(cultivator_plant_id='POT-1', batch='2026-01')
        ]))
        report = upload_plants(self.cultivator, sheet_of([
            row(cultivator_plant_id='POT-2', batch='2026-01')
        ]))

        self.assertEqual(Batch.objects.count(), 1)
        self.assertEqual(
            report.created[0].batch, Batch.objects.get(reference='2026-01')
        )


class TemplateReferenceTests(PlantTestCase):
    def test_it_lists_the_cultivators_listed_strains(self):
        reference = template_reference(self.cultivator)

        self.assertEqual(reference, [('OG Kush', 'Pre-rolls')])

    def test_a_draft_listing_is_left_out(self):
        """It would put a strain in the dropdown that the upload then refuses."""
        self.listing.status = ListingStatus.DRAFT
        self.listing.save(update_fields=['status'])

        self.assertEqual(template_reference(self.cultivator), [])

    def test_a_listing_with_no_product_types_says_so(self):
        """A blank cell reads as missing data; this reads as a problem to fix."""
        self.listing.finished_product_types.clear()

        self.assertEqual(
            template_reference(self.cultivator), [('OG Kush', '— nothing set —')]
        )


class CommandTests(PlantTestCase):
    def upload(self, rows, *args, tmp=None, **kwargs):
        path = tmp / 'stock.xlsx'
        path.write_bytes(sheet_of(rows).getvalue())
        call_command(
            'upload_plants', str(path),
            '--cultivator', 'Kloof', *args, **kwargs
        )
        return path

    def test_it_loads_a_file(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            self.upload([row()], tmp=Path(directory))

        self.assertEqual(Plant.objects.count(), 1)

    def test_a_bad_file_fails_the_command_and_writes_nothing(self):
        """A management command that reports a problem and exits zero is one a
        deployment pipeline treats as a success."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(CommandError) as refused:
                self.upload([row(grow_price='free')], tmp=Path(directory))

        self.assertIn('Nothing was loaded', str(refused.exception))
        self.assertEqual(Plant.objects.count(), 0)

    def test_a_dry_run_writes_nothing(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            self.upload([row()], '--dry-run', tmp=Path(directory))

        self.assertEqual(Plant.objects.count(), 0)

    def test_a_missing_file_is_refused_before_anything_else(self):
        with self.assertRaises(CommandError) as refused:
            call_command(
                'upload_plants', 'no-such-file.xlsx',
                '--cultivator', 'Kloof',
            )

        self.assertIn('not a file', str(refused.exception))

    def test_an_account_that_is_not_a_cultivator_is_refused(self):
        """Loading stock against a member's account creates inventory nobody can
        sell and a listing nobody owns."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stock.xlsx'
            path.write_bytes(sheet_of([row()]).getvalue())

            with self.assertRaises(CommandError) as refused:
                call_command(
                    'upload_plants', str(path),
                    '--cultivator', 'Sam',
                )

        self.assertIn('No producer trades as', str(refused.exception))

    def test_an_unknown_cultivator_is_refused(self):
        with self.assertRaises(CommandError):
            call_command(
                'upload_plants', 'x.xlsx', '--cultivator', 'Nobody'
            )

    def test_a_primary_key_is_not_a_trading_name(self):
        """The command resolves a **farm** by the name it trades under.

        It used to resolve a person by email address or nickname, and refused an
        erased one. A `Producer` is an organisation: erasing the grower who
        keyed the stock in does not retire their farm, and a UUID was never a
        trading name — so what this now pins down is that the argument is a
        name, not an identifier.
        """
        import tempfile
        from pathlib import Path

        self.grower.soft_delete()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stock.xlsx'
            path.write_bytes(sheet_of([row()]).getvalue())

            with self.assertRaises(CommandError) as refused:
                call_command(
                    'upload_plants', str(path),
                    '--cultivator', str(self.cultivator.pk),
                )

        self.assertIn('No producer trades as', str(refused.exception))

    def test_the_template_command_writes_a_workbook(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'template.xlsx'
            call_command(
                'plant_template', 'Kloof',
                '--output', str(destination),
            )

            self.assertTrue(destination.is_file())

            # And the template it wrote is one the reader accepts.
            from ..spreadsheet import read_rows
            with self.assertRaises(SheetError) as refused:
                read_rows(destination)
            self.assertIn('no plants', str(refused.exception))


class SheetShapeAtServiceLevelTests(PlantTestCase):
    def test_a_wrong_shaped_workbook_raises_rather_than_reporting_rows(self):
        book = Workbook()
        book.active.title = 'Sheet1'
        stream = BytesIO()
        book.save(stream)
        stream.seek(0)

        with self.assertRaises(SheetError):
            upload_plants(self.cultivator, stream)

"""Capturing one plant, and the two routes to it.

``cultivator-stock-upload.md`` asks for individual capture beside the batch
upload and gives one list of requirements for both. The tests that matter here
are therefore not the rules -- ``test_spreadsheet.py`` and ``test_upload.py``
already cover those -- but the claim that **there is only one set of them.** If
the single-plant path ever grew a validator of its own, the half that drifted
would be this one, because it is the half used less until Block 9.

So the assertions come in three kinds:

* the same refusals reach a single capture as reach a row of a workbook;
* the errors arrive keyed by field, which is what a form needs and what an
  upload report does not;
* **the admin add form allocates a serial.** That one is a fix, not a feature:
  ``serial`` is ``editable=False`` and so on no form, and the column is unique
  but not null — so before this, the first plant added by hand would have saved
  with a blank serial and the second would have failed on the index.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase

from app.finished_product.models import FinishedProductType
from app.strains.models import ListingStatus

from ..admin import PlantAdmin, PlantCaptureForm
from ..models import Batch, Plant, PlantStatus, SerialCounter
from ..services import capture_plant
from .support import BLOOMS, HARVESTS, PLANTED, PlantTestCase

RAW = {
    'cultivator_plant_id': 'POT-1',
    'strain': 'OG Kush',
    'grow_price': '950',
    'planting_date': '2026-03-01',
    'estimated_bloom_date': '2026-04-30',
    'estimated_harvest_date': '2026-06-29',
    'minimum_yield_grams': '30',
}


def raw(**overrides):
    return RAW | overrides


class CaptureTests(PlantTestCase):
    def test_one_plant_is_loaded(self):
        plant = capture_plant(self.cultivator, **raw())

        self.assertEqual(plant.cultivator_plant_id, 'POT-1')
        self.assertEqual(plant.listing, self.listing)
        self.assertEqual(plant.grow_price, Decimal('950.00'))
        self.assertEqual(plant.planting_date, PLANTED)
        self.assertEqual(Plant.objects.count(), 1)

    def test_it_starts_as_the_cultivators_unsold_stock(self):
        plant = capture_plant(self.cultivator, **raw())

        self.assertEqual(plant.status, PlantStatus.PREFLOWERING)
        self.assertIsNone(plant.owner_id)

    def test_the_platform_allocates_the_serial_and_the_leaf_rating(self):
        """The fields `cultivator-stock-upload.md` lists as system-generated."""
        plant = capture_plant(self.cultivator, **raw(grow_price='1650'))

        self.assertTrue(plant.serial.startswith('CC-'))
        self.assertEqual(plant.leaf_rating, Decimal('1.5'))

    def test_it_draws_on_the_same_serial_counter_as_an_upload(self):
        """Two allocators would eventually reissue a number that is already on a
        certificate."""
        capture_plant(self.cultivator, **raw(cultivator_plant_id='POT-1'))
        capture_plant(self.cultivator, **raw(cultivator_plant_id='POT-2'))

        self.assertEqual(SerialCounter.objects.get(name='plant').next_value, 3)

    def test_dates_may_arrive_as_dates_rather_than_strings(self):
        """A form hands over `date` objects; a shell hands over text. The same
        coercion takes both."""
        plant = capture_plant(self.cultivator, **raw(
            planting_date=PLANTED,
            estimated_bloom_date=BLOOMS,
            estimated_harvest_date=HARVESTS,
        ))

        self.assertEqual(plant.planting_date, PLANTED)

    def test_a_batch_reference_groups_the_plant(self):
        capture_plant(self.cultivator, **raw(batch='2026-01'))
        plant = capture_plant(
            self.cultivator, **raw(cultivator_plant_id='POT-2', batch='2026-01')
        )

        self.assertEqual(Batch.objects.count(), 1)
        self.assertEqual(plant.batch.reference, '2026-01')

    def test_the_product_types_are_inherited(self):
        """C18. There is no per-plant override on either route."""
        plant = capture_plant(self.cultivator, **raw())

        self.assertEqual(list(plant.finished_product_types), [self.pre_roll])

    def test_the_optional_fields_may_be_left_out_entirely(self):
        """A caller should not have to pass keys for things it has no value for."""
        plant = capture_plant(self.cultivator, **raw())

        self.assertIsNone(plant.batch_id)


class SharedRuleTests(PlantTestCase):
    """The same refusals as a workbook row, reached through the other door."""

    def assert_refused(self, field, fragment, **overrides):
        with self.assertRaises(ValidationError) as refused:
            capture_plant(self.cultivator, **raw(**overrides))

        self.assertIn(field, refused.exception.message_dict)
        self.assertIn(
            fragment, ' '.join(refused.exception.message_dict[field])
        )
        self.assertEqual(Plant.objects.count(), 0)

    def test_an_ambiguous_date_is_refused_rather_than_guessed(self):
        self.assert_refused(
            'planting_date', 'must be a date', planting_date='03/04/2026'
        )

    def test_a_price_with_three_decimals_is_refused_rather_than_rounded(self):
        self.assert_refused(
            'grow_price', 'two decimal places', grow_price='100.005'
        )

    def test_a_free_plant_is_refused(self):
        self.assert_refused('grow_price', 'more than zero', grow_price='0')

    def test_a_missing_required_field_is_refused(self):
        self.assert_refused('minimum_yield_grams', 'required',
                            minimum_yield_grams=None)

    def test_bloom_before_planting_is_refused(self):
        self.assert_refused(
            'estimated_bloom_date', 'flower before it was planted',
            estimated_bloom_date='2026-02-01',
        )

    def test_harvest_before_bloom_is_refused(self):
        """No check constraint expresses this one, so validation is the only
        thing that catches it."""
        self.assert_refused(
            'estimated_harvest_date', 'before bloom',
            estimated_bloom_date='2026-06-29',
            estimated_harvest_date='2026-04-30',
        )

    def test_a_strain_with_no_listing_is_refused(self):
        self.assert_refused(
            'strain', 'no listed offering', strain='Nonesuch'
        )

    def test_a_draft_listing_is_not_enough(self):
        self.listing.status = ListingStatus.DRAFT
        self.listing.save(update_fields=['status'])

        self.assert_refused('strain', 'draft')

    def test_a_plant_id_already_used_is_refused(self):
        capture_plant(self.cultivator, **raw())

        with self.assertRaises(ValidationError) as refused:
            capture_plant(self.cultivator, **raw())

        self.assertIn(
            'already loaded',
            ' '.join(refused.exception.message_dict['cultivator_plant_id']),
        )
        self.assertEqual(Plant.objects.count(), 1)

    def test_a_plant_id_used_by_an_upload_is_refused(self):
        """The two routes share one namespace, because they share one table.

        Asserted directly rather than through ``assert_refused``, which expects
        no stock at all — here a plant is loaded on purpose first, and the point
        is that the second route sees it.
        """
        from ..services import upload_plants
        from .test_upload import row, sheet_of

        upload_plants(self.cultivator, sheet_of([row()]))

        with self.assertRaises(ValidationError) as refused:
            capture_plant(self.cultivator, **raw())

        self.assertIn(
            'already loaded',
            ' '.join(refused.exception.message_dict['cultivator_plant_id']),
        )
        self.assertEqual(Plant.objects.count(), 1)

    def test_a_product_type_the_listing_does_not_offer_is_refused(self):
        FinishedProductType.objects.create(code='loose', name='Loose')

        self.assert_refused(
            'finished_product_types', 'does not offer that',
            finished_product_types='Loose',
        )

    def test_no_serial_is_consumed_by_a_refused_capture(self):
        """As with an upload: otherwise retrying burns a number per attempt and
        the sequence has gaps nobody can explain."""
        with self.assertRaises(ValidationError):
            capture_plant(self.cultivator, **raw(grow_price='free'))

        self.assertEqual(SerialCounter.objects.get(name='plant').next_value, 1)

    def test_another_cultivator_cannot_capture_against_this_listing(self):
        """The security property, on this route as well as the upload's."""
        other = self.another_member('other@example.com', 'Tygerberg')
        other.role = 'cultivator'
        other.save(update_fields=['role'])

        with self.assertRaises(ValidationError):
            capture_plant(other, **raw())

        self.assertEqual(Plant.objects.count(), 0)

    def test_every_problem_in_one_capture_is_reported_at_once(self):
        """A form that reveals one error per submission is a form somebody
        submits six times."""
        with self.assertRaises(ValidationError) as refused:
            capture_plant(
                self.cultivator,
                **raw(grow_price='free', minimum_yield_grams='nope'),
            )

        self.assertEqual(
            set(refused.exception.message_dict),
            {'grow_price', 'minimum_yield_grams'},
        )


class CommandTests(PlantTestCase):
    def add(self, **overrides):
        options = {
            '--cultivator': 'grower@example.com',
            '--plant-id': 'POT-1',
            '--strain': 'OG Kush',
            '--grow-price': '950',
            '--planting-date': '2026-03-01',
            '--bloom-date': '2026-04-30',
            '--harvest-date': '2026-06-29',
            '--minimum-yield': '30',
        } | overrides
        flat = []
        for name, value in options.items():
            flat.extend([name, value])
        call_command('add_plant', *flat)

    def test_it_loads_one_plant(self):
        self.add()

        self.assertEqual(Plant.objects.count(), 1)

    def test_a_bad_value_fails_the_command_and_writes_nothing(self):
        with self.assertRaises(CommandError) as refused:
            self.add(**{'--grow-price': 'free'})

        self.assertIn('Nothing was loaded', str(refused.exception))
        self.assertEqual(Plant.objects.count(), 0)

    def test_an_account_that_is_not_a_cultivator_is_refused(self):
        with self.assertRaises(CommandError) as refused:
            self.add(**{'--cultivator': 'member@example.com'})

        self.assertIn('not a cultivator', str(refused.exception))

    def test_the_product_types_may_be_confirmed(self):
        self.add(**{'--product-types': 'Pre-rolls'})

        self.assertEqual(Plant.objects.count(), 1)

    def test_a_batch_may_be_named(self):
        self.add(**{'--batch': '2026-01'})

        self.assertEqual(Batch.objects.get().reference, '2026-01')


class AdminCaptureFormTests(PlantTestCase):
    def payload(self, **overrides):
        return {
            'listing': str(self.listing.pk),
            'cultivator_plant_id': 'POT-1',
            'batch': '',
            'grow_price': '950.00',
            'minimum_yield_grams': '30.00',
            'planting_date': '2026-03-01',
            'estimated_bloom_date': '2026-04-30',
            'estimated_harvest_date': '2026-06-29',
        } | overrides

    def test_a_complete_form_is_valid(self):
        form = PlantCaptureForm(data=self.payload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_the_form_does_not_ask_for_anything_the_platform_generates(self):
        form = PlantCaptureForm()

        for generated in ('serial', 'leaf_rating', 'status', 'owner',
                          'harvested_on'):
            with self.subTest(field=generated):
                self.assertNotIn(generated, form.fields)

    def test_only_listed_offerings_are_offered(self):
        """A draft listing in the dropdown is a choice the save would refuse."""
        self.listing.status = ListingStatus.DRAFT
        self.listing.save(update_fields=['status'])

        form = PlantCaptureForm()

        self.assertEqual(list(form.fields['listing'].queryset), [])

    def test_a_date_error_lands_on_its_own_field(self):
        """Not on the form as a whole. `RowError.key` is what makes that
        possible."""
        form = PlantCaptureForm(data=self.payload(
            estimated_bloom_date='2026-02-01'
        ))

        self.assertFalse(form.is_valid())
        self.assertIn('estimated_bloom_date', form.errors)

    def test_a_duplicate_plant_id_lands_on_its_own_field(self):
        capture_plant(self.cultivator, **raw())

        form = PlantCaptureForm(data=self.payload())

        self.assertFalse(form.is_valid())
        self.assertIn('cultivator_plant_id', form.errors)

    def test_a_listing_error_lands_on_the_listing_field(self):
        """A row names a strain; the form picks a listing. The mapping is what
        turns one into the other."""
        self.listing.status = ListingStatus.WITHDRAWN
        self.listing.save(update_fields=['status'])

        form = PlantCaptureForm(data=self.payload())

        self.assertFalse(form.is_valid())
        # The listing is no longer a choice at all, so that is what is reported.
        self.assertIn('listing', form.errors)

    def test_a_missing_listing_does_not_crash_the_other_checks(self):
        form = PlantCaptureForm(data=self.payload(listing=''))

        self.assertFalse(form.is_valid())
        self.assertIn('listing', form.errors)


class AdminSerialTests(PlantTestCase):
    """The fix. Without it, adding a plant by hand produced a blank serial."""

    def setUp(self):
        super().setUp()
        self.admin = PlantAdmin(Plant, AdminSite())

    def add_through_admin(self, **overrides):
        form = PlantCaptureForm(data={
            'listing': str(self.listing.pk),
            'cultivator_plant_id': 'POT-1',
            'batch': '',
            'grow_price': '950.00',
            'minimum_yield_grams': '30.00',
            'planting_date': '2026-03-01',
            'estimated_bloom_date': '2026-04-30',
            'estimated_harvest_date': '2026-06-29',
        } | overrides)
        self.assertTrue(form.is_valid(), form.errors)
        plant = form.save(commit=False)
        self.admin.save_model(None, plant, form, change=False)
        return plant

    def test_a_serial_is_allocated_on_add(self):
        plant = self.add_through_admin()

        plant.refresh_from_db()
        self.assertTrue(plant.serial.startswith('CC-'))

    def test_two_plants_added_by_hand_get_different_serials(self):
        """The second one is what used to fail on the unique index."""
        first = self.add_through_admin(cultivator_plant_id='POT-1')
        second = self.add_through_admin(cultivator_plant_id='POT-2')

        self.assertNotEqual(first.serial, second.serial)
        self.assertEqual(Plant.objects.count(), 2)

    def test_the_leaf_rating_is_derived_on_add(self):
        """`save_model` goes through `Plant.save`, which is the only thing that
        derives it."""
        plant = self.add_through_admin(grow_price='1650.00')

        plant.refresh_from_db()
        self.assertEqual(plant.leaf_rating, Decimal('1.5'))

    def test_a_change_does_not_reallocate_the_serial(self):
        """A serial is printed on a certificate. Re-saving a plant must not move
        it."""
        plant = self.add_through_admin()
        original = plant.serial

        plant.grow_price = Decimal('1100.00')
        self.admin.save_model(None, plant, None, change=True)

        plant.refresh_from_db()
        self.assertEqual(plant.serial, original)

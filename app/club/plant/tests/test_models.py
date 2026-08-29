"""The plant, its serials, its constraints, and the reads Blocks 5 to 10 need.

Written around the same idea as the rest of the suite: test what is invisible
when it breaks. Four things here qualify.

**A reissued serial.** It is printed on a certificate of ownership and is how a
plant is traced. Two plants sharing one is not a validation error somebody sees,
it is two members holding proof of the same thing.

**A stale leaf rating.** Derived from the grow price and, uniquely among the
derived columns in this project, *not* backed by a check constraint — the model
says why. So the tests carry the weight the database cannot, including a test
that asserts the gap so nobody mistakes it for closed.

**A gap in the ownership history.** ``transfer_to`` writes the column and the
tenure in one transaction. A plant with two open tenures has two current owners
and no way to say which certificate is real, so that half *is* enforced in SQL
and is asserted through a raw update.

**The four-plant count.** C16 decides that a harvested plant does not count
toward the statutory limit. Nothing enforces the limit yet — it is Block 10 — but
the queryset that will be asked is here, and getting it wrong means either
refusing a swap ``harvest.md`` explicitly permits or letting a member hold five
flowering plants.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from ..models import (
    Batch,
    OwnershipReason,
    Plant,
    PlantOwnership,
    PlantStatus,
    SerialCounter,
    allocate_serials,
    format_serial,
)
from .support import BLOOMS, HARVESTS, PLANTED, PlantTestCase


class SerialTests(TestCase):
    def test_a_serial_reads_as_an_identifier_not_a_number(self):
        """It goes on a certificate and into a search box."""
        self.assertEqual(format_serial(1), 'CC-00000001')
        self.assertEqual(format_serial(123456), 'CC-00123456')

    def test_serials_sort_in_the_order_they_were_issued(self):
        """The reason they are zero-padded: an admin list and a spreadsheet
        export have to agree."""
        issued = allocate_serials(12)

        self.assertEqual(issued, sorted(issued))

    def test_serials_are_consecutive_within_one_allocation(self):
        """So the plants in one crop come out contiguous."""
        issued = allocate_serials(3)

        self.assertEqual(
            issued, [format_serial(1), format_serial(2), format_serial(3)]
        )

    def test_a_second_allocation_carries_on_where_the_first_stopped(self):
        allocate_serials(5)

        self.assertEqual(allocate_serials(1), [format_serial(6)])

    def test_the_counter_is_advanced_by_the_size_of_the_allocation(self):
        """One call per upload, not one per row: a five-hundred-plant batch takes
        the counter once."""
        allocate_serials(500)

        self.assertEqual(
            SerialCounter.objects.get(name='plant').next_value, 501
        )

    def test_an_empty_allocation_is_refused(self):
        with self.assertRaises(ValueError):
            allocate_serials(0)

    def test_a_missing_counter_refuses_rather_than_restarting_the_sequence(self):
        """The failure worth being loud about.

        A `get_or_create` here would silently restart at 1 and reissue serials
        that are already printed on certificates in members' hands. The
        migration seeds the row; its absence afterwards is somebody's mistake,
        not something to repair automatically.
        """
        SerialCounter.objects.all().delete()

        with self.assertRaises(SerialCounter.DoesNotExist) as refused:
            allocate_serials(1)

        self.assertIn('restart', str(refused.exception))


class PlantIdentityTests(PlantTestCase):
    def test_a_plant_carries_both_identifiers(self):
        """`plant-id-numbers.md`: the cultivator's own ID and the platform's."""
        plant = self.make_plant(cultivator_plant_id='POT-7')

        self.assertEqual(plant.cultivator_plant_id, 'POT-7')
        self.assertTrue(plant.serial.startswith('CC-'))

    def test_two_plants_cannot_share_a_platform_serial(self):
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_plant(serial=plant.serial, cultivator_plant_id='POT-2')

    def test_a_cultivator_cannot_reuse_their_own_plant_id_on_one_listing(self):
        self.make_plant(cultivator_plant_id='POT-1')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_plant(cultivator_plant_id='POT-1')

    def test_the_strain_and_cultivator_are_read_through_the_listing(self):
        """Never stored twice, so the pair cannot disagree about who grows what."""
        plant = self.make_plant()

        self.assertEqual(plant.strain, self.strain)
        self.assertEqual(plant.cultivator, self.cultivator)

    def test_the_pseudonym_is_a_nickname_and_never_an_email_address(self):
        """It goes on the certificate of ownership. Section 6.6 of
        `roles-and-permissions.md`."""
        plant = self.make_plant()

        self.assertEqual(plant.cultivator_pseudonym, 'Kloof')
        self.assertNotIn('@', plant.cultivator_pseudonym)

    def test_the_product_types_are_inherited_from_the_listing(self):
        """C18's middle level, with no per-plant override."""
        plant = self.make_plant()

        self.assertEqual(list(plant.finished_product_types), [self.pre_roll])

    def test_the_string_form_is_the_serial(self):
        self.assertEqual(str(self.make_plant()), Plant.objects.get().serial)


class LeafRatingColumnTests(PlantTestCase):
    def test_the_rating_is_derived_on_creation(self):
        plant = self.make_plant(grow_price=Decimal('1650.00'))

        self.assertEqual(plant.leaf_rating, Decimal('1.5'))

    def test_the_rating_follows_a_price_change(self):
        """Block 4 lets a cultivator reprice unsold inventory."""
        plant = self.make_plant(grow_price=Decimal('500.00'))

        plant.grow_price = Decimal('1900.00')
        plant.save()

        plant.refresh_from_db()
        self.assertEqual(plant.leaf_rating, Decimal('2.0'))

    def test_the_rating_follows_a_partial_save(self):
        """Where a derived column normally gets left behind."""
        plant = self.make_plant(grow_price=Decimal('500.00'))

        plant.grow_price = Decimal('1900.00')
        plant.save(update_fields=['grow_price'])

        plant.refresh_from_db()
        self.assertEqual(plant.leaf_rating, Decimal('2.0'))

    def test_a_raw_price_update_leaves_the_rating_stale_and_nothing_stops_it(self):
        """The gap, asserted so it is not mistaken for a guarantee.

        Every other derived column in this project is tied to its source by a
        check constraint. This one is not: the rounding rule would have to be a
        database expression, and division plus ROUND differs enough between
        SQLite and MySQL — and between decimal and float arithmetic — that the
        constraint would risk refusing the model's own write.

        So `save` is the only thing keeping this true, and **a price change has
        to go through the model.** Block 4 is where that matters.
        """
        plant = self.make_plant(grow_price=Decimal('500.00'))

        Plant.objects.filter(pk=plant.pk).update(grow_price=Decimal('1900.00'))

        plant.refresh_from_db()
        self.assertEqual(plant.leaf_rating, Decimal('0.5'))

    def test_a_negative_rating_is_refused_by_the_database(self):
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plant.objects.filter(pk=plant.pk).update(
                    leaf_rating=Decimal('-1.0')
                )


class PlantConstraintTests(PlantTestCase):
    def test_a_free_plant_is_refused_by_the_database(self):
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plant.objects.filter(pk=plant.pk).update(
                    grow_price=Decimal('0.00')
                )

    def test_a_zero_minimum_yield_is_refused_by_the_database(self):
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plant.objects.filter(pk=plant.pk).update(
                    minimum_yield_grams=Decimal('0.00')
                )

    def test_an_unrecognised_status_is_refused_by_the_database(self):
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plant.objects.filter(pk=plant.pk).update(status='composted')

    def test_a_harvest_before_planting_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_plant(
                    estimated_harvest_date=PLANTED - timedelta(days=1)
                )

    def test_a_bloom_before_planting_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_plant(
                    estimated_bloom_date=PLANTED - timedelta(days=1)
                )

    def test_a_harvested_plant_cannot_lack_an_actual_harvest_date(self):
        """`harvest.md` makes the date and the status one fact in two columns.
        The Block 6 notification reads the status; the certificate reads the
        date."""
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plant.objects.filter(pk=plant.pk).update(
                    status=PlantStatus.HARVESTED
                )

    def test_an_unharvested_plant_cannot_carry_a_harvest_date(self):
        plant = self.make_plant()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Plant.objects.filter(pk=plant.pk).update(harvested_on=HARVESTS)


class HarvestTests(PlantTestCase):
    def test_harvesting_records_the_actual_date_and_keeps_the_estimate(self):
        """`harvest.md`: the cultivator converts the estimate to an actual date.
        The estimate is what the member bought against, so it stays."""
        plant = self.make_plant()
        actual = HARVESTS + timedelta(days=4)

        plant.mark_harvested(actual)

        plant.refresh_from_db()
        self.assertEqual(plant.harvested_on, actual)
        self.assertEqual(plant.estimated_harvest_date, HARVESTS)
        self.assertEqual(plant.status, PlantStatus.HARVESTED)

    def test_harvesting_before_planting_is_refused_with_a_readable_error(self):
        plant = self.make_plant()

        with self.assertRaises(ValidationError) as refused:
            plant.mark_harvested(PLANTED - timedelta(days=1))

        self.assertEqual(
            refused.exception.error_list[0].code, 'harvest_before_planting'
        )

    def test_an_unharvested_status_is_refused(self):
        plant = self.make_plant()

        with self.assertRaises(ValidationError):
            plant.mark_harvested(HARVESTS, status=PlantStatus.IN_BLOOM)

    def test_days_to_harvest_stops_counting_once_harvested(self):
        plant = self.make_plant()
        self.assertIsNotNone(plant.days_to_harvest(today=PLANTED))

        plant.mark_harvested(HARVESTS)

        self.assertIsNone(plant.days_to_harvest(today=PLANTED))

    def test_days_to_bloom_stops_counting_once_in_bloom(self):
        plant = self.make_plant()
        self.assertEqual(plant.days_to_bloom(today=PLANTED), 60)

        plant.status = PlantStatus.IN_BLOOM
        plant.save(update_fields=['status'])

        self.assertIsNone(plant.days_to_bloom(today=PLANTED))

    def test_the_derived_day_counts_are_not_columns(self):
        """They would be wrong by one every midnight, and a stored field needing
        a daily recalculation is a scheduled job whose failure is invisible."""
        columns = {field.name for field in Plant._meta.fields}

        self.assertNotIn('days_to_bloom', columns)
        self.assertNotIn('days_to_harvest', columns)


class OwnershipTests(PlantTestCase):
    def test_a_new_plant_is_the_cultivators_stock(self):
        """No owner, and no tenure. The history is a list of members, not one
        that begins with the person who grew it."""
        plant = self.make_plant()

        self.assertIsNone(plant.owner_id)
        self.assertTrue(plant.is_available)
        self.assertEqual(plant.ownerships.count(), 0)

    def test_a_transfer_sets_the_owner_and_opens_a_tenure(self):
        plant = self.make_plant()

        tenure = plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        plant.refresh_from_db()
        self.assertEqual(plant.owner, self.member)
        self.assertTrue(tenure.is_open)
        self.assertEqual(tenure.reason, OwnershipReason.PURCHASE)

    def test_a_second_transfer_closes_the_first_tenure(self):
        """The history survives every transfer. `todo.md` Block 3."""
        plant = self.make_plant()
        alex = self.another_member()

        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        plant.transfer_to(alex, reason=OwnershipReason.SWAP)

        plant.refresh_from_db()
        self.assertEqual(plant.owner, alex)
        self.assertEqual(plant.ownerships.count(), 2)
        self.assertEqual(
            plant.ownerships.filter(released_at__isnull=True).count(), 1
        )

    def test_the_whole_chain_of_owners_is_recoverable(self):
        """What a certificate of ownership is evidence from."""
        plant = self.make_plant()
        alex = self.another_member()

        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        plant.transfer_to(alex, reason=OwnershipReason.SWAP)

        held_by = [
            tenure.owner for tenure in plant.ownerships.order_by('acquired_at')
        ]
        self.assertEqual(held_by, [self.member, alex])

    def test_transferring_to_the_same_member_twice_is_refused(self):
        """It would close and reopen a tenure for no event, putting a
        discontinuity in the history."""
        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        with self.assertRaises(ValidationError) as refused:
            plant.transfer_to(self.member, reason=OwnershipReason.SWAP)

        self.assertEqual(refused.exception.error_list[0].code, 'already_owner')

    def test_a_withdrawn_plant_cannot_change_hands(self):
        plant = self.make_plant()
        plant.disable()

        with self.assertRaises(ValidationError) as refused:
            plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        self.assertEqual(refused.exception.error_list[0].code, 'plant_disabled')

    def test_a_plant_cannot_have_two_open_tenures(self):
        """Two current owners means two certificates and no way to say which is
        real. Enforced in SQL, because this is the half that can be."""
        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlantOwnership.objects.create(
                    plant=plant,
                    owner=self.another_member(),
                    acquired_at=timezone.now(),
                    reason=OwnershipReason.ADJUSTMENT,
                )

    def test_reopening_a_closed_tenure_by_hand_is_refused(self):
        """The three-valued-logic case. A CHECK passes when its condition is
        unknown, so without the explicit null test in the constraint this write
        would succeed and the unique index above would guard nothing."""
        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        plant.transfer_to(self.another_member(), reason=OwnershipReason.SWAP)
        closed = plant.ownerships.filter(released_at__isnull=False).get()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlantOwnership.objects.filter(pk=closed.pk).update(
                    released_at=None
                )

    def test_a_tenure_cannot_end_before_it_began(self):
        plant = self.make_plant()
        tenure = plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlantOwnership.objects.filter(pk=tenure.pk).update(
                    released_at=tenure.acquired_at - timedelta(days=1),
                    current_for_plant=None,
                )

    def test_nothing_in_the_database_ties_the_owner_column_to_the_open_tenure(self):
        """The gap, named. A cross-table equality is not something a check
        constraint can express, so `transfer_to` is the only thing keeping the
        two in step and a raw update walks past it. Block 2's object-level work
        should put this behind a service."""
        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        alex = self.another_member()

        Plant.objects.filter(pk=plant.pk).update(owner=alex)

        plant.refresh_from_db()
        self.assertEqual(plant.owner, alex)
        self.assertEqual(
            plant.ownerships.get(released_at__isnull=True).owner, self.member
        )

    def test_the_tenure_string_shows_a_nickname_and_never_an_email_address(self):
        plant = self.make_plant()
        tenure = plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        self.assertIn('Sam', str(tenure))
        self.assertNotIn('@', str(tenure))


class StockQuerySetTests(PlantTestCase):
    """The reads that make a cultivator's *stock* a queryset rather than a model.

    `design/backend.md` section 3 records the decision; these are what it means
    in practice. There is no quantity anywhere in this schema.
    """

    def test_available_from_is_a_cultivators_stock_on_hand(self):
        unsold = self.make_plant(cultivator_plant_id='POT-1')
        sold = self.make_plant(cultivator_plant_id='POT-2')
        sold.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        withdrawn = self.make_plant(cultivator_plant_id='POT-3')
        withdrawn.disable()

        self.assertEqual(
            list(Plant.objects.available_from(self.cultivator)), [unsold]
        )

    def test_held_by_is_a_members_own_inventory(self):
        mine = self.make_plant(cultivator_plant_id='POT-1')
        mine.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        theirs = self.make_plant(cultivator_plant_id='POT-2')
        theirs.transfer_to(self.another_member(), reason=OwnershipReason.PURCHASE)

        self.assertEqual(list(Plant.objects.held_by(self.member)), [mine])

    def test_a_withdrawn_plant_leaves_a_members_inventory(self):
        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        plant.disable()

        self.assertEqual(list(Plant.objects.held_by(self.member)), [])

    def test_the_flowering_count_excludes_a_harvested_plant(self):
        """C16. The Act's limit is on *flowering* plants, and `harvest.md`
        explicitly lets a member swap for a harvested one — so counting those
        would have two briefs refusing the same transaction."""
        flowering = self.make_plant(cultivator_plant_id='POT-1')
        flowering.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        flowering.status = PlantStatus.IN_BLOOM
        flowering.save(update_fields=['status'])

        harvested = self.make_plant(cultivator_plant_id='POT-2')
        harvested.transfer_to(self.member, reason=OwnershipReason.PURCHASE)
        harvested.mark_harvested(HARVESTS)

        self.assertEqual(Plant.objects.held_by(self.member).count(), 2)
        self.assertEqual(
            list(Plant.objects.flowering_held_by(self.member)), [flowering]
        )

    def test_a_preflowering_plant_counts_toward_the_four(self):
        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        self.assertEqual(Plant.objects.flowering_held_by(self.member).count(), 1)

    def test_swappable_excludes_a_harvested_plant(self):
        """`harvest.md`: "After harvest no further swapping for paying members."
        The sharing-member exception is a rule about who, not about the plant."""
        flowering = self.make_plant(cultivator_plant_id='POT-1')
        harvested = self.make_plant(cultivator_plant_id='POT-2')
        harvested.mark_harvested(HARVESTS)

        self.assertEqual(list(Plant.objects.swappable()), [flowering])

    def test_by_planting_date_counts_plants_per_date(self):
        """Step 3 of `member-plant-purchase.md`: dates with a count, not serials.

        The member picks a date and a quantity, and the system allocates the
        specific serials afterwards — so this query must never leak them.
        """
        self.make_plant(cultivator_plant_id='POT-1')
        self.make_plant(cultivator_plant_id='POT-2')
        self.make_plant(
            cultivator_plant_id='POT-3',
            estimated_harvest_date=HARVESTS + timedelta(days=30),
        )

        rows = list(Plant.objects.available().by_planting_date())

        self.assertEqual(
            rows,
            [
                {
                    'planting_date': PLANTED,
                    'estimated_harvest_date': HARVESTS,
                    'plants': 2,
                },
                {
                    'planting_date': PLANTED,
                    'estimated_harvest_date': HARVESTS + timedelta(days=30),
                    'plants': 1,
                },
            ],
        )
        self.assertNotIn('serial', rows[0])


class BatchTests(PlantTestCase):
    def test_a_batch_groups_plants_and_is_optional(self):
        batch = Batch.objects.create(
            cultivator=self.cultivator, reference='2026-01'
        )
        grouped = self.make_plant(cultivator_plant_id='POT-1', batch=batch)
        self.make_plant(cultivator_plant_id='POT-2')

        self.assertEqual(list(batch.plants.all()), [grouped])

    def test_a_cultivator_cannot_reuse_a_batch_reference(self):
        Batch.objects.create(cultivator=self.cultivator, reference='2026-01')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Batch.objects.create(
                    cultivator=self.cultivator, reference='2026-01'
                )

    def test_two_cultivators_may_number_their_crops_the_same_way(self):
        """`2026-01` is not a collision between two farms, and scoping this to
        live rows would need a partial index MySQL will not build."""
        _other_grower, other = self.another_cultivator()
        Batch.objects.create(cultivator=self.cultivator, reference='2026-01')

        Batch.objects.create(cultivator=other, reference='2026-01')

    def test_disabling_a_batch_does_not_withdraw_its_plants(self):
        """A mis-numbered crop must not void stock a member has bought."""
        batch = Batch.objects.create(
            cultivator=self.cultivator, reference='2026-01'
        )
        plant = self.make_plant(batch=batch)

        batch.disabled_at = timezone.now()
        batch.save(update_fields=['disabled_at'])

        plant.refresh_from_db()
        self.assertTrue(batch.is_disabled)
        self.assertTrue(plant.is_available)

    def test_a_batch_with_plants_cannot_be_deleted(self):
        """PROTECT. Deleting a batch must not take stock with it."""
        batch = Batch.objects.create(
            cultivator=self.cultivator, reference='2026-01'
        )
        self.make_plant(batch=batch)

        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                batch.delete()


class WithdrawalTests(PlantTestCase):
    def test_disabling_takes_a_plant_off_sale(self):
        plant = self.make_plant()

        plant.disable()

        plant.refresh_from_db()
        self.assertFalse(plant.is_available)
        self.assertEqual(list(Plant.objects.available()), [])

    def test_a_plant_with_a_history_cannot_be_deleted(self):
        """PROTECT on `PlantOwnership.plant`. A certificate of ownership is
        evidence, and evidence whose subject can be deleted is not evidence."""
        from django.db.models import ProtectedError

        plant = self.make_plant()
        plant.transfer_to(self.member, reason=OwnershipReason.PURCHASE)

        with self.assertRaises(ProtectedError):
            with transaction.atomic():
                plant.delete()

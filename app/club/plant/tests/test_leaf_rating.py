"""The leaf rating, against the brief's own worked examples.

``twp-tasks/swap-zone.md`` gives five, and they are the specification: this is a
number members will trade against, so a formula that agrees with the prose but
not with the examples is wrong whatever the prose says.

The examples also matter because they are what catches a floating-point
implementation. In binary, ``0.85`` is not representable and Python's ``round``
uses banker's rounding — so a float version puts R1,250 at 1.0 rather than 1.5,
which is the one case the brief does *not* cover and therefore the one nobody
would notice.

The brief leaves two things it does not decide. The midpoint is one and C4
records the choice. The other is the bottom of the scale, where the formula alone
gives 0.0 — answered in the brief now, and covered by ``FloorTests`` and the two
swappability classes below.

C4 is the other half of this file: the leaf rating is swap value and has nothing
to do with reputation. There is no test here for a rating changing when a review
is left, because nothing should ever make it do so.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.utils import timezone

from ..models import (
    HARVESTED_STATUSES,
    LEAF_RATING_FLOOR,
    SWAP_MINIMUM_LEAF_RATING,
    Plant,
    PlantStatus,
    leaf_rating_for,
)
from .support import HARVESTS, PlantTestCase


class WorkedExampleTests(SimpleTestCase):
    """The five in `swap-zone.md`, verbatim."""

    def test_the_briefs_examples(self):
        for price, expected in (
            ('500', '0.5'),
            ('850', '1.0'),
            ('1100', '1.0'),
            ('1650', '1.5'),
            ('1900', '2.0'),
        ):
            with self.subTest(grow_price=price):
                self.assertEqual(
                    leaf_rating_for(Decimal(price)), Decimal(expected)
                )


class TieBreakTests(SimpleTestCase):
    """The case the brief avoids. C4, and a decision rather than a derivation."""

    def test_a_midpoint_rounds_up(self):
        """R1,250 is exactly 1.25. Round half up favours the member offering the
        plant, which is the right way for a rounding rule in a barter system to
        lean — and it is what `todo.md` chose."""
        self.assertEqual(leaf_rating_for(Decimal('1250')), Decimal('1.5'))

    def test_every_midpoint_rounds_up_not_just_the_documented_one(self):
        """Banker's rounding would take 0.25 down and 0.75 up, so one example is
        not enough to tell the two rules apart."""
        for price, expected in (
            ('250', '0.5'),
            ('750', '1.0'),
            ('1250', '1.5'),
            ('1750', '2.0'),
        ):
            with self.subTest(grow_price=price):
                self.assertEqual(
                    leaf_rating_for(Decimal(price)), Decimal(expected)
                )

    def test_the_result_is_always_a_multiple_of_a_half_above_the_floor(self):
        """From R250 up, which is where the formula proper applies. Below it the
        answer is the floor and deliberately not a step — see `FloorTests`."""
        for rand in range(250, 4000, 37):
            with self.subTest(grow_price=rand):
                rating = leaf_rating_for(Decimal(rand))
                self.assertEqual((rating * 2) % 1, 0, f'{rating} is not a step')


class FloorTests(SimpleTestCase):
    """Under R250, where the formula alone gives nothing.

    `swap-zone.md` sets no floor and its cheapest example is R500, so the
    question was open. It is answered in the brief: a grow price that low is not
    expected in practice, so the rule chosen is the one that keeps an unexpected
    price harmless — the plant rates 0.1 and cannot be swapped, rather than
    rating 0.0 and matching nothing, or everything for free.
    """

    def test_a_cheap_plant_floors_rather_than_rounding_to_zero(self):
        self.assertEqual(leaf_rating_for(Decimal('0.01')), Decimal('0.1'))
        self.assertEqual(leaf_rating_for(Decimal('100')), Decimal('0.1'))
        self.assertEqual(leaf_rating_for(Decimal('249.99')), Decimal('0.1'))

    def test_the_floor_ends_where_the_first_step_begins(self):
        """R250 earns a real step rather than the floor, so the two rules meet
        with neither a gap nor an overlap."""
        self.assertEqual(leaf_rating_for(Decimal('250')), Decimal('0.5'))

    def test_no_price_ever_rates_zero(self):
        for rand in range(1, 600, 7):
            with self.subTest(grow_price=rand):
                self.assertGreaterEqual(
                    leaf_rating_for(Decimal(rand)), LEAF_RATING_FLOOR
                )

    def test_the_floor_is_not_a_step_so_it_reads_as_below_swap_value(self):
        """The point of 0.1 rather than 0.5: it is distinguishable on sight
        wherever a rating is read, and it does not promote a R50 plant to the
        swap value of a R250 one."""
        self.assertNotEqual((LEAF_RATING_FLOOR * 2) % 1, 0)
        self.assertLess(LEAF_RATING_FLOOR, SWAP_MINIMUM_LEAF_RATING)


class EdgeTests(SimpleTestCase):
    def test_no_price_gives_no_rating(self):
        self.assertIsNone(leaf_rating_for(None))


class SwappabilityTests(SimpleTestCase):
    """A floored plant cannot be swapped, and the refusal says why.

    No database: `is_swappable` and `assert_swappable` read three fields on the
    row in front of them. `SwappableQueryTests` covers the queryset half.

    The codes matter more than the messages. The floor and `harvest.md`'s
    after-harvest rule are different refusals, and Block 10 has to tell a member
    which one it hit without matching on prose.
    """

    def plant(self, **overrides):
        return Plant(**{
            'status': PlantStatus.IN_BLOOM,
            'leaf_rating': Decimal('1.0'),
            'disabled_at': None,
        } | overrides)

    def test_a_rated_growing_plant_is_swappable(self):
        self.assertTrue(self.plant().is_swappable)
        self.plant().assert_swappable()

    def test_a_floored_plant_is_not_swappable(self):
        plant = self.plant(leaf_rating=LEAF_RATING_FLOOR)
        self.assertFalse(plant.is_swappable)
        with self.assertRaises(ValidationError) as caught:
            plant.assert_swappable()
        self.assertEqual(caught.exception.code, 'below_swap_value')

    def test_the_first_real_step_is_swappable(self):
        """0.5 is in, so the guard uses the threshold rather than rounding it."""
        self.assertTrue(self.plant(leaf_rating=Decimal('0.5')).is_swappable)

    def test_a_harvested_plant_is_refused_for_the_harvest_not_the_rating(self):
        plant = self.plant(status=PlantStatus.HARVESTED)
        self.assertFalse(plant.is_swappable)
        with self.assertRaises(ValidationError) as caught:
            plant.assert_swappable()
        self.assertEqual(caught.exception.code, 'not_flowering')

    def test_a_withdrawn_plant_is_refused_for_the_withdrawal(self):
        plant = self.plant(disabled_at=timezone.now())
        self.assertFalse(plant.is_swappable)
        with self.assertRaises(ValidationError) as caught:
            plant.assert_swappable()
        self.assertEqual(caught.exception.code, 'plant_disabled')


class SwappableQueryTests(PlantTestCase):
    """The queryset and the property must agree.

    Two implementations of one rule — one in SQL because Block 10 has to match
    plants of equal swap value in a `WHERE` clause, one in Python because a
    caller holds a plant rather than a queryset. The duplication is the same one
    `leaf_rating` itself is, and it earns a test that fails when only one side is
    edited.
    """

    def test_a_floored_plant_is_excluded(self):
        cheap = self.make_plant(
            cultivator_plant_id='POT-CHEAP',
            grow_price=Decimal('100.00'),
            status=PlantStatus.IN_BLOOM,
        )
        self.assertEqual(cheap.leaf_rating, LEAF_RATING_FLOOR)
        self.assertNotIn(cheap, Plant.objects.swappable())

    def test_a_rated_plant_is_included(self):
        plant = self.make_plant(status=PlantStatus.IN_BLOOM)
        self.assertIn(plant, Plant.objects.swappable())

    def test_the_queryset_and_the_property_agree(self):
        plants = [
            self.make_plant(
                cultivator_plant_id=f'POT-{i}',
                grow_price=price,
                status=status,
                # `harvested_plant_has_a_harvest_date` is a check constraint, so
                # a harvested row has to carry the date the constraint asks for.
                harvested_on=(
                    HARVESTS if status in HARVESTED_STATUSES else None
                ),
            )
            for i, (price, status) in enumerate((
                (Decimal('100.00'), PlantStatus.IN_BLOOM),
                (Decimal('249.99'), PlantStatus.PREFLOWERING),
                (Decimal('250.00'), PlantStatus.IN_BLOOM),
                (Decimal('950.00'), PlantStatus.HARVESTED),
                (Decimal('1900.00'), PlantStatus.PREFLOWERING),
            ))
        ]
        by_query = set(Plant.objects.swappable().values_list('pk', flat=True))
        by_property = {p.pk for p in plants if p.is_swappable}
        self.assertEqual(by_query, by_property)

    def test_a_withdrawn_plant_is_excluded_by_both(self):
        plant = self.make_plant(status=PlantStatus.IN_BLOOM)
        plant.disable()
        self.assertNotIn(plant, Plant.objects.swappable())
        self.assertFalse(plant.is_swappable)

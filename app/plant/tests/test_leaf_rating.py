"""The leaf rating, against the brief's own worked examples.

``twp-tasks/swap-zone.md`` gives five, and they are the specification: this is a
number members will trade against, so a formula that agrees with the prose but
not with the examples is wrong whatever the prose says.

The examples also matter because they are what catches a floating-point
implementation. In binary, ``0.85`` is not representable and Python's ``round``
uses banker's rounding — so a float version puts R1,250 at 1.0 rather than 1.5,
which is the one case the brief does *not* cover and therefore the one nobody
would notice.

C4 is the other half of this file: the leaf rating is swap value and has nothing
to do with reputation. There is no test here for a rating changing when a review
is left, because nothing should ever make it do so.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from ..models import leaf_rating_for


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

    def test_the_result_is_always_a_multiple_of_a_half(self):
        for rand in range(1, 4000, 37):
            with self.subTest(grow_price=rand):
                rating = leaf_rating_for(Decimal(rand))
                self.assertEqual((rating * 2) % 1, 0, f'{rating} is not a step')


class EdgeTests(SimpleTestCase):
    def test_no_price_gives_no_rating(self):
        self.assertIsNone(leaf_rating_for(None))

    def test_a_cheap_plant_can_rate_zero_which_is_an_open_question(self):
        """Recorded rather than asserted as desirable.

        The formula is `grow_price / 1000` to the nearest 0.5, so anything under
        R250 rounds to 0.0 — and a plant with a leaf rating of zero has no swap
        value at all, which in an equivalent-value trade means it matches
        nothing, or matches everything for free depending on how Block 10 reads
        it. `swap-zone.md` sets no floor and its cheapest example is R500.

        Left as the formula specifies rather than quietly given a minimum of
        0.5: inventing a floor here would settle a swap-zone rule in the wrong
        file. The test exists so the behaviour is known before Block 10 relies
        on it.
        """
        self.assertEqual(leaf_rating_for(Decimal('100')), Decimal('0.0'))
        self.assertEqual(leaf_rating_for(Decimal('249.99')), Decimal('0.0'))
        self.assertEqual(leaf_rating_for(Decimal('250')), Decimal('0.5'))

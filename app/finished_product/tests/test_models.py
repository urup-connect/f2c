"""What the product type catalogue guarantees.

Three things here fail invisibly if they break, which is what the whole suite is
written around.

A **negative price** would read as a credit to the member at harvest, and the
model validator is a form-level rule that a queryset ``.update()`` walks past --
so the check constraint is asserted against a raw update rather than through
``full_clean``, which is the only way to know it is really in the database.

A **duplicate code** would mean two rows answering to one machine key, and
whichever the upload template resolved first would silently win.

``requires_payment`` is what the Block 6 harvest flow will branch on. A property
that stops tracking ``price`` sends a member to a checkout for nothing, or lets
a priced type through free.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from ..models import FinishedProductType


class FinishedProductTypeTests(TestCase):
    def make(self, **overrides):
        fields = {'code': 'pre-roll', 'name': 'Pre-rolls'} | overrides
        return FinishedProductType.objects.create(**fields)

    def test_a_type_costs_nothing_unless_it_is_given_a_price(self):
        """Both launch types are free. `product-types.md`."""
        product_type = self.make()

        self.assertEqual(product_type.price, Decimal('0.00'))
        self.assertFalse(product_type.requires_payment)

    def test_requires_payment_follows_the_price(self):
        """The flag the harvest flow branches on is derived, never stored."""
        product_type = self.make(price=Decimal('45.00'))
        self.assertTrue(product_type.requires_payment)

        product_type.price = Decimal('0.00')
        self.assertFalse(product_type.requires_payment)

    def test_a_negative_price_is_refused_by_the_database(self):
        """Not only by the validator.

        A queryset `.update()` never runs a validator, so this is the assertion
        that matters: the rule has to be in the schema. On MySQL that needs
        8.0.16 or later -- before it, `CHECK` is parsed and discarded and this
        test passes on SQLite while the deployed database enforces nothing.
        """
        product_type = self.make()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinishedProductType.objects.filter(pk=product_type.pk).update(
                    price=Decimal('-1.00')
                )

    def test_a_negative_price_is_refused_by_validation_too(self):
        with self.assertRaises(ValidationError) as caught:
            FinishedProductType(
                code='loose', name='Loose', price=Decimal('-1.00')
            ).full_clean()

        self.assertIn('price', caught.exception.error_dict)

    def test_two_types_cannot_share_a_code(self):
        self.make()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FinishedProductType.objects.create(code='pre-roll', name='Pre-roll')

    def test_available_excludes_withdrawn_types(self):
        """Retirement is a flag. Nothing is deleted -- harvests point at it."""
        self.make()
        self.make(code='loose', name='Loose', is_available=False)

        self.assertEqual(
            [t.code for t in FinishedProductType.objects.available()], ['pre-roll']
        )

    def test_chargeable_finds_only_types_that_cost_something(self):
        self.make()
        self.make(code='edible', name='Edibles', price=Decimal('120.00'))

        self.assertEqual(
            [t.code for t in FinishedProductType.objects.chargeable()], ['edible']
        )

    def test_ordering_is_by_display_order_then_name(self):
        self.make(code='loose', name='Loose', display_order=2)
        self.make(display_order=1)
        self.make(code='edible', name='Edibles', display_order=1)

        self.assertEqual(
            [t.code for t in FinishedProductType.objects.all()],
            ['edible', 'pre-roll', 'loose'],
        )

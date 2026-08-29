"""Fixtures the catalogue's service and API tests both build on.

The accounts are the reason this exists. Every endpoint under ``/api/catalogue``
holds out for ``platform.manage_strain_catalogue``, which
``accounts.roles.permissions_for`` grants to the administrator role and refuses
to everybody else -- and it refuses an inactive account of *any* role, because
the permission set is empty for one. So a test of a permission needs three
accounts that differ in exactly one way each, and building them by hand in every
test case is how two of them end up differing in two ways.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.club.finished_product.models import FinishedProductType
from f2c.testing import make_administrator, make_cultivator, make_member

from ..models import (
    Aroma,
    CultivatorStrainListing,
    Effect,
    ListingStatus,
    Strain,
    StrainStatus,
    StrainType,
)

User = get_user_model()


class CatalogueTestCase(TestCase):
    """An administrator, a cultivator, a member, and a strain to act on."""

    def setUp(self):
        # Three accounts differing in exactly one way each: which relationship
        # they hold. Every account is Active, deliberately —
        # `permissions_for` empties the set for one that cannot sign in, so a
        # suspended administrator would be refused for the wrong reason and a
        # test asserting a 403 would pass without testing anything.
        self.admin = make_administrator('admin@example.com')
        # `self.cultivator` is the **producer**, which is what a listing points
        # at; `self.grower` is the person appointed to it.
        self.grower, self.cultivator = make_cultivator(
            'grower@example.com', trading_name='Kloof'
        )
        self.member = make_member('member@example.com', 'Thabo')

    def strain(self, name='OG Kush', **overrides):
        return Strain.objects.create(
            name=name,
            strain_type=overrides.pop('strain_type', StrainType.HYBRID),
            status=overrides.pop('status', StrainStatus.ACTIVE),
            **overrides,
        )

    def listing(self, strain, cultivator=None, **overrides):
        """One offer against ``strain``.

        ``full_clean`` is deliberately not called: several tests want a listing
        against a strain whose status would refuse one, so the fixture writes the
        row and each test asserts about the rule it is interested in.
        """
        return CultivatorStrainListing.objects.create(
            strain=strain,
            cultivator=cultivator or self.cultivator,
            status=overrides.pop('status', ListingStatus.LISTED),
            short_description=overrides.pop(
                'short_description', 'Grown slow, under glass.'
            ),
            default_grow_price=overrides.pop('default_grow_price', Decimal('950.00')),
            minimum_yield_grams=overrides.pop(
                'minimum_yield_grams', Decimal('30.00')
            ),
            **overrides,
        )

    def product_type(self, code='pre-roll', name='Pre-rolls', **overrides):
        return FinishedProductType.objects.create(code=code, name=name, **overrides)

    def aroma(self, name='Citrus', **overrides):
        return Aroma.objects.create(name=name, **overrides)

    def effect(self, name='Relaxing', **overrides):
        return Effect.objects.create(name=name, **overrides)

    def payload(self, **overrides):
        """A complete, acceptable ``StrainIn`` body.

        Every field present, because the endpoint is a replace and a test that
        sent a subset would be testing a shape the screen never produces.
        """
        return {
            'name': 'Durban Poison',
            'status': StrainStatus.ACTIVE,
            'strain_type': StrainType.SATIVA,
            'exclusive_to': None,
            'genetic_lineage': 'Durban landrace',
            'breeder_origin': 'KwaZulu-Natal',
            'description': 'A tall, quick sativa.',
            'thc_content': '18.50',
            'cbd_content': '0.30',
            'other_cannabinoids': {'CBG': 0.8},
            'terpene_profile': {'terpinolene': 0.6},
            'disease_resistance': {'botrytis': 'good'},
            'aromas': [],
            'effects': [],
            'flowering_time_weeks': 9,
            'preferred_growing_environment': 'outdoor',
            'difficulty_level': 'easy',
        } | overrides

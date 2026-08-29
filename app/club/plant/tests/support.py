"""Fixtures for the plant tests.

A plant needs a cultivator, a strain, a listing and a product type before it can
exist at all, which is the cost of the decision in ``models`` to point at a
listing rather than to duplicate the cultivator and the strain onto every row.
Worth it: the pair can never disagree, and C18's inheritance is free.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from f2c.testing import make_cultivator, make_member
from app.club.finished_product.models import FinishedProductType
from app.club.strains.models import (
    CultivatorStrainListing,
    ListingStatus,
    Strain,
    StrainStatus,
    StrainType,
)

from ..models import Plant, PlantStatus, allocate_serials

User = get_user_model()

PLANTED = date(2026, 3, 1)
BLOOMS = PLANTED + timedelta(days=60)
HARVESTS = PLANTED + timedelta(days=120)


class PlantTestCase(TestCase):
    """One cultivator, one strain, one listing, one product type."""

    def setUp(self):
        super().setUp()
        # `self.cultivator` is the **producer** now, not the person: stock
        # belongs to the farm, and `Batch.cultivator` and
        # `CultivatorStrainListing.cultivator` both point at it. `self.grower`
        # is the person appointed to it, for the tests that need a caller.
        self.grower, self.cultivator = make_cultivator(
            'grower@example.com', trading_name='Kloof'
        )
        self.member = make_member('member@example.com', 'Sam')
        self.strain = Strain.objects.create(
            name='OG Kush',
            strain_type=StrainType.HYBRID,
            status=StrainStatus.ACTIVE,
        )
        self.pre_roll = FinishedProductType.objects.create(
            code='pre-roll', name='Pre-rolls'
        )
        self.listing = CultivatorStrainListing.objects.create(
            cultivator=self.cultivator,
            strain=self.strain,
            status=ListingStatus.LISTED,
            short_description='Grown slow, under glass.',
            default_grow_price=Decimal('950.00'),
            minimum_yield_grams=Decimal('30.00'),
        )
        self.listing.finished_product_types.set([self.pre_roll])

    def make_plant(self, **overrides):
        """One plant, with a freshly allocated serial."""
        fields = {
            'serial': allocate_serials(1)[0],
            'cultivator_plant_id': 'POT-1',
            'listing': self.listing,
            'grow_price': Decimal('950.00'),
            'minimum_yield_grams': Decimal('30.00'),
            'planting_date': PLANTED,
            'estimated_bloom_date': BLOOMS,
            'estimated_harvest_date': HARVESTS,
            'status': PlantStatus.PREFLOWERING,
        } | overrides
        return Plant.objects.create(**fields)

    def another_member(self, email='other@example.com', nickname='Alex'):
        return make_member(email, nickname)

    def another_cultivator(self, trading_name='Tygerberg'):
        """A second farm, and the person appointed to it.

        Returns `(person, farm)`. Stock belongs to the farm — `Batch.cultivator`
        and `CultivatorStrainListing.cultivator` both point at it — so a test
        about one grower not reaching another's stock needs the farm, and a test
        about who is *calling* needs the person.
        """
        return make_cultivator(f'{trading_name.lower()}@example.com',
                               trading_name=trading_name)


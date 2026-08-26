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

from app.accounts.roles import UserRole
from app.finished_product.models import FinishedProductType
from app.strains.models import (
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
        self.cultivator = User.objects.create_user(
            email='grower@example.com', nickname='Kloof', role=UserRole.CULTIVATOR
        )
        self.member = User.objects.create_user(
            email='member@example.com', nickname='Sam'
        )
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
        return User.objects.create_user(email=email, nickname=nickname)

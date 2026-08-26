"""The admin form, because it is the only thing enforcing C18 at creation time.

``Model.clean`` cannot see a many-to-many on a row that does not exist yet, so
on the save that creates a listing the subset rule and the "a listed offer needs
a type" rule have nothing behind them but this form. That makes it load-bearing
rather than convenience, which is why it is tested directly.

The cultivator picker is tested for the same reason ``accounts``' admin tests
exist: a picker over every account in the club, on a screen where staff write
somebody's commercial terms or reserve a strain to them, is an invitation to pick
the wrong person -- and nothing about the rendered page would show it had
happened.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.accounts.roles import UserRole
from app.finished_product.models import FinishedProductType

from ..admin import CultivatorStrainListingForm
from ..models import ListingStatus, Strain, StrainStatus, StrainType

User = get_user_model()


class ListingFormTests(TestCase):
    def setUp(self):
        self.cultivator = User.objects.create_user(
            email='grower@example.com', nickname='Kloof', role=UserRole.CULTIVATOR
        )
        self.strain = Strain.objects.create(
            name='OG Kush',
            strain_type=StrainType.HYBRID,
            status=StrainStatus.ACTIVE,
        )
        self.pre_roll = FinishedProductType.objects.create(
            code='pre-roll', name='Pre-rolls'
        )
        self.withdrawn = FinishedProductType.objects.create(
            code='edible', name='Edibles', is_available=False
        )

    def payload(self, **overrides):
        return {
            'cultivator': str(self.cultivator.pk),
            'strain': str(self.strain.pk),
            'status': ListingStatus.LISTED,
            'short_description': 'Grown slow, under glass.',
            'description': '',
            'default_grow_price': Decimal('950.00'),
            'minimum_yield_grams': Decimal('30.00'),
            'finished_product_types': [str(self.pre_roll.pk)],
        } | overrides

    def test_a_complete_listed_offer_is_accepted(self):
        form = CultivatorStrainListingForm(data=self.payload())

        self.assertTrue(form.is_valid(), form.errors)

    def test_a_listed_offer_with_no_product_type_is_refused_on_creation(self):
        """The rule the model cannot check on a first save."""
        form = CultivatorStrainListingForm(
            data=self.payload(finished_product_types=[])
        )

        self.assertFalse(form.is_valid())
        self.assertIn('finished_product_types', form.errors)

    def test_a_withdrawn_product_type_cannot_be_offered(self):
        form = CultivatorStrainListingForm(
            data=self.payload(finished_product_types=[str(self.withdrawn.pk)])
        )

        self.assertFalse(form.is_valid())
        self.assertIn('finished_product_types', form.errors)

    def test_a_draft_needs_no_product_type(self):
        form = CultivatorStrainListingForm(
            data=self.payload(
                status=ListingStatus.DRAFT, finished_product_types=[]
            )
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_a_reserved_strain_is_refused_to_another_cultivator(self):
        """Through the form, since the model rule has to survive the admin path."""
        other = User.objects.create_user(
            email='other@example.com', nickname='Tygerberg',
            role=UserRole.CULTIVATOR,
        )
        self.strain.exclusive_to = other
        self.strain.save(update_fields=['exclusive_to'])

        form = CultivatorStrainListingForm(data=self.payload())

        self.assertFalse(form.is_valid())
        self.assertIn('strain', form.errors)


class CultivatorPickerTests(TestCase):
    def test_only_cultivators_are_offered(self):
        """A member, an administrator and an erased grower are all excluded."""
        from ..admin import cultivator_choices
        from ..models import CultivatorStrainListing

        grower = User.objects.create_user(
            email='grower@example.com', nickname='Kloof', role=UserRole.CULTIVATOR
        )
        User.objects.create_user(email='member@example.com', nickname='Sam')
        User.objects.create_user(
            email='boss@example.com', nickname='Boss', role=UserRole.ADMIN
        )
        gone = User.objects.create_user(
            email='gone@example.com', nickname='Gone', role=UserRole.CULTIVATOR
        )
        # Erasure leaves the role in place deliberately, so filtering on the
        # role alone would keep offering them.
        gone.soft_delete()

        field = CultivatorStrainListing._meta.get_field('cultivator')

        self.assertEqual(list(cultivator_choices(field)), [grower])

"""What the strain catalogue and the cultivators' listings guarantee.

The assertions worth naming, because each of them is a rule that fails quietly:

**The slug is the uniqueness key.** A plain unique index on ``name`` behaves
differently on MySQL, whose default collation is case-insensitive, and on the
SQLite this suite runs against, which is not. So "OG Kush" and "og kush" would
collide in production and both be accepted in development -- and the catalogue
would grow duplicates that nobody sees until two cultivators list against
different rows for the same plant. The slug folds case identically everywhere,
and these tests assert the fold rather than the index.

**Exclusivity is enforced by nothing in SQL.** ``Strain.exclusive_to`` is a
column on another table, which no check constraint can reach. ``clean`` is the
only thing standing between a reserved strain and another grower's listing, so
it is tested directly, and the gap -- a raw ``create`` walks past it -- is tested
too, so that nobody later mistakes the rule for a guarantee.

**The C18 subset rule is split across a model and a form**, because a
many-to-many is invisible to ``Model.clean`` until the row exists. Both routes
go through ``check_offered_types``, and both are exercised here.

**The status columns carry check constraints** for the same reason
``accounts.User.role`` does: ``browsable()`` filters on a value, so a row written
by a data migration with an unrecognised status simply stops appearing, with
nothing to explain why.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.accounts.roles import UserRole
from app.finished_product.models import FinishedProductType

from ..models import (
    Aroma,
    CultivatorStrainListing,
    Effect,
    ListingStatus,
    Strain,
    StrainStatus,
    StrainType,
    check_offered_types,
)

User = get_user_model()


def make_cultivator(email):
    return User.objects.create_user(
        email=email, nickname=email.split('@')[0], role=UserRole.CULTIVATOR
    )


def make_strain(name='OG Kush', **overrides):
    fields = {
        'name': name,
        'strain_type': StrainType.HYBRID,
        'status': StrainStatus.ACTIVE,
    } | overrides
    return Strain.objects.create(**fields)


def make_listing(cultivator, strain, **overrides):
    fields = {
        'cultivator': cultivator,
        'strain': strain,
        'short_description': 'Grown slow, under glass.',
        'default_grow_price': Decimal('950.00'),
        'minimum_yield_grams': Decimal('30.00'),
    } | overrides
    return CultivatorStrainListing.objects.create(**fields)


class StrainIdentityTests(TestCase):
    def test_the_slug_is_derived_from_the_name(self):
        self.assertEqual(make_strain('OG Kush').slug, 'og-kush')

    def test_the_slug_follows_a_renamed_strain(self):
        """Including on a partial save, which is where a derived key gets lost."""
        strain = make_strain('OG Kush')

        strain.name = 'Durban Poison'
        strain.save(update_fields=['name'])

        strain.refresh_from_db()
        self.assertEqual(strain.slug, 'durban-poison')

    def test_two_strains_cannot_share_a_name_whatever_the_case(self):
        """The rule the slug exists to make portable. See the module docstring."""
        make_strain('OG Kush')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_strain('og  kush')

    def test_an_unrecognised_status_is_refused_by_the_database(self):
        strain = make_strain()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Strain.objects.filter(pk=strain.pk).update(status='retired')

    def test_an_unrecognised_type_is_refused_by_the_database(self):
        strain = make_strain()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Strain.objects.filter(pk=strain.pk).update(strain_type='ruderalis')

    def test_a_cannabinoid_figure_above_a_hundred_is_refused(self):
        """A THC figure of 220 is a misplaced decimal point, not a strong plant."""
        strain = make_strain()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Strain.objects.filter(pk=strain.pk).update(
                    thc_content=Decimal('220.00')
                )

    def test_a_blank_cannabinoid_figure_is_allowed(self):
        """Unknown is a real answer, and the constraint has to permit it."""
        strain = make_strain(thc_content=None, cbd_content=None)

        strain.full_clean()
        self.assertIsNone(strain.thc_content)

    def test_the_json_profiles_default_to_empty(self):
        """No value required on insert. See the field comments."""
        strain = make_strain()

        self.assertEqual(strain.other_cannabinoids, {})
        self.assertEqual(strain.terpene_profile, {})
        self.assertEqual(strain.disease_resistance, {})

    def test_a_strain_carries_several_aromas_and_effects(self):
        """The reason these are lookup tables and not single choice columns."""
        strain = make_strain()
        strain.aromas.set([
            Aroma.objects.create(name='Earthy'),
            Aroma.objects.create(name='Citrus'),
        ])
        strain.effects.set([
            Effect.objects.create(name='Relaxing'),
            Effect.objects.create(name='Uplifting'),
        ])

        self.assertEqual(strain.aromas.count(), 2)
        self.assertEqual(strain.effects.count(), 2)

    def test_a_vocabulary_term_cannot_be_added_twice(self):
        Aroma.objects.create(name='Earthy')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Aroma.objects.create(name='earthy')

    def test_browsable_is_only_the_active_catalogue(self):
        make_strain('Active One')
        make_strain('Pending One', status=StrainStatus.PENDING)
        make_strain('Hidden One', status=StrainStatus.HIDDEN)
        make_strain('Retired One', status=StrainStatus.INACTIVE)

        self.assertEqual(
            [s.name for s in Strain.objects.browsable()], ['Active One']
        )


class StrainExclusivityTests(TestCase):
    def setUp(self):
        self.owner = make_cultivator('owner@example.com')
        self.other = make_cultivator('other@example.com')

    def test_a_strain_is_open_to_every_cultivator_by_default(self):
        strain = make_strain()

        self.assertFalse(strain.is_exclusive)
        self.assertTrue(strain.may_be_listed_by(self.other))

    def test_a_reserved_strain_admits_only_its_own_cultivator(self):
        strain = make_strain(exclusive_to=self.owner)

        self.assertTrue(strain.is_exclusive)
        self.assertTrue(strain.may_be_listed_by(self.owner))
        self.assertFalse(strain.may_be_listed_by(self.other))

    def test_listable_by_hides_another_growers_reserved_strain(self):
        """What the listing form's strain picker reads."""
        make_strain('Open One')
        make_strain('Mine', exclusive_to=self.owner)
        make_strain('Theirs', exclusive_to=self.other)

        self.assertEqual(
            sorted(s.name for s in Strain.objects.listable_by(self.owner)),
            ['Mine', 'Open One'],
        )

    def test_listable_by_excludes_strains_that_are_not_active(self):
        make_strain('Pending One', status=StrainStatus.PENDING)

        self.assertEqual(list(Strain.objects.listable_by(self.owner)), [])

    def test_another_cultivator_cannot_list_against_a_reserved_strain(self):
        strain = make_strain(exclusive_to=self.owner)
        listing = CultivatorStrainListing(
            cultivator=self.other,
            strain=strain,
            short_description='Mine now.',
            default_grow_price=Decimal('900.00'),
            minimum_yield_grams=Decimal('25.00'),
        )

        with self.assertRaises(ValidationError) as caught:
            listing.full_clean()

        self.assertEqual(
            caught.exception.error_dict['strain'][0].code, 'strain_is_exclusive'
        )

    def test_exclusivity_is_refused_even_on_a_draft(self):
        """Finding out at publication is finding out after the work is done."""
        strain = make_strain(exclusive_to=self.owner)
        listing = CultivatorStrainListing(
            cultivator=self.other,
            strain=strain,
            status=ListingStatus.DRAFT,
            default_grow_price=Decimal('900.00'),
            minimum_yield_grams=Decimal('25.00'),
        )

        with self.assertRaises(ValidationError) as caught:
            listing.full_clean()

        self.assertIn('strain', caught.exception.error_dict)

    def test_the_reserved_cultivator_may_list_against_their_own_strain(self):
        strain = make_strain(exclusive_to=self.owner)

        make_listing(self.owner, strain).full_clean()

    def test_nothing_in_the_database_enforces_exclusivity(self):
        """The gap, asserted so it is not mistaken for a guarantee.

        A cross-table rule cannot be a check constraint, so a raw ``create``
        writes a listing against another grower's reserved strain without
        complaint. Anything writing a listing outside the admin has to call
        ``full_clean`` -- which is why this belongs behind a service in Block 2.
        """
        strain = make_strain(exclusive_to=self.owner)

        listing = make_listing(self.other, strain)

        self.assertEqual(listing.strain.exclusive_to, self.owner)


class CultivatorStrainListingTests(TestCase):
    def setUp(self):
        self.cultivator = make_cultivator('grower@example.com')
        self.strain = make_strain()
        self.pre_roll = FinishedProductType.objects.create(
            code='pre-roll', name='Pre-rolls'
        )

    def test_a_cultivator_holds_one_listing_per_strain(self):
        make_listing(self.cultivator, self.strain)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_listing(self.cultivator, self.strain)

    def test_a_withdrawn_listing_still_occupies_the_pair(self):
        """Deliberate. Scoping the index to live rows needs a partial unique
        index, which MySQL cannot express and Django would silently drop."""
        make_listing(self.cultivator, self.strain, status=ListingStatus.WITHDRAWN)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_listing(self.cultivator, self.strain)

    def test_two_cultivators_may_offer_the_same_strain_on_different_terms(self):
        """The reason the commercial fields are not on `Strain`."""
        other = make_cultivator('other@example.com')

        make_listing(self.cultivator, self.strain, minimum_yield_grams=Decimal('30.00'))
        make_listing(other, self.strain, minimum_yield_grams=Decimal('45.00'))

        self.assertEqual(self.strain.listings.count(), 2)

    def test_a_free_grow_price_is_refused_by_the_database(self):
        listing = make_listing(self.cultivator, self.strain)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CultivatorStrainListing.objects.filter(pk=listing.pk).update(
                    default_grow_price=Decimal('0.00')
                )

    def test_a_zero_minimum_yield_is_refused_by_the_database(self):
        listing = make_listing(self.cultivator, self.strain)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CultivatorStrainListing.objects.filter(pk=listing.pk).update(
                    minimum_yield_grams=Decimal('0.00')
                )

    def test_a_listed_offer_cannot_be_written_without_a_short_description(self):
        """It is what a member reads beside the grower's name."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_listing(
                    self.cultivator,
                    self.strain,
                    status=ListingStatus.LISTED,
                    short_description='',
                )

    def test_a_draft_may_be_incomplete(self):
        make_listing(
            self.cultivator, self.strain, status=ListingStatus.DRAFT,
            short_description='',
        )

    def test_a_draft_is_allowed_against_a_strain_awaiting_curation(self):
        """A cultivator prepares the offer while the request sits in the queue."""
        pending = make_strain('New One', status=StrainStatus.PENDING)

        make_listing(
            self.cultivator, pending, status=ListingStatus.DRAFT
        ).full_clean()

    def test_a_listed_offer_against_an_unpublished_strain_is_refused(self):
        pending = make_strain('New One', status=StrainStatus.PENDING)
        listing = make_listing(self.cultivator, pending, status=ListingStatus.LISTED)

        with self.assertRaises(ValidationError) as caught:
            listing.full_clean()

        self.assertEqual(
            caught.exception.error_dict['strain'][0].code, 'strain_not_browsable'
        )

    def test_visible_needs_both_the_listing_and_the_strain_to_be_live(self):
        """Retiring a strain takes every offer against it off the shelf."""
        listed = make_listing(
            self.cultivator, self.strain, status=ListingStatus.LISTED
        )
        make_listing(
            self.cultivator,
            make_strain('Hidden One', status=StrainStatus.HIDDEN),
            status=ListingStatus.LISTED,
        )
        make_listing(
            self.cultivator, make_strain('Second'), status=ListingStatus.DRAFT
        )

        self.assertEqual(
            [row.pk for row in CultivatorStrainListing.objects.visible()],
            [listed.pk],
        )

    def test_the_string_form_shows_a_nickname_and_never_an_email_address(self):
        """Section 6.6 of `roles-and-permissions.md`. `__str__` reaches log entries."""
        listing = make_listing(self.cultivator, self.strain)

        self.assertIn('grower', str(listing))
        self.assertNotIn('@', str(listing))


class OfferedTypeTests(TestCase):
    """The C18 subset rule, through both routes that check it."""

    def setUp(self):
        self.cultivator = make_cultivator('grower@example.com')
        self.strain = make_strain()
        self.available = FinishedProductType.objects.create(
            code='pre-roll', name='Pre-rolls'
        )
        self.withdrawn = FinishedProductType.objects.create(
            code='edible', name='Edibles', is_available=False
        )

    def test_a_withdrawn_type_cannot_be_offered(self):
        error = check_offered_types(ListingStatus.DRAFT, [self.withdrawn])

        self.assertIsNotNone(error)
        self.assertEqual(error.code, 'type_not_available')

    def test_an_available_type_passes(self):
        self.assertIsNone(
            check_offered_types(ListingStatus.LISTED, [self.available])
        )

    def test_a_listed_offer_needs_at_least_one_type(self):
        """Without one a member buys a plant and has nothing to choose at harvest."""
        error = check_offered_types(ListingStatus.LISTED, [])

        self.assertIsNotNone(error)
        self.assertEqual(error.code, 'no_types')

    def test_a_draft_needs_none(self):
        self.assertIsNone(check_offered_types(ListingStatus.DRAFT, []))

    def test_the_model_checks_the_relation_once_the_row_exists(self):
        listing = make_listing(
            self.cultivator, self.strain, status=ListingStatus.LISTED
        )
        listing.finished_product_types.set([self.withdrawn])

        with self.assertRaises(ValidationError) as caught:
            listing.full_clean()

        self.assertIn('finished_product_types', caught.exception.error_dict)

    def test_the_model_cannot_see_the_relation_before_the_row_exists(self):
        """The gap the admin form closes, asserted so the split is on the record.

        An unsaved listing has no join rows to read, so ``clean`` passes a listed
        offer with no product type. Whatever writes a listing has to check the
        submitted set itself -- ``admin.CultivatorStrainListingForm`` does.
        """
        listing = CultivatorStrainListing(
            cultivator=self.cultivator,
            strain=self.strain,
            status=ListingStatus.LISTED,
            short_description='Grown slow.',
            default_grow_price=Decimal('950.00'),
            minimum_yield_grams=Decimal('30.00'),
        )

        listing.full_clean()

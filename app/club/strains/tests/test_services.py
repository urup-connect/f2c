"""The rules behind the catalogue endpoints.

Tested here rather than only through the API because these are the rules nothing
else enforces. Five of them exist only in ``strains.services`` -- the module
docstring lists them -- and for three of those the database will accept the row
happily:

* a second strain wearing an existing name reaches a unique index on a column
  ``full_clean`` does not validate, so without the check here it is a 500;
* ``exclusive_to`` is a foreign key to any account at all, so a strain can be
  reserved to a member;
* an aroma withdrawn from the vocabulary can be attached to a new strain.

The permission check is tested against every role rather than only against a
member, because ``permissions_for`` empties the set for an inactive account of
any role -- so "a cultivator is refused" and "a suspended administrator is
refused" are two different claims and only one of them is about the role.
"""
import uuid

from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from app.core.accounts.models import UserStatus

from .. import services
from ..models import Aroma, Effect, ListingStatus, Strain, StrainStatus, StrainType
from .support import CatalogueTestCase
from f2c.testing import make_producer


class PermissionTests(CatalogueTestCase):
    def test_an_administrator_may_read_the_catalogue(self):
        self.assertEqual(services.catalogue(self.admin).count(), 0)

    def test_a_cultivator_may_not(self):
        """The catalogue is administrator-curated. `member-roles.md` gives a
        cultivator a request, not a write -- and not this read either, which
        carries every grower's listing counts."""
        with self.assertRaises(PermissionDenied):
            services.catalogue(self.grower)

    def test_a_member_may_not(self):
        with self.assertRaises(PermissionDenied):
            services.catalogue(self.member)

    def test_a_suspended_administrator_may_not(self):
        """Not a claim about the role. `permissions_for` empties the set for an
        account that cannot sign in, so this passes through a different branch
        than the two above and would keep passing if the role were removed."""
        self.admin.status = UserStatus.SUSPENDED
        self.admin.save()

        with self.assertRaises(PermissionDenied):
            services.catalogue(self.admin)

    def test_every_write_asks_the_same_question(self):
        strain = self.strain()

        with self.assertRaises(PermissionDenied):
            services.create_strain(self.member, **self.writable())
        with self.assertRaises(PermissionDenied):
            services.update_strain(self.member, strain, **self.writable())
        with self.assertRaises(PermissionDenied):
            services.retire_strain(self.member, strain)
        with self.assertRaises(PermissionDenied):
            services.create_term(self.member, 'aromas', name='Gassy')

    def writable(self):
        """`self.payload` minus the two relations, which are keyword arguments."""
        fields = self.payload()
        fields.pop('aromas')
        fields.pop('effects')
        fields['exclusive_to'] = None
        fields['thc_content'] = Decimal('18.50')
        fields['cbd_content'] = Decimal('0.30')
        return fields


class ServiceWriteTestCase(CatalogueTestCase):
    """Shared shaping: the service takes model instances, not a request body."""

    def fields(self, **overrides):
        fields = self.payload(**overrides)
        fields.pop('aromas', None)
        fields.pop('effects', None)
        for money in ('thc_content', 'cbd_content'):
            if isinstance(fields.get(money), str):
                fields[money] = Decimal(fields[money])
        return fields

    def create(self, **overrides):
        aromas = overrides.pop('aromas', ())
        effects = overrides.pop('effects', ())
        return services.create_strain(
            self.admin, aromas=aromas, effects=effects, **self.fields(**overrides)
        )


class NameTests(ServiceWriteTestCase):
    def test_a_strain_is_created_with_its_slug_derived(self):
        strain = self.create(name='Durban Poison')

        self.assertEqual(strain.slug, 'durban-poison')

    def test_a_second_strain_with_the_same_name_is_refused(self):
        self.create(name='Durban Poison')

        with self.assertRaises(ValidationError) as refused:
            self.create(name='Durban Poison')

        self.assertIn('name', refused.exception.message_dict)

    def test_the_refusal_folds_case_and_spacing(self):
        """The index is on the slug, and `slugify` folds both. A plain unique
        index on `name` would behave differently on MySQL's case-insensitive
        default collation than on SQLite's case-sensitive one; this is the
        behaviour the derived column exists to guarantee."""
        self.create(name='Durban Poison')

        with self.assertRaises(ValidationError):
            self.create(name='durban  poison')

    def test_the_refusal_names_the_name_field(self):
        """Not `slug`. The index is on the slug and the administrator typed a
        name, so a refusal against a field that is not on the form is a refusal
        nothing can render."""
        self.create(name='Durban Poison')

        with self.assertRaises(ValidationError) as refused:
            self.create(name='Durban Poison')

        self.assertNotIn('slug', refused.exception.message_dict)

    def test_a_strain_may_keep_its_own_name_through_an_edit(self):
        strain = self.create(name='Durban Poison')

        services.update_strain(
            self.admin, strain, **self.fields(name='Durban Poison', description='Edited.')
        )

        strain.refresh_from_db()
        self.assertEqual(strain.description, 'Edited.')

    def test_a_name_with_no_letters_or_numbers_is_refused(self):
        """`slugify` produces an empty string, which would be a second strain
        keyed on '' the moment anybody did it twice."""
        with self.assertRaises(ValidationError) as refused:
            self.create(name='---')

        self.assertIn('name', refused.exception.message_dict)

    def test_a_blank_name_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.create(name='   ')

        self.assertIn('name', refused.exception.message_dict)

    def test_a_name_is_trimmed(self):
        strain = self.create(name='  Cheese  ')

        self.assertEqual(strain.name, 'Cheese')


class ExclusivityTests(ServiceWriteTestCase):
    def test_a_strain_may_be_reserved_to_a_cultivator(self):
        strain = self.create(exclusive_to=self.cultivator)

        self.assertEqual(strain.exclusive_to_id, self.cultivator.pk)

    def test_a_strain_may_be_reserved_to_nobody(self):
        strain = self.create(exclusive_to=None)

        self.assertIsNone(strain.exclusive_to_id)
        self.assertFalse(strain.is_exclusive)

    def test_a_strain_may_not_be_reserved_to_a_member(self):
        """The column is a foreign key to any account, so nothing in SQL refuses
        this. The Django admin narrows its picker, which governs one screen."""
        with self.assertRaises(ValidationError) as refused:
            self.create(exclusive_to=self.member)

        self.assertIn('exclusive_to', refused.exception.message_dict)

    def test_a_strain_may_not_be_reserved_to_an_administrator(self):
        with self.assertRaises(ValidationError):
            self.create(exclusive_to=self.admin)

    def test_a_strain_may_be_reserved_to_any_producer(self):
        """**The departure rule is gone, and this records that rather than
        deleting the test.**

        It used to refuse a cultivator who had left, by erasing their account.
        Exclusivity points at a `Producer` now — an organisation, which is not
        erased and has no departure state — so there is nothing to refuse. The
        rule it enforced is real and wants a producer lifecycle to hang on;
        `_validated_exclusive_to` and `todo.md` both say so.
        """
        strain = self.create(exclusive_to=self.cultivator)

        self.assertEqual(strain.exclusive_to, self.cultivator)

    def test_a_strain_may_not_be_reserved_to_nothing(self):
        """What the check does still refuse."""
        with self.assertRaises(ValidationError):
            self.create(exclusive_to=uuid.uuid4())


class VocabularyAttachmentTests(ServiceWriteTestCase):
    def setUp(self):
        super().setUp()
        self.citrus = self.aroma('Citrus')
        self.relaxing = self.effect('Relaxing')

    def test_terms_are_attached(self):
        strain = self.create(aromas=[self.citrus.pk], effects=[self.relaxing.pk])

        self.assertEqual([term.name for term in strain.aromas.all()], ['Citrus'])
        self.assertEqual([term.name for term in strain.effects.all()], ['Relaxing'])

    def test_an_edit_replaces_rather_than_adds(self):
        pungent = self.aroma('Pungent')
        strain = self.create(aromas=[self.citrus.pk])

        services.update_strain(
            self.admin, strain, aromas=[pungent.pk], **self.fields()
        )

        self.assertEqual([term.name for term in strain.aromas.all()], ['Pungent'])

    def test_a_withdrawn_term_may_not_be_added_to_a_new_strain(self):
        """The field's help text is the specification: 'Clear this to stop
        offering the term on new strains.'"""
        retired = self.aroma('Gassy', is_available=False)

        with self.assertRaises(ValidationError) as refused:
            self.create(aromas=[retired.pk])

        self.assertIn('aromas', refused.exception.message_dict)

    def test_a_strain_already_carrying_a_withdrawn_term_keeps_it(self):
        """The other half of the same sentence: 'Existing strains keep it.' The
        rule is about a change rather than a state, which is why no constraint
        can hold it."""
        gassy = self.aroma('Gassy')
        strain = self.create(aromas=[gassy.pk])

        gassy.is_available = False
        gassy.save()

        services.update_strain(
            self.admin, strain, aromas=[gassy.pk], **self.fields(description='Edited.')
        )

        strain.refresh_from_db()
        self.assertEqual(strain.description, 'Edited.')
        self.assertEqual([term.name for term in strain.aromas.all()], ['Gassy'])

    def test_an_unknown_term_id_is_refused_rather_than_dropped(self):
        """Silently dropping it would save a strain with fewer terms than the
        caller asked for and report success."""
        with self.assertRaises(ValidationError) as refused:
            self.create(aromas=[self.relaxing.pk])  # an Effect id, in the aroma list

        self.assertIn('aromas', refused.exception.message_dict)


class JsonColumnTests(ServiceWriteTestCase):
    def test_a_mapping_is_stored_as_given(self):
        strain = self.create(terpene_profile={'myrcene': 0.5, 'limonene': 0.2})

        strain.refresh_from_db()
        self.assertEqual(strain.terpene_profile, {'myrcene': 0.5, 'limonene': 0.2})

    def test_a_string_value_is_kept_a_string(self):
        """`{"CBG": 0.8}` and `{"botrytis": "good"}` are both things these
        columns are for, and the model's help text quotes the first."""
        strain = self.create(disease_resistance={'botrytis': 'good'})

        strain.refresh_from_db()
        self.assertEqual(strain.disease_resistance, {'botrytis': 'good'})

    def test_too_many_entries_are_refused(self):
        too_many = {f'terpene-{index}': 0.1 for index in range(services.MAX_JSON_KEYS + 1)}

        with self.assertRaises(ValidationError) as refused:
            self.create(terpene_profile=too_many)

        self.assertIn('terpene_profile', refused.exception.message_dict)

    def test_a_long_key_is_refused(self):
        long_key = 'x' * (services.MAX_JSON_KEY_LENGTH + 1)

        with self.assertRaises(ValidationError) as refused:
            self.create(other_cannabinoids={long_key: 1})

        self.assertIn('other_cannabinoids', refused.exception.message_dict)

    def test_a_long_value_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.create(
                disease_resistance={
                    'botrytis': 'y' * (services.MAX_JSON_VALUE_LENGTH + 1)
                }
            )

        self.assertIn('disease_resistance', refused.exception.message_dict)

    def test_a_blank_key_is_refused(self):
        with self.assertRaises(ValidationError):
            self.create(terpene_profile={'  ': 0.5})

    def test_an_emptied_column_is_saved_empty(self):
        """The reason the write is a replace rather than a patch: a cleared JSON
        column must not quietly survive the save that cleared it."""
        strain = self.create(terpene_profile={'myrcene': 0.5})

        services.update_strain(self.admin, strain, **self.fields(terpene_profile={}))

        strain.refresh_from_db()
        self.assertEqual(strain.terpene_profile, {})


class ModelRuleTests(ServiceWriteTestCase):
    """The rules `full_clean` contributes, so the service is not restating them."""

    def test_a_percentage_over_a_hundred_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.create(thc_content=Decimal('220.00'))

        self.assertIn('thc_content', refused.exception.message_dict)

    def test_an_unknown_status_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.create(status='retired')

        self.assertIn('status', refused.exception.message_dict)

    def test_an_unknown_strain_type_is_refused(self):
        with self.assertRaises(ValidationError):
            self.create(strain_type='ruderalis')

    def test_a_flowering_time_beyond_a_year_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            self.create(flowering_time_weeks=60)

        self.assertIn('flowering_time_weeks', refused.exception.message_dict)

    def test_several_refusals_arrive_together(self):
        """An administrator who mistyped two fields should be told about both,
        not told the first and then the second on the next attempt."""
        self.create(name='Durban Poison')

        with self.assertRaises(ValidationError) as refused:
            self.create(name='Durban Poison', thc_content=Decimal('220.00'))

        self.assertEqual(
            sorted(refused.exception.message_dict), ['name', 'thc_content']
        )

    def test_a_refused_write_changes_nothing(self):
        """Everything is validated before anything is saved, inside one
        transaction, so a half-applied edit is not a state that exists."""
        strain = self.create(name='Cheese', description='Original.')
        citrus = self.aroma('Citrus')

        with self.assertRaises(ValidationError):
            services.update_strain(
                self.admin,
                strain,
                aromas=[citrus.pk],
                **self.fields(name='Cheese', description='Edited.', thc_content=Decimal('220')),
            )

        strain.refresh_from_db()
        self.assertEqual(strain.description, 'Original.')
        self.assertEqual(strain.aromas.count(), 0)


class RetirementTests(ServiceWriteTestCase):
    def test_retiring_sets_the_status_and_leaves_the_row(self):
        strain = self.create()

        services.retire_strain(self.admin, strain)

        strain.refresh_from_db()
        self.assertEqual(strain.status, StrainStatus.INACTIVE)
        self.assertTrue(Strain.objects.filter(pk=strain.pk).exists())

    def test_a_retired_strain_leaves_the_browsable_catalogue(self):
        strain = self.create()

        services.retire_strain(self.admin, strain)

        self.assertFalse(Strain.objects.browsable().filter(pk=strain.pk).exists())

    def test_it_reports_how_many_live_offers_came_down(self):
        strain = self.create()
        self.listing(strain, status=ListingStatus.LISTED)
        self.listing(
            strain,
            cultivator=make_producer('Dale'),
            status=ListingStatus.WITHDRAWN,
        )

        _, taken_down = services.retire_strain(self.admin, strain)

        self.assertEqual(taken_down, 1)

    def test_the_listings_themselves_are_untouched(self):
        """A withdrawn listing is a grower's own decision; this is the club
        retiring the strain underneath them. Overwriting each listing's status
        would erase the difference and leave nothing to reinstate."""
        strain = self.create()
        listing = self.listing(strain, status=ListingStatus.LISTED)

        services.retire_strain(self.admin, strain)

        listing.refresh_from_db()
        self.assertEqual(listing.status, ListingStatus.LISTED)

    def test_a_retired_strain_takes_every_offer_off_the_shelf(self):
        strain = self.create()
        listing = self.listing(strain, status=ListingStatus.LISTED)

        services.retire_strain(self.admin, strain)

        self.assertFalse(
            type(listing).objects.visible().filter(pk=listing.pk).exists()
        )

    def test_retiring_twice_is_a_no_op(self):
        strain = self.create()
        self.listing(strain, status=ListingStatus.LISTED)
        services.retire_strain(self.admin, strain)

        _, taken_down = services.retire_strain(self.admin, strain)

        self.assertEqual(taken_down, 0)

    def test_a_retired_strain_can_be_reinstated_through_an_edit(self):
        """The reason retirement needs no undo endpoint of its own: the status
        is a field on the form."""
        strain = self.create()
        services.retire_strain(self.admin, strain)

        services.update_strain(
            self.admin, strain, **self.fields(status=StrainStatus.ACTIVE)
        )

        strain.refresh_from_db()
        self.assertEqual(strain.status, StrainStatus.ACTIVE)


class CatalogueReadTests(ServiceWriteTestCase):
    def setUp(self):
        super().setUp()
        self.kush = self.create(
            name='OG Kush', strain_type=StrainType.HYBRID, breeder_origin='Unknown'
        )
        self.poison = self.create(
            name='Durban Poison',
            strain_type=StrainType.SATIVA,
            status=StrainStatus.PENDING,
            breeder_origin='KwaZulu-Natal',
        )

    def names(self, **filters):
        return [strain.name for strain in services.catalogue(self.admin, **filters)]

    def test_it_returns_the_whole_catalogue_in_name_order(self):
        self.assertEqual(self.names(), ['Durban Poison', 'OG Kush'])

    def test_it_narrows_by_status(self):
        self.assertEqual(self.names(status=StrainStatus.PENDING), ['Durban Poison'])

    def test_it_narrows_by_type(self):
        self.assertEqual(self.names(strain_type=StrainType.HYBRID), ['OG Kush'])

    def test_it_searches_the_name(self):
        self.assertEqual(self.names(search='kush'), ['OG Kush'])

    def test_it_searches_the_breeder(self):
        self.assertEqual(self.names(search='kwazulu'), ['Durban Poison'])

    def test_a_blank_filter_narrows_nothing(self):
        """A `select` reset to 'any' submits an empty string, so blank and
        absent have to mean the same thing."""
        self.assertEqual(len(self.names(status='', strain_type='', search='  ')), 2)

    def test_each_row_carries_both_listing_counts(self):
        self.listing(self.kush, status=ListingStatus.LISTED)
        self.listing(
            self.kush,
            cultivator=make_producer('Dale'),
            status=ListingStatus.WITHDRAWN,
        )

        row = next(
            strain for strain in services.catalogue(self.admin) if strain.pk == self.kush.pk
        )

        self.assertEqual(row.listing_live, 1)
        self.assertEqual(row.listing_total, 2)

    def test_the_counts_do_not_multiply_each_other(self):
        """Two aggregates over one relation in one query multiply each other's
        rows without `distinct=True`."""
        for index in range(3):
            self.listing(
                self.kush,
                cultivator=make_producer(f'Farm{index}'),
                status=ListingStatus.LISTED,
            )

        row = next(
            strain for strain in services.catalogue(self.admin) if strain.pk == self.kush.pk
        )

        self.assertEqual(row.listing_live, 3)
        self.assertEqual(row.listing_total, 3)


class StrainDetailTests(ServiceWriteTestCase):
    def test_it_carries_the_offers_against_the_strain(self):
        strain = self.create()
        self.listing(strain)

        detail = services.strain_detail(self.admin, strain.pk)

        self.assertEqual(len(detail.listings.all()), 1)

    def test_each_offer_carries_how_many_plants_are_behind_it(self):
        """`Plant.listing` is PROTECT, so a listing with plants behind it can
        never go away -- and a strain behind that listing is permanent too. An
        administrator about to retire a strain should be told before, not after."""
        strain = self.create()
        self.listing(strain)

        detail = services.strain_detail(self.admin, strain.pk)

        self.assertEqual(detail.listings.all()[0].plant_count, 0)

    def test_an_unknown_id_raises_does_not_exist(self):
        with self.assertRaises(Strain.DoesNotExist):
            services.strain_detail(self.admin, '00000000-0000-7000-8000-000000000000')


class TermTests(CatalogueTestCase):
    def test_a_term_is_created_with_its_slug_derived(self):
        term = services.create_term(self.admin, 'aromas', name='Gassy')

        self.assertEqual(term.slug, 'gassy')
        self.assertTrue(term.is_available)

    def test_effects_go_to_the_other_table(self):
        services.create_term(self.admin, 'effects', name='Uplifting')

        self.assertEqual(Effect.objects.count(), 1)
        self.assertEqual(Aroma.objects.count(), 0)

    def test_an_unknown_list_raises_a_key_error(self):
        """Turned into a 404 by the endpoint: a path naming a list that does not
        exist is a path with nothing behind it."""
        with self.assertRaises(KeyError):
            services.create_term(self.admin, 'flavours', name='Sweet')

    def test_a_duplicate_term_is_refused(self):
        services.create_term(self.admin, 'aromas', name='Citrus')

        with self.assertRaises(ValidationError) as refused:
            services.create_term(self.admin, 'aromas', name='citrus')

        self.assertIn('name', refused.exception.message_dict)

    def test_the_same_name_may_exist_in_both_lists(self):
        """Two tables, two vocabularies. 'Earthy' as an aroma and as an effect is
        two different terms, and the unique index is per table."""
        services.create_term(self.admin, 'aromas', name='Earthy')
        services.create_term(self.admin, 'effects', name='Earthy')

        self.assertEqual(Aroma.objects.count(), 1)
        self.assertEqual(Effect.objects.count(), 1)

    def test_a_rename_takes_the_slug_with_it(self):
        term = self.aroma('Citrus')

        renamed = services.update_term(
            self.admin, 'aromas', term.pk, name='Citrusy', is_available=True
        )

        self.assertEqual(renamed.slug, 'citrusy')

    def test_a_rename_onto_an_existing_term_is_refused(self):
        self.aroma('Citrusy')
        term = self.aroma('Citrus')

        with self.assertRaises(ValidationError):
            services.update_term(
                self.admin, 'aromas', term.pk, name='Citrusy', is_available=True
            )

    def test_a_term_may_keep_its_own_name_through_a_withdrawal(self):
        term = self.aroma('Citrus')

        withdrawn = services.update_term(
            self.admin, 'aromas', term.pk, name='Citrus', is_available=False
        )

        self.assertFalse(withdrawn.is_available)

    def test_a_withdrawn_term_keeps_its_row_and_its_strains(self):
        """Deleting an Aroma would silently remove it from every strain that
        used it, with nothing to say it had happened."""
        term = self.aroma('Citrus')
        strain = self.strain()
        strain.aromas.add(term)

        services.update_term(
            self.admin, 'aromas', term.pk, name='Citrus', is_available=False
        )

        self.assertEqual(strain.aromas.count(), 1)

    def test_a_blank_name_is_refused(self):
        with self.assertRaises(ValidationError):
            services.create_term(self.admin, 'aromas', name='   ')

    def test_vocabularies_carry_a_strain_count(self):
        term = self.aroma('Citrus')
        strain = self.strain()
        strain.aromas.add(term)

        lists = services.vocabularies(self.admin)

        self.assertEqual(list(lists['aromas'])[0].strain_count, 1)

    def test_vocabularies_include_withdrawn_terms(self):
        """An administrator managing the list has to see what is in it,
        including what has been withdrawn -- otherwise a withdrawal is
        irreversible from the screen that made it."""
        self.aroma('Gassy', is_available=False)

        lists = services.vocabularies(self.admin)

        self.assertEqual(len(list(lists['aromas'])), 1)

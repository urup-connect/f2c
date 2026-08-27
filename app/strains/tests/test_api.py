"""Tests for the catalogue endpoints.

The rules themselves are tested in ``test_services``. What is tested here is
what the router adds and nothing else: the status code each outcome becomes, the
shape of each payload, and the four things a screen would break on if they were
wrong.

1. **A ``Decimal`` crosses the wire as a string.** ``thc_content`` and a
   listing's ``default_grow_price`` are ``DECIMAL`` columns, and a float cannot
   hold two decimal places exactly. Asserted rather than assumed, because
   nothing in the schema *says* string -- it is a property of how django-ninja
   serialises ``Decimal``, and a change to it would round money silently.
2. **403 rather than 404 for a caller without the permission.** Both would keep
   a member out; only one of them is honest about why.
3. **A create and a read answer the same shape.** The screen has one renderer.
4. **Every write is authenticated *and* CSRF-checked**, because django-ninja's
   cookie auth enforces CSRF on unsafe methods and the frontend's `apiFetch`
   depends on it.
"""
import json
from decimal import Decimal

from app.accounts.roles import UserRole

from ..models import ListingStatus, Strain, StrainStatus, StrainType
from .support import CatalogueTestCase

CATALOGUE = '/api/catalogue/strains'
TERMS = '/api/catalogue/terms'


class ApiTestCase(CatalogueTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def body(self, response):
        return json.loads(response.content)

    def post(self, path, payload):
        return self.client.post(
            path, data=json.dumps(payload), content_type='application/json'
        )

    def put(self, path, payload):
        return self.client.put(
            path, data=json.dumps(payload), content_type='application/json'
        )

    def created(self, **overrides):
        """A strain created through the endpoint, as the payload it answered with."""
        response = self.post(CATALOGUE, self.payload(**overrides))
        self.assertEqual(response.status_code, 201, response.content)
        return self.body(response)


class PermissionTests(ApiTestCase):
    def test_an_administrator_may_list_the_catalogue(self):
        self.assertEqual(self.client.get(CATALOGUE).status_code, 200)

    def test_a_member_is_refused_with_403(self):
        """Not 404. Hiding the existence of a strain from somebody who may not
        manage it buys nothing -- every member browses the catalogue in Block 5."""
        self.client.force_login(self.member)

        self.assertEqual(self.client.get(CATALOGUE).status_code, 403)

    def test_a_cultivator_is_refused(self):
        self.client.force_login(self.cultivator)

        self.assertEqual(self.client.get(CATALOGUE).status_code, 403)

    def test_a_visitor_with_no_session_is_refused_with_401(self):
        """The API's default is `django_auth` and nothing here opts out, so this
        is the router's own answer rather than the service's."""
        self.client.logout()

        self.assertEqual(self.client.get(CATALOGUE).status_code, 401)

    def test_a_member_may_not_write(self):
        strain = self.strain()
        self.client.force_login(self.member)

        self.assertEqual(self.post(CATALOGUE, self.payload()).status_code, 403)
        self.assertEqual(
            self.put(f'{CATALOGUE}/{strain.pk}', self.payload()).status_code, 403
        )
        self.assertEqual(
            self.client.post(f'{CATALOGUE}/{strain.pk}/retire').status_code, 403
        )
        self.assertEqual(
            self.post(f'{TERMS}/aromas', {'name': 'Gassy'}).status_code, 403
        )


class ListTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.kush = self.strain('OG Kush', strain_type=StrainType.HYBRID)
        self.poison = self.strain(
            'Durban Poison',
            strain_type=StrainType.SATIVA,
            status=StrainStatus.PENDING,
        )

    def rows(self, query=''):
        response = self.client.get(f'{CATALOGUE}{query}')
        self.assertEqual(response.status_code, 200, response.content)
        return self.body(response)

    def test_it_lists_every_strain_in_name_order(self):
        self.assertEqual(
            [row['name'] for row in self.rows()], ['Durban Poison', 'OG Kush']
        )

    def test_each_row_carries_what_the_list_screen_draws(self):
        row = next(row for row in self.rows() if row['name'] == 'OG Kush')

        self.assertEqual(
            sorted(row),
            [
                'id',
                'listings_live',
                'listings_total',
                'name',
                'reserved_to',
                'slug',
                'status',
                'strain_type',
                'updated_at',
            ],
        )

    def test_a_row_carries_no_description_and_no_json(self):
        """The list is meant to be scanned. Two hundred strains each carrying
        three free-form JSON objects is a payload nobody reads."""
        row = self.rows()[0]

        self.assertNotIn('description', row)
        self.assertNotIn('terpene_profile', row)
        self.assertNotIn('listings', row)

    def test_reserved_to_is_a_display_name(self):
        """Section 6.6 of `roles-and-permissions.md`: never a legal name or an
        email address, in any payload."""
        self.kush.exclusive_to = self.cultivator
        self.kush.save()

        row = next(row for row in self.rows() if row['name'] == 'OG Kush')

        self.assertEqual(row['reserved_to'], self.cultivator.display_name)
        self.assertNotIn(self.cultivator.email, json.dumps(row))

    def test_reserved_to_is_null_for_the_normal_case(self):
        row = next(row for row in self.rows() if row['name'] == 'OG Kush')

        self.assertIsNone(row['reserved_to'])

    def test_it_narrows_by_status(self):
        rows = self.rows(f'?status={StrainStatus.PENDING}')

        self.assertEqual([row['name'] for row in rows], ['Durban Poison'])

    def test_it_narrows_by_type(self):
        rows = self.rows(f'?strain_type={StrainType.HYBRID}')

        self.assertEqual([row['name'] for row in rows], ['OG Kush'])

    def test_it_searches(self):
        self.assertEqual([row['name'] for row in self.rows('?search=kush')], ['OG Kush'])

    def test_a_blank_filter_narrows_nothing(self):
        self.assertEqual(len(self.rows('?status=&strain_type=&search=')), 2)

    def test_the_counts_are_on_every_row(self):
        self.listing(self.kush, status=ListingStatus.LISTED)
        self.listing(
            self.kush,
            cultivator=self.account('two@example.com', 'Dale', UserRole.CULTIVATOR),
            status=ListingStatus.WITHDRAWN,
        )

        row = next(row for row in self.rows() if row['name'] == 'OG Kush')

        self.assertEqual(row['listings_live'], 1)
        self.assertEqual(row['listings_total'], 2)


class CreateTests(ApiTestCase):
    def test_it_answers_201_with_the_record_as_stored(self):
        payload = self.created(name='Durban Poison')

        self.assertEqual(payload['name'], 'Durban Poison')
        self.assertEqual(payload['slug'], 'durban-poison')

    def test_the_record_is_read_back_rather_than_echoed(self):
        """A create and a read answer the same shape, so the screen has one
        renderer rather than two."""
        created = self.created()
        read = self.body(self.client.get(f'{CATALOGUE}/{created["id"]}'))

        self.assertEqual(created, read)

    def test_a_percentage_crosses_the_wire_as_a_string(self):
        """A DECIMAL column, and a float cannot hold 18.50 exactly. The frontend
        types these as strings and never does arithmetic on one."""
        payload = self.created(thc_content='18.50')

        self.assertEqual(payload['thc_content'], '18.50')

    def test_a_blank_percentage_is_null_rather_than_zero(self):
        """Zero THC is a fact about a plant; unknown is the absence of one, and
        a screen showing 0.00 for an unmeasured strain would be stating the
        first."""
        payload = self.created(thc_content=None, cbd_content=None)

        self.assertIsNone(payload['thc_content'])
        self.assertIsNone(payload['cbd_content'])

    def test_the_json_columns_survive_the_round_trip(self):
        payload = self.created(
            other_cannabinoids={'CBG': 0.8}, disease_resistance={'botrytis': 'good'}
        )

        self.assertEqual(payload['other_cannabinoids'], {'CBG': 0.8})
        self.assertEqual(payload['disease_resistance'], {'botrytis': 'good'})

    def test_terms_are_attached_by_id(self):
        citrus = self.aroma('Citrus')
        relaxing = self.effect('Relaxing')

        payload = self.created(aromas=[str(citrus.pk)], effects=[str(relaxing.pk)])

        self.assertEqual([term['name'] for term in payload['aromas']], ['Citrus'])
        self.assertEqual([term['name'] for term in payload['effects']], ['Relaxing'])

    def test_a_new_strain_has_no_listings(self):
        self.assertEqual(self.created()['listings'], [])

    def test_a_duplicate_name_is_refused_with_422_against_the_name(self):
        self.created(name='Durban Poison')

        response = self.post(CATALOGUE, self.payload(name='Durban Poison'))

        self.assertEqual(response.status_code, 422)
        self.assertIn('name', self.body(response)['fields'])

    def test_a_refusal_carries_a_sentence_as_well_as_the_fields(self):
        """`detail` is for a caller reading the endpoint directly; `fields` is
        what the form marks up against each input."""
        self.created(name='Durban Poison')

        body = self.body(self.post(CATALOGUE, self.payload(name='Durban Poison')))

        self.assertTrue(body['detail'])

    def test_reserving_to_a_member_is_refused(self):
        response = self.post(
            CATALOGUE, self.payload(exclusive_to=str(self.member.pk))
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn('exclusive_to', self.body(response)['fields'])

    def test_an_unknown_status_is_refused(self):
        response = self.post(CATALOGUE, self.payload(status='retired'))

        self.assertEqual(response.status_code, 422)

    def test_a_malformed_body_is_refused_by_the_schema(self):
        """422 from django-ninja rather than from the service: `aromas` is typed
        as a list of UUIDs, so a string never reaches `_validated_terms`."""
        response = self.post(CATALOGUE, self.payload(aromas='citrus'))

        self.assertEqual(response.status_code, 422)

    def test_nothing_is_created_when_the_write_is_refused(self):
        self.post(CATALOGUE, self.payload(name='   '))

        self.assertEqual(Strain.objects.count(), 0)


class ReadTests(ApiTestCase):
    def test_it_carries_the_whole_record(self):
        strain = self.strain()

        payload = self.body(self.client.get(f'{CATALOGUE}/{strain.pk}'))

        for field in (
            'genetic_lineage',
            'breeder_origin',
            'description',
            'other_cannabinoids',
            'terpene_profile',
            'disease_resistance',
            'aromas',
            'effects',
            'listings',
            'created_at',
            'updated_at',
        ):
            self.assertIn(field, payload)

    def test_exclusive_to_is_sent_as_an_id_and_as_a_name(self):
        """The picker is set from the id and the screen shows the name. Having
        the screen look the name up from a list it also holds would break the
        moment a reserved cultivator was not in that list."""
        strain = self.strain(exclusive_to=self.cultivator)

        payload = self.body(self.client.get(f'{CATALOGUE}/{strain.pk}'))

        self.assertEqual(payload['exclusive_to'], str(self.cultivator.pk))
        self.assertEqual(payload['reserved_to'], self.cultivator.display_name)

    def test_an_unknown_id_is_a_404(self):
        response = self.client.get(f'{CATALOGUE}/00000000-0000-7000-8000-000000000000')

        self.assertEqual(response.status_code, 404)

    def test_a_malformed_id_is_not_a_500(self):
        """The path converter refuses it before the view runs."""
        self.assertEqual(self.client.get(f'{CATALOGUE}/not-a-uuid').status_code, 404)

    def test_a_strain_carrying_a_withdrawn_term_still_reports_it(self):
        """The picker's list is the offerable vocabulary and does not have to
        contain a retired term, so the strain has to carry the whole term rather
        than an id the screen would fail to resolve."""
        gassy = self.aroma('Gassy', is_available=False)
        strain = self.strain()
        strain.aromas.add(gassy)

        payload = self.body(self.client.get(f'{CATALOGUE}/{strain.pk}'))

        self.assertEqual(payload['aromas'][0]['name'], 'Gassy')
        self.assertFalse(payload['aromas'][0]['is_available'])


class ListingsInDetailTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.subject = self.strain()
        self.offer = self.listing(self.subject)
        self.offer.finished_product_types.add(self.product_type())

    def listings(self):
        payload = self.body(self.client.get(f'{CATALOGUE}/{self.subject.pk}'))
        return payload['listings']

    def test_the_offers_come_down_with_the_strain(self):
        """Read-only, and in the same payload: the edit screen shows them every
        time, so a second round trip would buy nothing."""
        self.assertEqual(len(self.listings()), 1)

    def test_an_offer_names_the_cultivator_by_display_name(self):
        entry = self.listings()[0]

        self.assertEqual(entry['cultivator'], self.cultivator.display_name)
        self.assertNotIn(self.cultivator.email, json.dumps(entry))

    def test_an_offer_carries_its_commercial_terms_as_strings(self):
        entry = self.listings()[0]

        self.assertEqual(entry['default_grow_price'], '950.00')
        self.assertEqual(entry['minimum_yield_grams'], '30.00')

    def test_an_offer_names_its_product_types(self):
        self.assertEqual(self.listings()[0]['finished_product_types'], ['Pre-rolls'])

    def test_an_offer_reports_how_many_plants_are_behind_it(self):
        self.assertEqual(self.listings()[0]['plant_count'], 0)


class UpdateTests(ApiTestCase):
    def test_it_replaces_every_field(self):
        created = self.created()

        response = self.put(
            f'{CATALOGUE}/{created["id"]}',
            self.payload(name='Durban Poison', description='Rewritten.'),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.body(response)['description'], 'Rewritten.')

    def test_an_emptied_json_column_is_saved_empty(self):
        created = self.created(terpene_profile={'myrcene': 0.5})

        payload = self.body(
            self.put(f'{CATALOGUE}/{created["id"]}', self.payload(terpene_profile={}))
        )

        self.assertEqual(payload['terpene_profile'], {})

    def test_a_strain_may_be_reinstated_by_setting_its_status(self):
        """Why retirement needs no undo endpoint: the status is a field on the
        form the edit screen already submits."""
        strain = self.strain(status=StrainStatus.INACTIVE)

        payload = self.body(
            self.put(
                f'{CATALOGUE}/{strain.pk}',
                self.payload(name=strain.name, status=StrainStatus.ACTIVE),
            )
        )

        self.assertEqual(payload['status'], StrainStatus.ACTIVE)

    def test_a_refused_edit_changes_nothing(self):
        created = self.created(description='Original.')

        self.put(
            f'{CATALOGUE}/{created["id"]}',
            self.payload(description='Edited.', thc_content='220.00'),
        )

        strain = Strain.objects.get(pk=created['id'])
        self.assertEqual(strain.description, 'Original.')

    def test_an_unknown_id_is_a_404(self):
        response = self.put(
            f'{CATALOGUE}/00000000-0000-7000-8000-000000000000', self.payload()
        )

        self.assertEqual(response.status_code, 404)


class RetireTests(ApiTestCase):
    def test_it_sets_the_status_and_keeps_the_row(self):
        strain = self.strain()

        response = self.client.post(f'{CATALOGUE}/{strain.pk}/retire')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.body(response)['strain']['status'], StrainStatus.INACTIVE
        )
        self.assertTrue(Strain.objects.filter(pk=strain.pk).exists())

    def test_it_reports_how_many_offers_came_down(self):
        strain = self.strain()
        self.listing(strain, status=ListingStatus.LISTED)

        body = self.body(self.client.post(f'{CATALOGUE}/{strain.pk}/retire'))

        self.assertEqual(body['listings_taken_down'], 1)

    def test_retiring_twice_answers_200_with_zero(self):
        strain = self.strain()
        self.client.post(f'{CATALOGUE}/{strain.pk}/retire')

        response = self.client.post(f'{CATALOGUE}/{strain.pk}/retire')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)['listings_taken_down'], 0)

    def test_the_body_carries_the_whole_strain(self):
        """The same shape as every other strain response, so the screen replaces
        the record it is holding rather than patching a status into it."""
        strain = self.strain()

        body = self.body(self.client.post(f'{CATALOGUE}/{strain.pk}/retire'))

        self.assertIn('listings', body['strain'])
        self.assertIn('aromas', body['strain'])

    def test_there_is_no_delete(self):
        """Both foreign keys into a strain are PROTECT, so a strain the club has
        sold against cannot be deleted -- and an endpoint that sometimes could
        and sometimes could not would have behaviour the caller cannot predict.
        405 rather than a route that only sometimes works."""
        strain = self.strain()

        response = self.client.delete(f'{CATALOGUE}/{strain.pk}')

        self.assertEqual(response.status_code, 405)


class TermTests(ApiTestCase):
    def test_it_lists_both_vocabularies(self):
        self.aroma('Citrus')
        self.effect('Relaxing')

        body = self.body(self.client.get(TERMS))

        self.assertEqual([term['name'] for term in body['aromas']], ['Citrus'])
        self.assertEqual([term['name'] for term in body['effects']], ['Relaxing'])

    def test_each_term_carries_how_many_strains_use_it(self):
        term = self.aroma('Citrus')
        self.strain().aromas.add(term)

        body = self.body(self.client.get(TERMS))

        self.assertEqual(body['aromas'][0]['strain_count'], 1)

    def test_a_term_is_created_with_201(self):
        response = self.post(f'{TERMS}/aromas', {'name': 'Gassy'})

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.body(response)['slug'], 'gassy')

    def test_a_new_term_reports_a_count_of_zero(self):
        body = self.body(self.post(f'{TERMS}/aromas', {'name': 'Gassy'}))

        self.assertEqual(body['strain_count'], 0)

    def test_a_renamed_term_reports_its_real_count(self):
        """The count is annotated in the list query; a term just written has
        come back from `save` with no annotation, and the schema's default of
        zero would be wrong here."""
        term = self.aroma('Citrus')
        self.strain().aromas.add(term)

        body = self.body(
            self.put(
                f'{TERMS}/aromas/{term.pk}', {'name': 'Citrusy', 'is_available': True}
            )
        )

        self.assertEqual(body['strain_count'], 1)

    def test_a_duplicate_term_is_refused_with_422(self):
        self.aroma('Citrus')

        response = self.post(f'{TERMS}/aromas', {'name': 'citrus'})

        self.assertEqual(response.status_code, 422)
        self.assertIn('name', self.body(response)['fields'])

    def test_a_term_is_withdrawn_by_clearing_is_available(self):
        term = self.aroma('Gassy')

        body = self.body(
            self.put(
                f'{TERMS}/aromas/{term.pk}', {'name': 'Gassy', 'is_available': False}
            )
        )

        self.assertFalse(body['is_available'])

    def test_an_unknown_list_is_a_404(self):
        """A path naming a list that does not exist is a path with nothing
        behind it, not a malformed submission."""
        response = self.post(f'{TERMS}/flavours', {'name': 'Sweet'})

        self.assertEqual(response.status_code, 404)

    def test_an_unknown_term_is_a_404(self):
        response = self.put(
            f'{TERMS}/aromas/00000000-0000-7000-8000-000000000000',
            {'name': 'Gassy', 'is_available': True},
        )

        self.assertEqual(response.status_code, 404)

    def test_there_is_no_delete(self):
        """Deleting an Aroma would silently remove it from every strain that
        carried it, with nothing to say it had happened."""
        term = self.aroma('Citrus')

        self.assertEqual(
            self.client.delete(f'{TERMS}/aromas/{term.pk}').status_code, 405
        )


class CultivatorPickerTests(ApiTestCase):
    def cultivators(self):
        response = self.client.get('/api/catalogue/cultivators')
        self.assertEqual(response.status_code, 200, response.content)
        return self.body(response)

    def test_it_lists_the_growers(self):
        self.assertEqual(
            [entry['display_name'] for entry in self.cultivators()],
            [self.cultivator.display_name],
        )

    def test_it_offers_nobody_else(self):
        """A picker over every account in the club, on a screen where staff
        reserve a strain to somebody, is an invitation to pick the wrong person
        entirely -- `admin.cultivator_choices` says so about its own widget."""
        names = [entry['display_name'] for entry in self.cultivators()]

        self.assertNotIn(self.member.display_name, names)
        self.assertNotIn(self.admin.display_name, names)

    def test_it_carries_no_email_address(self):
        """Section 6.6 of `roles-and-permissions.md` makes `display_name` the
        only name any payload carries, and a picker is where that is most easily
        broken for the sake of a nicer autocomplete."""
        body = json.dumps(self.cultivators())

        self.assertNotIn(self.cultivator.email, body)
        self.assertNotIn('email', body)

    def test_it_offers_no_departed_grower(self):
        self.cultivator.soft_delete()

        self.assertEqual(self.cultivators(), [])

    def test_a_member_is_refused(self):
        self.client.force_login(self.member)

        self.assertEqual(
            self.client.get('/api/catalogue/cultivators').status_code, 403
        )

    def test_the_picker_agrees_with_the_write(self):
        """The property that matters: a picker offering an account the write
        would refuse is a form that refuses itself."""
        offered = {entry['id'] for entry in self.cultivators()}

        for account in (self.member, self.admin):
            self.assertNotIn(str(account.pk), offered)
            response = self.post(
                CATALOGUE, self.payload(exclusive_to=str(account.pk))
            )
            self.assertEqual(response.status_code, 422)

        for account_id in offered:
            response = self.post(
                CATALOGUE,
                self.payload(name=f'Reserved {account_id}', exclusive_to=account_id),
            )
            self.assertEqual(response.status_code, 201, response.content)


class DecimalPrecisionTests(ApiTestCase):
    def test_a_percentage_is_not_rounded_through_a_float(self):
        """The reason `Decimal` is serialised as a string. `0.1 + 0.2` is the
        canonical demonstration; `12.35` is the one that reaches a member."""
        payload = self.created(thc_content='12.35')

        self.assertEqual(payload['thc_content'], '12.35')
        self.assertEqual(
            Strain.objects.get(pk=payload['id']).thc_content, Decimal('12.35')
        )

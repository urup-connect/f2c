"""Tests for the stock-capture endpoints.

The rules themselves are tested in ``test_capture.py`` and ``test_upload.py``.
What is tested here is what the router and ``plant.stock`` add on top of them,
and nothing else:

1. **Who may load stock, and into whose greenhouse.** ``manage_plant_stock`` is
   granted to anybody appointed to any producer, so the permission on its own
   would let one farm's staff load plants into another's inventory. The test
   that matters is the second half -- a grower naming somebody else's producer
   gets a 403 -- because that is the object-level rule C13 recorded as having
   nothing to point at, and it is now the only thing standing between two
   farms.
2. **A ``Decimal`` crosses the wire as a string.** ``grow_price`` and
   ``leaf_rating`` are ``DECIMAL`` columns and a float cannot hold two decimal
   places exactly. Asserted rather than assumed: nothing in the schema *says*
   string, it is a property of how django-ninja serialises ``Decimal``, and a
   change to it would round money silently.
3. **The status code distinguishes a bad file from bad rows.** 400 for a
   workbook that is not a template, 422 for one whose rows were refused. Both
   load nothing, and a screen that could not tell them apart would show an
   empty error report for the first.
4. **Nothing is written when anything is refused**, over HTTP as at the shell.
   Asserted by counting plants, not by reading the response.
"""
import json
from io import BytesIO
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from f2c.testing import make_administrator

from ..models import Plant
from ..spreadsheet import COLUMNS, HEADINGS, PLANTS_SHEET
from .support import BLOOMS, HARVESTS, PLANTED, PlantTestCase

PLANTS = '/api/stock/plants'
UPLOADS = '/api/stock/uploads'
TEMPLATE = '/api/stock/template'

KEYS = [key for key, _, _ in COLUMNS]

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def workbook_of(rows):
    """A filled-in template, as bytes, ready to be posted."""
    book = Workbook()
    sheet = book.active
    sheet.title = PLANTS_SHEET
    sheet.append([HEADINGS[key] for key in KEYS])
    for row in rows:
        sheet.append([row.get(key) for key in KEYS])

    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


class StockApiTestCase(PlantTestCase):
    """Signed in as the person appointed to ``self.cultivator``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.grower)

    def body(self, response):
        return json.loads(response.content)

    def payload(self, **overrides):
        return {
            'cultivator': str(self.cultivator.pk),
            'cultivator_plant_id': 'POT-1',
            'strain': 'OG Kush',
            'grow_price': '950.00',
            'planting_date': PLANTED.isoformat(),
            'estimated_bloom_date': BLOOMS.isoformat(),
            'estimated_harvest_date': HARVESTS.isoformat(),
            'minimum_yield_grams': '30.00',
        } | overrides

    def capture(self, **overrides):
        return self.client.post(
            PLANTS,
            data=json.dumps(self.payload(**overrides)),
            content_type='application/json',
        )

    def sheet_row(self, **overrides):
        return {
            'cultivator_plant_id': 'POT-1',
            'strain': 'OG Kush',
            'grow_price': 950,
            'planting_date': PLANTED,
            'estimated_bloom_date': BLOOMS,
            'estimated_harvest_date': HARVESTS,
            'minimum_yield_grams': 30,
        } | overrides

    def upload(self, rows, *, cultivator=None, dry_run=False, content=None):
        content = workbook_of(rows) if content is None else content
        return self.client.post(UPLOADS, {
            'workbook': SimpleUploadedFile('stock.xlsx', content),
            'cultivator': str((cultivator or self.cultivator).pk),
            'dry_run': 'true' if dry_run else 'false',
        })


class PermissionTests(StockApiTestCase):
    def test_an_appointed_grower_may_capture(self):
        self.assertEqual(self.capture().status_code, 201)

    def test_a_member_is_refused(self):
        """A club membership grants ``view_own_inventory``, never
        ``manage_plant_stock``. Loading stock is a farm's act."""
        self.client.force_login(self.member)

        response = self.capture()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Plant.objects.count(), 0)

    def test_a_club_administrator_is_refused(self):
        """Not an oversight. ``manage_plant_stock`` is a producer action and no
        administrator set holds it -- an administrator who loaded stock would be
        keying plants into a greenhouse they have never seen."""
        self.client.force_login(make_administrator('admin@example.com'))

        self.assertEqual(self.capture().status_code, 403)

    def test_a_grower_may_not_load_into_another_farm(self):
        """The object-level half, and the reason ``plant.stock`` exists.

        Both accounts hold ``manage_plant_stock`` -- it is granted by every
        appointment -- so the permission alone would let this through, and the
        producer arrives in the payload where the caller controls it.
        """
        other_person, other_farm = self.another_cultivator()
        self.client.force_login(other_person)

        response = self.capture()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Plant.objects.count(), 0)

    def test_a_visitor_is_refused_before_anything_is_read(self):
        self.client.logout()

        self.assertEqual(self.capture().status_code, 401)

    def test_an_unknown_producer_is_a_404(self):
        """A 404 rather than a 403, and asked before the permission question so
        a caller cannot learn which unknown identifiers are real farms."""
        response = self.capture(cultivator=str(uuid4()))

        self.assertEqual(response.status_code, 404)

    def test_a_malformed_producer_identifier_is_a_404(self):
        response = self.client.get(TEMPLATE, {'cultivator': 'not-a-uuid'})

        self.assertEqual(response.status_code, 404)


class CaptureTests(StockApiTestCase):
    def test_a_captured_plant_answers_with_the_record_as_stored(self):
        response = self.capture()
        body = self.body(response)
        plant = Plant.objects.get()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(body['id'], str(plant.pk))
        self.assertEqual(body['serial'], plant.serial)
        self.assertEqual(body['cultivator_pseudonym'], 'Kloof')
        self.assertEqual(body['strain_name'], 'OG Kush')
        self.assertEqual(body['status'], 'preflowering')
        self.assertEqual(body['finished_product_types'], ['Pre-rolls'])
        self.assertIsNone(body['batch'])

    def test_money_and_the_leaf_rating_cross_the_wire_as_strings(self):
        """A float cannot hold ``950.00`` exactly, and a leaf rating that
        arrived as ``0.9999999`` would disagree with the swap zone."""
        body = self.body(self.capture())

        self.assertEqual(body['grow_price'], '950.00')
        self.assertEqual(body['minimum_yield_grams'], '30.00')
        self.assertEqual(body['leaf_rating'], '1.0')

    def test_the_day_counts_are_reported(self):
        body = self.body(self.capture())

        self.assertIsInstance(body['days_to_bloom'], int)
        self.assertIsInstance(body['days_to_harvest'], int)

    def test_a_batch_reference_comes_back_by_name(self):
        body = self.body(self.capture(batch='CROP-7'))

        self.assertEqual(body['batch'], 'CROP-7')

    def test_a_refusal_is_keyed_by_field_and_writes_nothing(self):
        response = self.capture(strain='Nothing I Grow')
        body = self.body(response)

        self.assertEqual(response.status_code, 422)
        self.assertIn('strain', body['fields'])
        self.assertEqual(Plant.objects.count(), 0)

    def test_an_ambiguous_date_is_refused_rather_than_guessed(self):
        """``03/04/2026`` is April in Johannesburg and March in Chicago. The
        endpoint passes the value through untouched so ``spreadsheet`` is the
        only thing that decides -- typing it as a ``date`` in the schema would
        have pydantic answer first, in a different shape."""
        response = self.capture(planting_date='03/04/2026')

        self.assertEqual(response.status_code, 422)
        self.assertIn('planting_date', self.body(response)['fields'])

    def test_a_price_with_three_decimals_is_refused(self):
        response = self.capture(grow_price='950.005')

        self.assertEqual(response.status_code, 422)
        self.assertIn('grow_price', self.body(response)['fields'])

    def test_a_missing_required_field_is_refused_by_field(self):
        response = self.capture(cultivator_plant_id='')

        self.assertEqual(response.status_code, 422)
        self.assertIn('cultivator_plant_id', self.body(response)['fields'])

    def test_a_duplicate_plant_id_is_refused(self):
        self.assertEqual(self.capture().status_code, 201)

        response = self.capture()

        self.assertEqual(response.status_code, 422)
        self.assertEqual(Plant.objects.count(), 1)


class UploadTests(StockApiTestCase):
    def test_a_valid_workbook_loads_stock(self):
        response = self.upload([
            self.sheet_row(cultivator_plant_id='POT-1'),
            self.sheet_row(cultivator_plant_id='POT-2'),
        ])
        body = self.body(response)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body['ok'])
        self.assertEqual(body['rows_read'], 2)
        self.assertEqual(len(body['created']), 2)
        self.assertEqual(
            body['created'],
            list(Plant.objects.order_by('serial').values_list('serial', flat=True)),
        )

    def test_a_dry_run_validates_and_writes_nothing(self):
        response = self.upload([self.sheet_row()], dry_run=True)
        body = self.body(response)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(body['ok'])
        self.assertTrue(body['dry_run'])
        self.assertEqual(body['created'], [])
        self.assertEqual(Plant.objects.count(), 0)

    def test_a_refused_row_is_a_422_and_loads_none_of_the_file(self):
        """The test that matters is not that the bad row is reported -- it is
        that the *good* row beside it is not loaded."""
        response = self.upload([
            self.sheet_row(cultivator_plant_id='POT-1'),
            self.sheet_row(cultivator_plant_id='POT-2', strain='Nothing I Grow'),
        ])
        body = self.body(response)

        self.assertEqual(response.status_code, 422)
        self.assertFalse(body['ok'])
        self.assertEqual(body['created'], [])
        self.assertEqual(Plant.objects.count(), 0)

    def test_an_error_names_the_row_the_column_and_the_field(self):
        """Three audiences in one payload: the row and heading a cultivator
        reads off the screen, and the key a form attaches the message to."""
        response = self.upload([self.sheet_row(strain='Nothing I Grow')])
        error = self.body(response)['errors'][0]

        self.assertEqual(error['row'], 2)
        self.assertEqual(error['key'], 'strain')
        self.assertEqual(error['column'], 'Strain')
        self.assertEqual(error['value'], 'Nothing I Grow')
        self.assertTrue(error['message'])

    def test_a_file_that_is_not_a_workbook_is_a_400(self):
        """Not 422. A file that will not open is not a row anybody can fix, and
        a refusal carrying an empty error list would show a failure with nothing
        under it."""
        response = self.upload([], content=b'this is not a spreadsheet')

        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', self.body(response))

    def test_a_workbook_without_the_plants_sheet_is_a_400(self):
        book = Workbook()
        book.active.title = 'Sheet1'
        stream = BytesIO()
        book.save(stream)

        response = self.upload([], content=stream.getvalue())

        self.assertEqual(response.status_code, 400)

    def test_a_grower_may_not_upload_into_another_farm(self):
        other_person, other_farm = self.another_cultivator()
        self.client.force_login(other_person)

        response = self.upload([self.sheet_row()])

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Plant.objects.count(), 0)


class TemplateTests(StockApiTestCase):
    def test_the_template_downloads_as_a_workbook(self):
        response = self.client.get(TEMPLATE, {'cultivator': self.cultivator.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], XLSX)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('Kloof', response['Content-Disposition'])

    def test_the_strain_count_is_a_header_so_a_screen_need_not_parse_the_file(self):
        response = self.client.get(TEMPLATE, {'cultivator': self.cultivator.pk})

        self.assertEqual(response['X-Strain-Count'], '1')

    def test_a_farm_with_no_listings_still_gets_a_template(self):
        """An appointment without a published listing is a normal state. The
        empty dropdown is why the count is reported."""
        other_person, other_farm = self.another_cultivator()
        self.client.force_login(other_person)

        response = self.client.get(TEMPLATE, {'cultivator': other_farm.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Strain-Count'], '0')

    def test_another_farm_may_not_read_this_one_s_template(self):
        """It lists a farm's own offerings and what each is delivered as, which
        is their commercial position rather than a public document."""
        other_person, other_farm = self.another_cultivator()
        self.client.force_login(other_person)

        response = self.client.get(TEMPLATE, {'cultivator': self.cultivator.pk})

        self.assertEqual(response.status_code, 403)

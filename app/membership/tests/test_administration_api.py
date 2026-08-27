"""The six endpoints under ``/api/members`` that an administrator drives.

What is asserted here is the translation and the payload: which status code each
outcome becomes, what crosses the wire, and -- the part worth the most -- what
deliberately does not. The rules themselves are tested in
``test_administration.py`` and are not asserted twice.

``force_login`` throughout, and unsafe methods go through ``enforce_csrf=False``
via the test client's own session handling: django-ninja's cookie auth enforces
CSRF on POST and PUT, and Django's test client is exempt by design. The 401 and
403 branches are tested because they are the two answers a browser can actually
provoke.
"""
import json

from app.accounts.models import IdentityNumberDisclosure, UserStatus
from app.accounts.roles import UserRole
from app.payments.models import SubscriptionStatus

from .support import ADULT_ID, RegisterTestCase

REGISTER = '/api/members'


class MemberApiTestCase(RegisterTestCase):
    """Request helpers, so each test reads as the call it is making."""

    def get(self, path=REGISTER, **query):
        return self.client.get(path, query)

    def put(self, path, payload):
        return self.client.put(
            path, data=json.dumps(payload), content_type='application/json'
        )

    def post(self, path, payload=None):
        return self.client.post(
            path,
            data=json.dumps(payload or {}),
            content_type='application/json',
        )

    def member_path(self, member=None, suffix=''):
        return f'{REGISTER}/{(member or self.member).pk}{suffix}'


class Authentication(MemberApiTestCase):
    """401 for no session, 403 for the wrong one. Two different answers."""

    def test_the_register_needs_a_session(self):
        self.assertEqual(401, self.get().status_code)

    def test_a_record_needs_a_session(self):
        self.assertEqual(401, self.get(self.member_path()).status_code)

    def test_a_member_is_refused_the_register(self):
        self.client.force_login(self.member)

        self.assertEqual(403, self.get().status_code)

    def test_a_member_is_refused_a_record(self):
        # 403 and not 404, and that is the right way round: the service asks the
        # permission question before it reads, so a caller who may not manage
        # the membership is told so rather than told the member does not exist.
        self.client.force_login(self.member)

        self.assertEqual(403, self.get(self.member_path()).status_code)

    def test_a_cultivator_is_refused(self):
        self.client.force_login(self.cultivator)

        self.assertEqual(403, self.get().status_code)

    def test_a_member_may_not_suspend_anybody(self):
        self.client.force_login(self.member)

        self.assertEqual(
            403, self.post(self.member_path(self.admin, '/suspend')).status_code
        )


class TheRegisterEndpoint(MemberApiTestCase):
    """``GET /api/members``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_it_lists_every_account_newest_first(self):
        response = self.get()

        self.assertEqual(200, response.status_code)
        nicknames = [row['nickname'] for row in response.json()]
        # setUp creates the administrator, then the cultivator, then the member.
        self.assertEqual(['Thabo', 'Kloof', 'Registrar'], nicknames)

    def test_a_row_carries_the_status_and_role_labels(self):
        # The two vocabularies live in `accounts` and the check constraints
        # enforce them; a second copy in the frontend would drift from both.
        row = self.get().json()[0]

        self.assertEqual(UserStatus.ACTIVE, row['status'])
        self.assertEqual('Active', row['status_label'])
        self.assertEqual(UserRole.MEMBER, row['role'])
        self.assertEqual('Member', row['role_label'])

    def test_a_row_carries_no_identity_number_in_any_form(self):
        # Not even the masked one: `id_number_masked` decrypts, and a masked
        # column on a list of six hundred members is six hundred decryptions per
        # page load. The list needs only whether one is on file.
        self.member.id_number = ADULT_ID
        self.member.save()

        row = self.get().json()[0]

        self.assertTrue(row['has_id_number'])
        self.assertNotIn('id_number', row)
        self.assertNotIn('id_number_masked', row)

    def test_a_row_carries_the_live_subscription(self):
        self.subscribe(self.member)

        row = self.get().json()[0]

        self.assertEqual(SubscriptionStatus.ACTIVE, row['membership']['status'])
        self.assertEqual('Active', row['membership']['status_label'])
        self.assertEqual('2026-12-31', row['membership']['paid_until'])

    def test_a_member_with_no_subscription_gets_nulls_not_a_missing_key(self):
        # A missing key is a screen that has to guard every read. Nulls in a
        # known shape is one branch, in one place.
        self.assertEqual(
            {'status': None, 'status_label': None, 'paid_until': None},
            self.get().json()[0]['membership'],
        )

    def test_the_filters_narrow(self):
        self.assertEqual(
            ['Kloof'],
            [row['nickname'] for row in self.get(role=UserRole.CULTIVATOR).json()],
        )

    def test_a_blank_filter_is_no_filter(self):
        self.assertEqual(
            len(self.get().json()),
            len(self.get(status='', role='', search='', joined_within=0).json()),
        )

    def test_joined_within_gives_the_recent_signups_view(self):
        self.joined(self.member, days_ago=200)

        listed = [row['nickname'] for row in self.get(joined_within=30).json()]
        self.assertNotIn('Thabo', listed)

    def test_an_erased_account_is_listed_and_marked(self):
        # Present, marked, and read-only -- rather than missing from the
        # register with nothing to say why.
        self.member.soft_delete()

        erased = [row for row in self.get().json() if row['erased']]
        self.assertEqual(1, len(erased))
        self.assertIsNone(erased[0]['email'])


class TheRecordEndpoint(MemberApiTestCase):
    """``GET /api/members/{id}``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_an_unknown_id_is_a_404(self):
        self.assertEqual(
            404,
            self.get(f'{REGISTER}/0195d3aa-0000-7000-8000-000000000000').status_code,
        )

    def test_it_carries_the_masked_identity_number_and_never_the_number(self):
        self.member.id_number = ADULT_ID
        self.member.save()

        record = self.get(self.member_path()).json()

        self.assertTrue(record['has_id_number'])
        self.assertTrue(record['id_number_masked'].endswith(ADULT_ID[-4:]))
        self.assertNotIn(ADULT_ID, json.dumps(record))

    def test_a_member_with_no_number_masks_to_blank(self):
        self.assertEqual('', self.get(self.member_path()).json()['id_number_masked'])

    def test_it_says_whether_the_record_may_be_written_to(self):
        # Sent rather than derived in the browser: the two reasons a record is
        # read-only are rules in `administration._editable`, and a second copy
        # in the frontend would be a form offering a save the API then refuses.
        self.assertTrue(self.get(self.member_path()).json()['editable'])

    def test_an_erased_record_is_readable_and_not_editable(self):
        self.member.soft_delete()

        record = self.get(self.member_path()).json()

        self.assertTrue(record['erased'])
        self.assertFalse(record['editable'])

    def test_a_sharing_member_names_the_cultivator_and_is_not_editable(self):
        held = self.sharing_member()

        record = self.get(self.member_path(held)).json()

        self.assertEqual('Kloof', record['registered_by'])
        self.assertFalse(record['editable'])

    def test_the_disclosure_history_comes_down_with_the_record(self):
        self.member.id_number = ADULT_ID
        self.member.save()
        self.post(
            self.member_path(suffix='/identity-number'),
            {'reason': 'Verifying against the document on file.'},
        )

        record = self.get(self.member_path()).json()

        self.assertEqual(1, len(record['disclosures']))
        self.assertEqual('Registrar', record['disclosures'][0]['read_by'])
        self.assertEqual(
            'Verifying against the document on file.',
            record['disclosures'][0]['reason'],
        )


class Editing(MemberApiTestCase):
    """``PUT /api/members/{id}``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_a_good_submission_answers_200_with_the_record_as_stored(self):
        response = self.put(self.member_path(), self.edit(last_name='Mahlangu'))

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual('Mahlangu', body['last_name'])
        # The stored form, not the submitted one: `+27…`, normalised by save.
        self.assertEqual('+27821234567', body['mobile'])
        # The same shape a read answers with, so the screen needs one code path.
        self.assertIn('disclosures', body)
        self.assertIn('membership', body)

    def test_a_field_refusal_is_a_422_keyed_to_the_field(self):
        other = self.account('taken@example.com', 'Taken')

        response = self.put(self.member_path(), self.edit(email=other.email))

        self.assertEqual(422, response.status_code)
        self.assertIn('email', response.json()['fields'])

    def test_a_record_level_refusal_is_a_422_in_detail(self):
        # An erased account is not a field an administrator can correct, so
        # marking it up against an input would point at nothing. It goes in
        # `detail`, which is where the screen renders a sentence.
        self.member.soft_delete()

        response = self.put(self.member_path(), self.edit())

        self.assertEqual(422, response.status_code)
        self.assertEqual({}, response.json()['fields'])
        self.assertIn('erased', response.json()['detail'].lower())

    def test_a_sharing_member_refuses_the_write(self):
        held = self.sharing_member()

        response = self.put(self.member_path(held), self.edit())

        self.assertEqual(422, response.status_code)

    def test_an_unknown_id_is_a_404_before_the_body_is_considered(self):
        response = self.put(
            f'{REGISTER}/0195d3aa-0000-7000-8000-000000000000', self.edit()
        )

        self.assertEqual(404, response.status_code)

    def test_there_is_no_create_endpoint(self):
        # One route into the membership, and it is `POST /api/members/register`.
        # An account typed in by hand would have no consent ledger behind it.
        response = self.post(REGISTER, self.edit())

        self.assertEqual(405, response.status_code)

    def test_there_is_no_delete_endpoint(self):
        # Suspension is reversible and is here; erasure is irreversible and is
        # `User.soft_delete` in the Django admin, deliberately not a button
        # beside an edit form.
        response = self.client.delete(self.member_path())

        self.assertEqual(405, response.status_code)


class Suspending(MemberApiTestCase):
    """``POST /api/members/{id}/suspend``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_it_answers_200_with_the_record_at_its_new_status(self):
        response = self.post(self.member_path(suffix='/suspend'))

        self.assertEqual(200, response.status_code)
        self.assertEqual(UserStatus.SUSPENDED, response.json()['status'])
        self.assertEqual('Suspended', response.json()['status_label'])

    def test_it_is_idempotent(self):
        self.post(self.member_path(suffix='/suspend'))

        self.assertEqual(
            200, self.post(self.member_path(suffix='/suspend')).status_code
        )

    def test_suspending_your_own_account_is_a_422(self):
        response = self.post(self.member_path(self.admin, '/suspend'))

        self.assertEqual(422, response.status_code)
        self.assertIn('sign you out', response.json()['detail'])

    def test_a_sharing_member_is_a_422(self):
        response = self.post(self.member_path(self.sharing_member(), '/suspend'))

        self.assertEqual(422, response.status_code)


class Reinstating(MemberApiTestCase):
    """``POST /api/members/{id}/reinstate``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def test_it_lifts_a_suspension(self):
        self.post(self.member_path(suffix='/suspend'))

        response = self.post(self.member_path(suffix='/reinstate'))

        self.assertEqual(200, response.status_code)
        self.assertEqual(UserStatus.ACTIVE, response.json()['status'])

    def test_an_unpaid_account_is_a_422_naming_where_it_sits(self):
        waiting = self.account(
            'waiting@example.com', 'Waiting', status=UserStatus.PENDING_PAYMENT
        )

        response = self.post(self.member_path(waiting, '/reinstate'))

        self.assertEqual(422, response.status_code)
        self.assertIn('pending payment', response.json()['detail'].lower())


class DisclosingAnIdentityNumber(MemberApiTestCase):
    """``POST /api/members/{id}/identity-number``."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)
        self.member.id_number = ADULT_ID
        self.member.save()
        self.path = self.member_path(suffix='/identity-number')

    def test_it_answers_the_number_and_the_record_of_the_read(self):
        response = self.post(
            self.path, {'reason': 'Verifying against the document on file.'}
        )

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(ADULT_ID, body['id_number'])
        self.assertEqual('Registrar', body['disclosure']['read_by'])

    def test_the_read_is_recorded_before_it_answers(self):
        self.post(self.path, {'reason': 'Verifying against the document on file.'})

        self.assertEqual(
            1, IdentityNumberDisclosure.objects.filter(member=self.member).count()
        )

    def test_a_reason_too_short_to_review_is_a_422_and_writes_nothing(self):
        response = self.post(self.path, {'reason': 'ok'})

        self.assertEqual(422, response.status_code)
        self.assertIn('reason', response.json()['fields'])
        self.assertFalse(IdentityNumberDisclosure.objects.exists())

    def test_a_member_with_no_number_on_file_is_a_422(self):
        bare = self.account('bare@example.com', 'Bare')

        response = self.post(
            self.member_path(bare, '/identity-number'),
            {'reason': 'Checking whether one is on file.'},
        )

        self.assertEqual(422, response.status_code)
        self.assertFalse(IdentityNumberDisclosure.objects.exists())

    def test_there_is_no_GET_that_returns_the_number(self):
        # A GET is cacheable, prefetchable and logged by every proxy between
        # here and the administrator's desk -- and it has no body to carry the
        # reason, which is the field that makes the disclosure reviewable.
        self.assertEqual(405, self.client.get(self.path).status_code)

    def test_a_member_may_not_read_their_own_number_through_this(self):
        # The self-service route is `/api/accounts/me/profile`, which answers
        # the masked form. This endpoint holds out for the register's permission
        # like every other one on the router.
        self.client.force_login(self.member)

        response = self.post(
            self.path, {'reason': 'I would like to see my own number.'}
        )

        self.assertEqual(403, response.status_code)
        self.assertFalse(IdentityNumberDisclosure.objects.exists())


class TheSignUpEndpointsStillWork(MemberApiTestCase):
    """The two routers share ``/api/members`` and must not shadow each other."""

    def test_nickname_availability_is_still_unauthenticated(self):
        # The regression this guards: mounting a second router on the same
        # prefix, or naming a path `/{uuid:member_id}` that swallowed
        # `/nickname/availability`, would take sign-up down silently.
        response = self.post(
            f'{REGISTER}/nickname/availability', {'nickname': 'Freshly'}
        )

        self.assertEqual(200, response.status_code)
        self.assertTrue(response.json()['available'])

    def test_register_is_still_reachable_without_a_session(self):
        # A 503 is the right answer here -- no club document has been published
        # in this test case, so there is nothing lawful to agree to. What
        # matters is that it is not a 401, 404 or 405.
        response = self.post(f'{REGISTER}/register', {})

        self.assertNotIn(response.status_code, (401, 404, 405))

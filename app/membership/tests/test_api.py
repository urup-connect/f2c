"""Tests for the registration endpoint.

The service tests cover what is written. These cover the contract: which status
code, which machine-readable refusal, and above all **what never appears in a
response**.

That last one is the reason this module exists separately. The identity number
is encrypted at rest precisely because it discloses age, gender and citizenship
status, and a response body echoing it back would put it in the browser cache
and every proxy log between here and the member. So there is an assertion for
it on every path, including the refusals -- the paths where an error handler is
most likely to have helpfully included the input.
"""
import json
from datetime import date

from django.conf import settings
from django.core.cache import cache
from django.test import Client

from app.accounts.models import User, UserStatus
from app.membership.throttles import RegisterThrottle

from .support import ADULT_ID, SECOND_ADULT_ID, RegistrationTestCase, sa_id_for

REGISTER = '/api/members/register'

# No test here raises the rate limit, and none needs to: the counters live in
# the cache, every test clears it first, and no test but ThrottleTests spends
# more than a couple of the allowance. Overriding the rate would not work
# anyway -- it is read when the throttle is constructed, at import time.


class RegisterEndpointTests(RegistrationTestCase):
    def setUp(self):
        super().setUp()
        # Limits live in the cache and are keyed on client IP, so without this
        # they carry from one test into the next and fail whichever ran last.
        cache.clear()
        self.client = Client()

    def register(self, **overrides):
        return self.client.post(
            REGISTER,
            data=json.dumps(self.submission(**overrides)),
            content_type='application/json',
        )

    def body(self, response):
        return json.loads(response.content)


class AcceptedTests(RegisterEndpointTests):
    def test_a_valid_submission_is_accepted(self):
        response = self.register()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)['status'], UserStatus.PENDING_PAYMENT)

    def test_it_creates_the_member(self):
        self.register()

        member = User.objects.get(email='thandiwe@example.com')
        self.assertEqual(member.status, UserStatus.PENDING_PAYMENT)
        self.assertFalse(member.is_active)

    def test_the_response_carries_nothing_the_member_typed(self):
        """A server action redirects after this; a redirect is only a URL."""
        response = self.register()

        self.assertEqual(set(self.body(response)), {'status', 'detail'})

    def test_the_response_never_carries_the_identity_number(self):
        response = self.register()

        self.assertNotIn(ADULT_ID, response.content.decode())

    def test_the_response_says_what_happens_next(self):
        response = self.register()

        self.assertIn('payment', self.body(response)['detail'].lower())


class DuplicateTests(RegisterEndpointTests):
    def test_a_registered_address_gets_the_same_answer_as_a_new_one(self):
        """Otherwise the form is a way to ask whether a named person is a member."""
        first = self.register()
        second = self.register(
            nickname='Grower2', id_number=SECOND_ADULT_ID, mobile='083 555 1234'
        )

        self.assertEqual(first.status_code, second.status_code)
        self.assertEqual(self.body(first), self.body(second))

    def test_a_registered_address_creates_no_second_member(self):
        self.register()
        self.register(
            nickname='Grower2', id_number=SECOND_ADULT_ID, mobile='083 555 1234'
        )

        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_identity_number_gets_the_same_answer(self):
        first = self.register()
        second = self.register(
            nickname='Grower2', email='other@example.com', mobile='083 555 1234'
        )

        self.assertEqual(self.body(first), self.body(second))
        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_mobile_number_gets_the_same_answer(self):
        first = self.register()
        second = self.register(
            nickname='Grower2', email='other@example.com', id_number=SECOND_ADULT_ID
        )

        self.assertEqual(self.body(first), self.body(second))
        self.assertEqual(User.objects.count(), 1)

    def test_every_duplicate_key_answers_identically(self):
        """Address, identity document, handset: one answer, so none is a lookup.

        The point is the *sameness*. If any key answered differently, the form
        would become a way to ask which of the three a given value matched.
        """
        accepted = self.body(self.register())

        fresh = {
            'nickname': 'Grower2',
            'email': 'other@example.com',
            'id_number': SECOND_ADULT_ID,
            'mobile': '083 555 1234',
        }

        for key in ('email', 'id_number', 'mobile'):
            with self.subTest(key=key):
                overrides = {k: v for k, v in fresh.items() if k != key}

                response = self.register(**overrides)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.body(response), accepted)

        self.assertEqual(User.objects.count(), 1)


class RefusalTests(RegisterEndpointTests):
    def test_a_taken_nickname_is_refused_and_says_so_in_a_readable_field(self):
        self.register()

        # A fresh address, identity number and mobile: all three are duplicate
        # keys checked before the nickname, so any one carried over would be
        # answered with a silent success instead.
        response = self.register(
            email='other@example.com',
            id_number=SECOND_ADULT_ID,
            mobile='083 555 1234',
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.body(response)['nickname_unavailable'])
        self.assertEqual(self.body(response)['superseded_documents'], [])

    def test_a_superseded_document_names_which_one(self):
        submitted = self.consents()
        self.supersede('annexures', label='2')

        response = self.register(consents=submitted)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.body(response)['superseded_documents'], ['annexures'])
        self.assertFalse(self.body(response)['nickname_unavailable'])

    def test_a_field_the_rules_refuse_is_a_422(self):
        response = self.register(mobile='086 123 4567')

        self.assertEqual(response.status_code, 422)
        self.assertEqual(User.objects.count(), 0)

    def test_a_refusal_never_carries_the_identity_number_either(self):
        response = self.register(mobile='086 123 4567')

        self.assertNotIn(ADULT_ID, response.content.decode())

    def test_a_missing_field_is_refused_by_the_schema(self):
        response = self.client.post(
            REGISTER,
            data=json.dumps({'email': 'thandiwe@example.com'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(User.objects.count(), 0)

    def test_a_document_with_no_revision_is_a_503(self):
        """Nothing is wrong with the submission, and the member can only return."""
        self.document(slug='code-of-conduct', position=3, required_at_signup=True)

        response = self.register()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(User.objects.count(), 0)


class ThrottleTests(RegisterEndpointTests):
    """The limit as a client meets it, at the configured rate.

    The rate is read when the throttle object is constructed, which happens at
    import time, so ``override_settings`` cannot reach it. These use the number
    that is actually deployed -- which is the number worth testing.
    """

    def allowance(self):
        return int(settings.NINJA_DEFAULT_THROTTLE_RATES[RegisterThrottle.scope]
                   .split('/')[0])

    def test_the_scope_has_a_configured_rate(self):
        """A scope with no rate is unlimited, and silently so."""
        self.assertIn(RegisterThrottle.scope, settings.NINJA_DEFAULT_THROTTLE_RATES)

    def test_the_endpoint_is_rate_limited(self):
        """The control that stands in for a CSRF check this endpoint cannot have."""
        for attempt in range(self.allowance()):
            # Each one a different person, so nothing is refused as a duplicate
            # and the limit is the only thing that can refuse anything.
            response = self.register(
                email=f'member{attempt}@example.com',
                nickname=f'Grower{attempt}',
                id_number=sa_id_for(date(1990, 3, 15), sequence=f'51{attempt:02d}'),
            )
            self.assertNotEqual(
                response.status_code, 429, f'refused at attempt {attempt + 1}'
            )

        refused = self.register(email='one-too-many@example.com', nickname='GrowerX')

        self.assertEqual(refused.status_code, 429)


class SignInTests(RegisterEndpointTests):
    def test_a_newly_registered_member_cannot_sign_in(self):
        """The requirement, end to end through the endpoints a member would use."""
        self.register()

        start = self.client.post(
            '/api/auth/login/start',
            data=json.dumps({'email': 'thandiwe@example.com'}),
            content_type='application/json',
        )

        # Answered exactly as an unknown address is: no passkey challenge, and
        # no code issued.
        self.assertEqual(self.body(start), {'method': 'otp', 'options': None})
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)

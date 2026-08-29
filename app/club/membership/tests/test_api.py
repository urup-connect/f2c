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
from django.core import mail
from django.core.cache import cache
from django.test import Client

from app.core.accounts.models import User, UserStatus
from app.club.membership.throttles import RegisterThrottle
from app.core.payments.models import Subscription

from .support import ADULT_ID, SECOND_ADULT_ID, RegistrationTestCase, sa_id_for
from app.club.membership.models import MembershipStatus
from app.core.documents.models import Agreement

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
        self.assertEqual(self.body(response)['status'], MembershipStatus.PENDING_PAYMENT)

    def test_it_creates_the_member(self):
        self.register()

        member = User.objects.get(email='thandiwe@example.com')
        self.assertEqual(member.club_membership.status, MembershipStatus.PENDING_PAYMENT)
        # Active from the moment the account exists — C27. What is
        # outstanding is the membership, asserted just above.
        self.assertTrue(member.is_active)

    def test_the_response_carries_nothing_the_member_typed(self):
        """A server action redirects after this; a redirect is only a URL.

        ``checkout_token`` is the third field and it is not something the member
        typed: it is 32 bytes of entropy naming a subscription, generated here.
        The assertion is on the exact key set rather than on the absence of the
        six submitted values, because a field added later without a decision
        behind it should fail this test rather than slip through.
        """
        response = self.register()

        self.assertEqual(
            set(self.body(response)), {'status', 'detail', 'checkout_token'}
        )

    def test_it_hands_back_a_checkout_token_for_the_subscription_it_opened(self):
        """The token is the only way a new member reaches Payfast."""
        response = self.register()

        member = User.objects.get(email='thandiwe@example.com')
        subscription = member.subscriptions.get()

        self.assertEqual(
            self.body(response)['checkout_token'], subscription.checkout_token
        )

    def test_the_checkout_token_is_not_the_subscription_id(self):
        """The id goes to Payfast; the token goes in a URL. Keeping them apart
        is what lets one be expired without touching the other."""
        response = self.register()
        subscription = User.objects.get(
            email='thandiwe@example.com'
        ).subscriptions.get()

        self.assertNotIn(
            str(subscription.pk), self.body(response)['checkout_token']
        )

    def test_the_response_never_carries_the_identity_number(self):
        response = self.register()

        self.assertNotIn(ADULT_ID, response.content.decode())

    def test_the_response_says_what_happens_next(self):
        response = self.register()

        self.assertIn('payment', self.body(response)['detail'].lower())


class DuplicateTests(RegisterEndpointTests):
    """What a submission naming somebody already on file is told.

    **This class encodes a rule that has been deliberately narrowed.** It used
    to assert that a duplicate and a new registration are answered *identically*,
    so that the form could not be used to ask whether a named person is a member
    of a cannabis club. Adding the Payfast redirect broke that: a new member is
    sent to a payment page and a duplicate cannot be, because there is no
    subscription to pay for.

    What is asserted now is the narrowest thing that is still true, and it is
    worth being precise about because the difference is the disclosure:

    * every field except ``checkout_token`` is byte-identical,
    * the token is ``null`` -- not a decoy, not a token for the existing
      member's subscription, which would let a stranger pay for one,
    * nothing is written, and
    * the status code is the same.

    So what leaks is one bit -- "this address may already be on file" -- to
    whoever submitted the form. It is not confirmed, no name, status, join date
    or outstanding amount comes back, and the link to finish an outstanding
    payment goes to the mailbox instead. That trade was taken knowingly; see
    ``design/features/payments.md`` section 4 and risk 1, and
    ``design/features/sign-up.md``.
    """

    def duplicate_of(self, first_body, response):
        """Assert ``response`` is the duplicate answer to ``first_body``.

        One helper rather than the same three assertions in five tests, so the
        rule is stated once and every duplicate key is held to all of it.
        """
        body = self.body(response)

        self.assertEqual(response.status_code, 200)
        # The disclosure, and its exact size: one field, and it is empty.
        self.assertIsNone(body['checkout_token'])
        # Everything else is identical. `first_body` carries a real token, so it
        # is compared with that key removed from both sides.
        self.assertEqual(
            {k: v for k, v in body.items() if k != 'checkout_token'},
            {k: v for k, v in first_body.items() if k != 'checkout_token'},
        )
        return body

    def test_a_registered_address_gets_the_same_answer_apart_from_the_token(self):
        """Otherwise the form is a way to ask whether a named person is a member."""
        first = self.register()
        second = self.register(
            nickname='Grower2', id_number=SECOND_ADULT_ID, mobile='083 555 1234'
        )

        self.assertEqual(first.status_code, second.status_code)
        self.duplicate_of(self.body(first), second)

    def test_a_registered_address_creates_no_second_member(self):
        self.register()
        self.register(
            nickname='Grower2', id_number=SECOND_ADULT_ID, mobile='083 555 1234'
        )

        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_address_opens_no_second_subscription(self):
        """A duplicate writes nothing at all, and a second live mandate against
        one account is the thing Payfast would bill twice."""
        self.register()
        self.register(
            nickname='Grower2', id_number=SECOND_ADULT_ID, mobile='083 555 1234'
        )

        self.assertEqual(Subscription.objects.count(), 1)

    def test_a_registered_identity_number_gets_the_same_answer(self):
        first = self.register()
        second = self.register(
            nickname='Grower2', email='other@example.com', mobile='083 555 1234'
        )

        self.duplicate_of(self.body(first), second)
        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_mobile_number_gets_the_same_answer(self):
        first = self.register()
        second = self.register(
            nickname='Grower2', email='other@example.com', id_number=SECOND_ADULT_ID
        )

        self.duplicate_of(self.body(first), second)
        self.assertEqual(User.objects.count(), 1)

    def test_every_duplicate_key_answers_identically(self):
        """Address, identity document, handset: one answer, so none is a lookup.

        The point is still the *sameness* -- across the three keys. If any of
        them answered differently from the others, the form would become a way
        to ask which of the three a given value matched, which is a sharper
        question than "is this address on file" and is the one this test has
        always been about.
        """
        accepted = self.body(self.register())

        fresh = {
            'nickname': 'Grower2',
            'email': 'other@example.com',
            'id_number': SECOND_ADULT_ID,
            'mobile': '083 555 1234',
        }

        answers = []
        for key in ('email', 'id_number', 'mobile'):
            with self.subTest(key=key):
                overrides = {k: v for k, v in fresh.items() if k != key}

                answers.append(self.duplicate_of(accepted, self.register(**overrides)))

        # And identical to each other, not merely each identical to the rule.
        self.assertEqual(answers[1:], answers[:-1])
        self.assertEqual(User.objects.count(), 1)

    def test_a_duplicate_address_is_emailed_the_outstanding_payment_link(self):
        """The one channel a duplicate may use: it reaches the mailbox, not the
        person who filled in the form."""
        self.register()
        subscription = Subscription.objects.get()
        mail.outbox.clear()

        # The send is deferred to commit -- see
        # `payments.services.email_outstanding_checkout` on why -- and a
        # TestCase never commits, so without this the callback is captured and
        # dropped and the assertion below reads as "no email was sent".
        with self.captureOnCommitCallbacks(execute=True):
            self.register(
                nickname='Grower2',
                id_number=SECOND_ADULT_ID,
                mobile='083 555 1234',
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['thandiwe@example.com'])
        self.assertIn(subscription.checkout_token, mail.outbox[0].body)

    def test_a_duplicate_identity_number_under_another_address_is_emailed_nothing(self):
        """Sending here would tell the typed address about somebody else's
        membership. The duplicate is answered; no mail moves."""
        self.register()
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.register(
                nickname='Grower2',
                email='other@example.com',
                mobile='083 555 1234',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mail.outbox, [])


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
        self.document(
            slug='code-of-conduct',
            position=3,
            agreement=Agreement.AT_REGISTRATION,
        )

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
    def test_a_newly_registered_member_signs_in_and_owes_the_club(self):
        """End to end through the endpoints a member would use.

        **The opposite of what this asserted until C27.** Sign-in used to answer
        an unpaid member exactly as it answers an unknown address — no passkey
        challenge, no code issued — because `is_active` was derived from an
        account status of `pending_payment`. The block is on the membership now,
        so the door opens and the club does not.
        """
        self.register()

        start = self.client.post(
            '/api/auth/login/start',
            data=json.dumps({'email': 'thandiwe@example.com'}),
            content_type='application/json',
        )

        # A real sign-in route is offered, where an unknown address gets none.
        self.assertEqual(self.body(start)['method'], 'otp')

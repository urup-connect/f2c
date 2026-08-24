"""Tests for the nickname check the sign-up form makes on the way out of the field.

Two things are being held in place here.

**The answer says one thing.** ``{"available": false}`` and nothing else -- no
holder, no count, no echo of what was asked. The assertion for that is on every
path, because a body that grows a field is how this becomes a way to ask about
somebody else's record rather than about a name the caller already had.

**Taken and reserved are the same answer.** They are two different facts to us
and one fact to a member: choose again.
"""
import json

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase

from app.accounts.models import User, UserStatus
from app.membership import services
from app.membership.throttles import NicknameAvailabilityThrottle

AVAILABILITY = '/api/members/nickname/availability'


class NicknameAvailabilityEndpointTests(TestCase):
    """The contract. No club documents needed: nothing here writes anything."""

    def setUp(self):
        super().setUp()
        # Keyed on client IP and held in the cache, so without this the count
        # carries into whichever test runs next.
        cache.clear()
        self.client = Client()

    def ask(self, nickname):
        return self.client.post(
            AVAILABILITY,
            data=json.dumps({'nickname': nickname}),
            content_type='application/json',
        )

    def body(self, response):
        return json.loads(response.content)

    def member(self, nickname, email='holder@example.com'):
        return User.objects.create_user(
            email=email, nickname=nickname, status=UserStatus.ACTIVE
        )


class AvailableTests(NicknameAvailabilityEndpointTests):
    def test_a_free_nickname_is_available(self):
        response = self.ask('Grower')

        self.assertEqual(response.status_code, 200)
        self.assertIs(self.body(response)['available'], True)

    def test_the_answer_carries_nothing_but_the_boolean(self):
        """A field added here is a disclosure nobody reviewed."""
        self.assertEqual(set(self.body(self.ask('Grower'))), {'available'})

    def test_the_nickname_is_not_echoed_back(self):
        self.assertNotIn('Grower', self.ask('Grower').content.decode())


class TakenTests(NicknameAvailabilityEndpointTests):
    def test_a_taken_nickname_is_unavailable(self):
        self.member('Grower')

        response = self.ask('Grower')

        self.assertEqual(response.status_code, 200)
        self.assertIs(self.body(response)['available'], False)

    def test_the_comparison_ignores_capitalisation(self):
        """`Grower` and `grower` cannot both exist, so neither may look free."""
        self.member('Grower')

        self.assertIs(self.body(self.ask('GROWER'))['available'], False)

    def test_a_reserved_nickname_is_unavailable_rather_than_rejected(self):
        """Well formed, belongs to nobody, and there is nothing else to say."""
        for nickname in ('admin', 'Support', 'collective', 'age-check'):
            with self.subTest(nickname=nickname):
                response = self.ask(nickname)

                self.assertEqual(response.status_code, 200)
                self.assertIs(self.body(response)['available'], False)

    def test_the_answer_does_not_say_who_holds_it(self):
        self.member('Grower', email='thandiwe@example.com')

        content = self.ask('Grower').content.decode()

        self.assertNotIn('thandiwe', content)
        self.assertEqual(set(self.body(self.ask('Grower'))), {'available'})

    def test_a_suspended_member_keeps_their_nickname(self):
        User.objects.create_user(
            email='suspended@example.com',
            nickname='Grower',
            status=UserStatus.SUSPENDED,
        )

        self.assertIs(self.body(self.ask('Grower'))['available'], False)


class MalformedTests(NicknameAvailabilityEndpointTests):
    """The frontend refuses all of these first. Reaching one means drift."""

    def test_a_malformed_nickname_is_a_422(self):
        for nickname in ('', '  ', 'ab', 'x' * 21, 'gro wer', '1grower', 'grower-'):
            with self.subTest(nickname=nickname):
                self.assertEqual(self.ask(nickname).status_code, 422)

    def test_a_refusal_says_what_is_wrong_without_repeating_the_value(self):
        response = self.ask('gro wer')

        self.assertIn('detail', self.body(response))
        self.assertNotIn('gro wer', response.content.decode())

    def test_a_missing_field_is_refused_rather_than_read_as_blank(self):
        response = self.client.post(
            AVAILABILITY, data=json.dumps({}), content_type='application/json'
        )

        self.assertEqual(response.status_code, 422)


class UnauthenticatedTests(NicknameAvailabilityEndpointTests):
    def test_no_session_is_needed(self):
        """There is no account until registration returns, so there is none here."""
        self.assertEqual(self.ask('Grower').status_code, 200)

    def test_the_nickname_never_travels_in_a_url(self):
        """A GET would put it in every access log between here and the member."""
        response = self.client.get(f'{AVAILABILITY}?nickname=Grower')

        self.assertEqual(response.status_code, 405)


class ThrottleTests(NicknameAvailabilityEndpointTests):
    """The limit at the rate that is actually deployed.

    The rate is read when the throttle is constructed, at import time, so
    ``override_settings`` cannot reach it.
    """

    def allowance(self):
        rate = settings.NINJA_DEFAULT_THROTTLE_RATES[NicknameAvailabilityThrottle.scope]
        return int(rate.split('/')[0])

    def test_the_scope_has_a_configured_rate(self):
        """A scope with no rate is unlimited, and silently so."""
        self.assertIn(
            NicknameAvailabilityThrottle.scope, settings.NINJA_DEFAULT_THROTTLE_RATES
        )

    def test_it_is_looser_than_registration(self):
        """A member tries a few names in one sitting; they join once."""
        rates = settings.NINJA_DEFAULT_THROTTLE_RATES

        self.assertGreater(
            int(rates[NicknameAvailabilityThrottle.scope].split('/')[0]),
            int(rates['register'].split('/')[0]),
        )

    def test_the_endpoint_is_rate_limited(self):
        """What bounds harvesting the nickname list."""
        for attempt in range(self.allowance()):
            self.assertNotEqual(
                self.ask(f'Grower{attempt}').status_code,
                429,
                f'refused at attempt {attempt + 1}',
            )

        self.assertEqual(self.ask('GrowerX').status_code, 429)


class ServiceTests(TestCase):
    """The rule itself, where the endpoint has nothing to do with the answer."""

    def test_a_free_nickname_is_available(self):
        self.assertIs(services.nickname_is_available('Grower'), True)

    def test_a_taken_nickname_is_not(self):
        User.objects.create_user(
            email='holder@example.com', nickname='Grower', status=UserStatus.ACTIVE
        )

        self.assertIs(services.nickname_is_available('Grower'), False)

    def test_a_reserved_nickname_is_answered_rather_than_raised(self):
        self.assertIs(services.nickname_is_available('admin'), False)

    def test_a_malformed_nickname_raises(self):
        for nickname in ('', 'ab', 'gro wer'):
            with self.subTest(nickname=nickname):
                with self.assertRaises(ValidationError):
                    services.nickname_is_available(nickname)

    def test_an_erased_member_holds_no_nickname(self):
        """Erasure blanks the nickname, so the name goes back into circulation."""
        user = User.objects.create_user(
            email='holder@example.com', nickname='Grower', status=UserStatus.ACTIVE
        )
        user.soft_delete()

        self.assertIs(services.nickname_is_available('Grower'), True)

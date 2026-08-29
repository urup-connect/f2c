"""Tests for the rate limits on the unauthenticated authentication endpoints.

These are the only thing standing between the API and two abuses that need no
credential at all: using ``otp/start`` to mailbomb a member, and using
``otp/verify`` to walk a six-digit space. Neither shows up as an error in
normal use, so a limit that has quietly stopped being applied looks exactly
like one that works.

Each endpoint has a scope of its own, so a burst of failed code entries cannot
exhaust the budget for sending new ones. The scopes are asserted separately
below for that reason.

Two things about how these are written. The rates come from
``NINJA_DEFAULT_THROTTLE_RATES`` and are read when the throttle object is
constructed, which happens at import time -- so ``override_settings`` cannot
reach them and the tests use the configured numbers instead. And the counters
live in the cache, so every test clears it first: otherwise the limit is shared
with whatever ran before.
"""
import json

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase

from app.core.accounts.models import User, UserStatus
from app.core.authn.models import EmailOtp
from app.core.authn.throttles import (
    AuthStartThrottle,
    OtpStartThrottle,
    OtpVerifyThrottle,
    PasskeyVerifyThrottle,
)

TOO_MANY_REQUESTS = 429


class ThrottleConfigTests(TestCase):
    """A scope with no configured rate is unlimited, and silently so."""

    def test_every_throttle_has_a_scope_of_its_own(self):
        scopes = [
            AuthStartThrottle.scope,
            OtpStartThrottle.scope,
            OtpVerifyThrottle.scope,
            PasskeyVerifyThrottle.scope,
        ]

        self.assertEqual(len(set(scopes)), len(scopes))

    def test_every_scope_has_a_configured_rate(self):
        for throttle in (
            AuthStartThrottle,
            OtpStartThrottle,
            OtpVerifyThrottle,
            PasskeyVerifyThrottle,
        ):
            with self.subTest(scope=throttle.scope):
                self.assertIn(
                    throttle.scope, settings.NINJA_DEFAULT_THROTTLE_RATES
                )
                self.assertTrue(
                    settings.NINJA_DEFAULT_THROTTLE_RATES[throttle.scope]
                )

    def test_sending_codes_is_the_tightest_limit(self):
        """It is the one that costs a member's mailbox rather than a request."""
        rates = settings.NINJA_DEFAULT_THROTTLE_RATES
        allowed = {
            scope: int(rate.split('/')[0]) for scope, rate in rates.items()
        }

        self.assertEqual(min(allowed, key=allowed.get), OtpStartThrottle.scope)

    def test_the_configured_rates_parse(self):
        """A malformed rate string raises at import, but only once it is parsed."""
        for throttle in (
            AuthStartThrottle,
            OtpStartThrottle,
            OtpVerifyThrottle,
            PasskeyVerifyThrottle,
        ):
            with self.subTest(scope=throttle.scope):
                instance = throttle()
                self.assertGreater(instance.num_requests, 0)
                self.assertGreater(instance.duration, 0)


class ThrottledEndpointTests(TestCase):
    """The limits as a client meets them: the request after the last one is a 429."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.member = User.objects.create_user(
            email='member@example.com', status=UserStatus.ACTIVE
        )

    def post(self, path, payload):
        return self.client.post(
            path, data=json.dumps(payload), content_type='application/json'
        )

    def allowance(self, scope):
        return int(settings.NINJA_DEFAULT_THROTTLE_RATES[scope].split('/')[0])

    def exhaust(self, path, payload, scope):
        """Spend the whole allowance, asserting none of it is refused."""
        for attempt in range(self.allowance(scope)):
            response = self.post(path, payload)
            self.assertNotEqual(
                response.status_code, TOO_MANY_REQUESTS, f'refused at attempt {attempt + 1}'
            )

    def test_sending_codes_is_capped(self):
        """Without this the endpoint is a mailbomb relay for any address."""
        payload = {'email': 'member@example.com'}
        self.exhaust('/api/auth/otp/start', payload, OtpStartThrottle.scope)

        self.assertEqual(
            self.post('/api/auth/otp/start', payload).status_code, TOO_MANY_REQUESTS
        )

    def test_the_cap_holds_for_an_address_with_no_account(self):
        """Otherwise the limit itself would reveal which addresses are members."""
        payload = {'email': 'nobody@example.com'}
        self.exhaust('/api/auth/otp/start', payload, OtpStartThrottle.scope)

        self.assertEqual(
            self.post('/api/auth/otp/start', payload).status_code, TOO_MANY_REQUESTS
        )

    def test_a_refused_request_sends_nothing(self):
        from django.core import mail

        payload = {'email': 'member@example.com'}
        self.exhaust('/api/auth/otp/start', payload, OtpStartThrottle.scope)
        sent = len(mail.outbox)

        self.post('/api/auth/otp/start', payload)

        self.assertEqual(len(mail.outbox), sent)

    def test_verifying_codes_is_capped(self):
        payload = {'email': 'member@example.com', 'code': '000000'}
        self.exhaust('/api/auth/otp/verify', payload, OtpVerifyThrottle.scope)

        self.assertEqual(
            self.post('/api/auth/otp/verify', payload).status_code, TOO_MANY_REQUESTS
        )

    def test_resolving_an_address_is_capped(self):
        payload = {'email': 'member@example.com'}
        self.exhaust('/api/auth/login/start', payload, AuthStartThrottle.scope)

        self.assertEqual(
            self.post('/api/auth/login/start', payload).status_code, TOO_MANY_REQUESTS
        )

    def test_presenting_passkeys_is_capped(self):
        payload = {'email': 'member@example.com', 'credential': {'id': 'nope'}}
        self.exhaust('/api/auth/login/passkey', payload, PasskeyVerifyThrottle.scope)

        self.assertEqual(
            self.post('/api/auth/login/passkey', payload).status_code,
            TOO_MANY_REQUESTS,
        )

    def test_each_endpoint_counts_separately(self):
        """A member locked out of sending codes can still be sent one by
        ``login/start``, and vice versa -- so the tighter limit cannot be used
        to disable the looser one."""
        payload = {'email': 'member@example.com'}
        self.exhaust('/api/auth/otp/start', payload, OtpStartThrottle.scope)

        self.assertEqual(
            self.post('/api/auth/otp/start', payload).status_code, TOO_MANY_REQUESTS
        )
        self.assertEqual(self.post('/api/auth/login/start', payload).status_code, 200)

    def test_the_authenticated_routes_are_not_throttled(self):
        """They need a session, which is a far better bound than a rate."""
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        for _ in range(self.allowance(OtpStartThrottle.scope) + 5):
            self.assertEqual(self.client.get('/api/health').status_code, 200)

    def test_the_limit_bounds_requests_not_codes_issued(self):
        """Superseding means one live code however many were asked for."""
        payload = {'email': 'member@example.com'}
        self.exhaust('/api/auth/otp/start', payload, OtpStartThrottle.scope)

        self.assertEqual(EmailOtp.objects.usable().count(), 1)

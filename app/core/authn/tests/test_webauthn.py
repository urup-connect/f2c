"""Tests for the WebAuthn ceremony helpers.

A ceremony is two round trips with a challenge held in the session between
them, and the challenge is the whole security property: it is what makes a
signature fresh rather than replayable. So what is tested here is the handling
of that value -- that it expires, that it is single use, and that a challenge
issued for one ceremony cannot be spent on the other -- rather than the
signature mathematics, which is py_webauthn's to get right and is exercised
against real authenticators, not in a unit test.

``store_challenge`` and ``take_challenge`` take a session object and nothing
else, so a bare ``SessionStore`` stands in for a request's session here.
"""
import json
import time

from django.contrib.sessions.backends.cache import SessionStore
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from app.core.authn import webauthn as wa
from app.core.authn.models import PasskeyCredential


class RelyingPartyConfigTests(SimpleTestCase):
    """A missing RP ID must stop the ceremony, not produce a broken one."""

    @override_settings(WEBAUTHN_RP_ID='f2c.co.za')
    def test_rp_id_is_read_from_settings(self):
        self.assertEqual(wa.rp_id(), 'f2c.co.za')

    @override_settings(WEBAUTHN_RP_ID='')
    def test_a_missing_rp_id_is_loud(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            wa.rp_id()

        # The message has to name the variable: this fails in deployment, not in dev.
        self.assertIn('DJANGO_WEBAUTHN_RP_ID', str(caught.exception))

    @override_settings(WEBAUTHN_ORIGINS=['https://app.example.co.za'])
    def test_origins_are_read_from_settings(self):
        self.assertEqual(wa.origins(), ['https://app.example.co.za'])

    @override_settings(WEBAUTHN_ORIGINS=[])
    def test_missing_origins_are_loud(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            wa.origins()

        self.assertIn('DJANGO_WEBAUTHN_ORIGINS', str(caught.exception))


class EncodingTests(SimpleTestCase):
    """Credentials are stored as base64url text, which is how the browser reports them."""

    def test_round_trip(self):
        raw = bytes(range(256))
        self.assertEqual(wa.decode(wa.encode(raw)), raw)

    def test_encoding_is_url_safe_and_unpadded(self):
        encoded = wa.encode(b'\xff\xfe\xfd\xfc')

        self.assertNotIn('+', encoded)
        self.assertNotIn('/', encoded)
        self.assertNotIn('=', encoded)


class ChallengeStoreTests(SimpleTestCase):
    """The challenge is the freshness guarantee. These are its three rules."""

    def setUp(self):
        self.session = SessionStore()

    async def test_a_stored_challenge_comes_back(self):
        await wa.store_challenge(self.session, wa.LOGIN_CHALLENGE_KEY, b'a-challenge')

        stored = await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        self.assertEqual(wa.decode(stored['challenge']), b'a-challenge')

    async def test_extra_ceremony_state_is_kept_alongside_it(self):
        """login_start pins the challenge to a user, so another account's
        credential cannot be presented against it."""
        await wa.store_challenge(
            self.session, wa.LOGIN_CHALLENGE_KEY, b'c', user_id='the-user'
        )

        stored = await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        self.assertEqual(stored['user_id'], 'the-user')

    async def test_a_challenge_is_single_use(self):
        """Removed whether or not the verification that follows succeeds."""
        await wa.store_challenge(self.session, wa.LOGIN_CHALLENGE_KEY, b'c')

        self.assertIsNotNone(
            await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        )
        self.assertIsNone(
            await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        )

    async def test_an_absent_challenge_is_none_rather_than_an_error(self):
        self.assertIsNone(
            await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        )

    async def stale_challenge(self, key):
        """A challenge whose TTL has already run out.

        Written straight into the session rather than by moving the clock: the
        stamp is what ``take_challenge`` reads, and patching ``time.time``
        process-wide would move it for everything else running too.
        """
        await self.session.aset(
            key, {'challenge': wa.encode(b'c'), 'expires': time.time() - 1}
        )

    async def test_an_expired_challenge_is_refused(self):
        await self.stale_challenge(wa.LOGIN_CHALLENGE_KEY)

        self.assertIsNone(
            await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        )

    async def test_an_expired_challenge_is_also_removed(self):
        """Refusing it but leaving it in the session would let it be retried."""
        await self.stale_challenge(wa.LOGIN_CHALLENGE_KEY)
        await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)

        self.assertNotIn(wa.LOGIN_CHALLENGE_KEY, self.session.keys())

    async def test_the_ttl_comes_from_settings(self):
        with override_settings(WEBAUTHN_CHALLENGE_TTL_SECONDS=60):
            before = time.time()
            await wa.store_challenge(self.session, wa.LOGIN_CHALLENGE_KEY, b'c')

        stored = await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        self.assertAlmostEqual(stored['expires'] - before, 60, delta=5)

    async def test_the_two_ceremonies_use_separate_keys(self):
        """Otherwise an enrolment challenge could be replayed against sign-in."""
        self.assertNotEqual(wa.LOGIN_CHALLENGE_KEY, wa.REGISTER_CHALLENGE_KEY)

        await wa.store_challenge(self.session, wa.REGISTER_CHALLENGE_KEY, b'enrol')

        self.assertIsNone(
            await wa.take_challenge(self.session, wa.LOGIN_CHALLENGE_KEY)
        )
        self.assertIsNotNone(
            await wa.take_challenge(self.session, wa.REGISTER_CHALLENGE_KEY)
        )


@override_settings(
    WEBAUTHN_RP_ID='localhost',
    WEBAUTHN_RP_NAME='Cultivators Collective',
    WEBAUTHN_ORIGINS=['http://localhost:3000'],
)
class OptionsTests(SimpleTestCase):
    """What the browser is handed. These options are the ceremony's parameters."""

    def credential(self, credential_id=b'existing-credential'):
        # Unsaved: only `credential_id` is read, and only to build a descriptor.
        return PasskeyCredential(credential_id=wa.encode(credential_id))

    def test_registration_options_name_the_relying_party(self):
        options, _ = wa.registration_options(
            user_handle=b'0123456789abcdef',
            user_name='member@example.com',
            user_display_name='Bean',
            exclude=[],
        )

        self.assertEqual(options['rp']['id'], 'localhost')
        self.assertEqual(options['rp']['name'], 'Cultivators Collective')

    def test_registration_options_carry_the_user_handle_not_the_address(self):
        """The spec forbids personal information in the user handle, and a
        discoverable credential syncs it into a password manager."""
        handle = b'0123456789abcdef'
        options, _ = wa.registration_options(
            user_handle=handle,
            user_name='member@example.com',
            user_display_name='Bean',
            exclude=[],
        )

        self.assertEqual(wa.decode(options['user']['id']), handle)
        # The address is the account's name, and must not also be its handle.
        self.assertEqual(options['user']['name'], 'member@example.com')
        self.assertNotIn(b'member@example.com', wa.decode(options['user']['id']))

    def test_registration_options_ask_for_a_discoverable_credential(self):
        options, _ = wa.registration_options(
            user_handle=b'0123456789abcdef',
            user_name='member@example.com',
            user_display_name='Bean',
            exclude=[],
        )
        selection = options['authenticatorSelection']

        self.assertEqual(selection['residentKey'], 'preferred')
        # Preferred, not required: requiring it locks out authenticators with
        # no biometric or PIN of their own.
        self.assertEqual(selection['userVerification'], 'preferred')

    def test_registration_options_exclude_the_passkeys_already_held(self):
        """So an authenticator that already has one says so instead of
        enrolling a duplicate."""
        options, _ = wa.registration_options(
            user_handle=b'0123456789abcdef',
            user_name='member@example.com',
            user_display_name='Bean',
            exclude=[self.credential()],
        )

        excluded = [wa.decode(item['id']) for item in options['excludeCredentials']]
        self.assertEqual(excluded, [b'existing-credential'])

    def test_registration_returns_the_raw_challenge_beside_the_options(self):
        """The caller stores the raw bytes; the browser gets the encoded form."""
        options, challenge = wa.registration_options(
            user_handle=b'0123456789abcdef',
            user_name='member@example.com',
            user_display_name='Bean',
            exclude=[],
        )

        self.assertIsInstance(challenge, bytes)
        self.assertEqual(wa.decode(options['challenge']), challenge)

    def test_authentication_options_allow_only_the_named_credentials(self):
        options, challenge = wa.authentication_options(allow=[self.credential()])

        allowed = [wa.decode(item['id']) for item in options['allowCredentials']]
        self.assertEqual(allowed, [b'existing-credential'])
        self.assertEqual(options['rpId'], 'localhost')
        self.assertEqual(wa.decode(options['challenge']), challenge)

    def test_two_ceremonies_never_share_a_challenge(self):
        _, first = wa.authentication_options(allow=[self.credential()])
        _, second = wa.authentication_options(allow=[self.credential()])

        self.assertNotEqual(first, second)

    def test_options_are_json_serialisable(self):
        """They cross the wire as a dict inside a JSON response."""
        options, _ = wa.authentication_options(allow=[self.credential()])

        self.assertIsInstance(json.dumps(options), str)


class VerificationConfigTests(SimpleTestCase):
    """Verification refuses to run at all without an RP ID to check against."""

    @override_settings(WEBAUTHN_RP_ID='', WEBAUTHN_ORIGINS=[])
    def test_registration_verification_needs_configuration(self):
        with self.assertRaises(ImproperlyConfigured):
            wa.verify_registration(credential={}, challenge=b'c')

    @override_settings(WEBAUTHN_RP_ID='', WEBAUTHN_ORIGINS=[])
    def test_authentication_verification_needs_configuration(self):
        with self.assertRaises(ImproperlyConfigured):
            wa.verify_authentication(
                credential={}, challenge=b'c', public_key=b'k', sign_count=0
            )

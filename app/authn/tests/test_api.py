"""Tests for the HTTP authentication surface.

Two properties dominate this module, and neither is visible in a response body.

The first is that the API must not say who is a member. ``login/start`` and
``otp/start`` answer an unknown address exactly as they answer a real one, and
a Pending, Suspended or erased account exactly as they answer an unknown one.
A regression there is silent: every response still looks correct, and the
endpoint has quietly become a membership lookup for anyone with a list of email
addresses. So the assertions are mostly about what did *not* happen -- no
email, no code row, no difference in the payload.

The second is that only an Active account can ever hold a session. That is
checked at two points on the passkey path, because a challenge issued moments
before a suspension must not still open one.

The signature mathematics is mocked. What a real authenticator returns is
verified by py_webauthn against real hardware; what is under test here is what
this application does with the answer -- which credential it will accept it
for, and what it writes when it does.
"""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from app.authn import webauthn as wa
from app.accounts.models import User, UserStatus
from app.authn.models import EmailOtp, PasskeyCredential, PasskeyUserHandle
from app.authn.tests.test_otp import code_from_last_email

# The RP has to be configured for any passkey route to run at all.
WEBAUTHN_SETTINGS = dict(
    WEBAUTHN_RP_ID='localhost',
    WEBAUTHN_RP_NAME='Cultivators Collective',
    WEBAUTHN_ORIGINS=['http://localhost:3000'],
)

STAFF_PASSWORD = 'Str0ng-Passphrase!'


class ApiTestCase(TestCase):
    """Shared plumbing: JSON helpers, and a cache cleared between tests.

    The rate limits live in the cache and are keyed on client IP, so without
    the clear they would carry from one test into the next and fail whichever
    one happened to run last.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = Client()

    def post(self, path, payload=None, client=None):
        return (client or self.client).post(
            path, data=json.dumps(payload or {}), content_type='application/json'
        )

    def get(self, path, client=None):
        return (client or self.client).get(path)

    def body(self, response):
        return json.loads(response.content)

    def make_member(self, email='member@example.com', **overrides):
        fields = {'status': UserStatus.ACTIVE}
        fields.update(overrides)
        return User.objects.create_user(email=email, **fields)

    def make_passkey(self, user, credential_id=b'credential-one', **overrides):
        fields = {
            'user': user,
            'credential_id': wa.encode(credential_id),
            'public_key': wa.encode(b'a-public-key'),
        }
        fields.update(overrides)
        return PasskeyCredential.objects.create(**fields)

    def put_challenge(self, key, challenge=b'a-challenge', **extra):
        """Park a challenge in the client's session, as the first half would."""
        session = self.client.session
        session[key] = {
            'challenge': wa.encode(challenge),
            'expires': (timezone.now() + timedelta(seconds=300)).timestamp(),
            **extra,
        }
        session.save()

    def assert_signed_in_as(self, user):
        response = self.get('/api/auth/me')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)['id'], str(user.pk))

    def assert_signed_out(self):
        self.assertEqual(self.get('/api/auth/me').status_code, 401)


class HealthTests(ApiTestCase):
    def test_health_needs_no_session(self):
        response = self.get('/api/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)['status'], 'ok')

    @override_settings(DEBUG=False)
    def test_the_schema_is_not_published_outside_debug(self):
        self.assertEqual(self.get('/api/docs').status_code, 404)


class CsrfTests(ApiTestCase):
    """Sign-in is a state-changing request, so it must not be forgeable.

    The endpoints that run before a session exists set ``auth=None``, which
    also turns off django-ninja's own CSRF check -- so they call it themselves,
    and this is what proves they still do.
    """

    def test_the_csrf_endpoint_sets_the_cookie(self):
        response = self.get('/api/auth/csrf')

        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', response.cookies)

    def test_an_unsafe_request_without_a_token_is_refused(self):
        strict = Client(enforce_csrf_checks=True)

        response = self.post(
            '/api/auth/login/start', {'email': 'member@example.com'}, client=strict
        )

        self.assertEqual(response.status_code, 403)

    def test_the_refusal_says_where_to_get_a_token(self):
        strict = Client(enforce_csrf_checks=True)

        response = self.post('/api/auth/otp/start', {'email': 'x@example.com'}, client=strict)

        self.assertIn('/api/auth/csrf', self.body(response)['detail'])

    def test_a_request_carrying_the_token_is_accepted(self):
        strict = Client(enforce_csrf_checks=True)
        strict.get('/api/auth/csrf')
        token = strict.cookies['csrftoken'].value

        response = strict.post(
            '/api/auth/login/start',
            data=json.dumps({'email': 'member@example.com'}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )

        self.assertEqual(response.status_code, 200)

    def test_every_pre_session_endpoint_checks(self):
        """One missing call here is one forgeable sign-in route.

        Each payload is schema-valid on purpose. django-ninja parses the body
        before it calls the view, and the CSRF check lives inside the view, so
        an empty body is refused as unprocessable and never reaches the check
        this test is about.
        """
        strict = Client(enforce_csrf_checks=True)
        address = {'email': 'member@example.com'}
        endpoints = (
            ('/api/auth/login/start', address),
            ('/api/auth/login/passkey', {**address, 'credential': {}}),
            ('/api/auth/otp/start', address),
            ('/api/auth/otp/verify', {**address, 'code': '000000'}),
            ('/api/auth/login', {**address, 'password': 'irrelevant'}),
            ('/api/auth/logout', {}),
        )

        for path, payload in endpoints:
            with self.subTest(path=path):
                response = self.post(path, payload, client=strict)
                self.assertEqual(response.status_code, 403)


class LoginStartTests(ApiTestCase):
    """Which credential to ask for -- and, above all, what this does not reveal."""

    def start(self, email):
        return self.post('/api/auth/login/start', {'email': email})

    def test_a_member_with_no_passkey_is_sent_a_code(self):
        member = self.make_member()

        response = self.start('member@example.com')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response), {'method': 'otp', 'options': None})
        self.assertEqual(EmailOtp.objects.filter(user=member).count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_an_unknown_address_gets_the_same_answer(self):
        """The endpoint cannot be used to find out who is a member."""
        known = self.start('member@example.com')
        self.make_member()
        cache.clear()
        registered = self.start('member@example.com')

        self.assertEqual(known.status_code, registered.status_code)
        self.assertEqual(self.body(known), self.body(registered))

    def test_an_unknown_address_is_sent_nothing(self):
        self.start('nobody@example.com')

        self.assertEqual(EmailOtp.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_an_inactive_account_is_indistinguishable_from_an_unknown_one(self):
        # Every status but Active, taken from the enum rather than listed. A
        # status added later -- Pending payment was -- must not arrive without
        # this covering it.
        for status in (
            status for status in UserStatus if status != UserStatus.ACTIVE
        ):
            with self.subTest(status=status):
                User.objects.all().delete()
                mail.outbox.clear()
                cache.clear()
                self.make_member(status=status)

                response = self.start('member@example.com')

                self.assertEqual(self.body(response), {'method': 'otp', 'options': None})
                self.assertEqual(len(mail.outbox), 0)

    def test_an_erased_account_is_too(self):
        self.make_member().soft_delete()

        response = self.start('member@example.com')

        self.assertEqual(self.body(response), {'method': 'otp', 'options': None})
        self.assertEqual(len(mail.outbox), 0)

    def test_a_blank_address_is_answered_without_a_lookup(self):
        response = self.start('   ')

        self.assertEqual(self.body(response)['method'], 'otp')
        self.assertEqual(len(mail.outbox), 0)

    def test_the_address_is_matched_case_insensitively(self):
        self.make_member()

        self.start('MEMBER@Example.COM')

        self.assertEqual(len(mail.outbox), 1)

    @override_settings(**WEBAUTHN_SETTINGS)
    def test_a_member_with_a_passkey_is_challenged(self):
        member = self.make_member()
        self.make_passkey(member)

        response = self.start('member@example.com')
        payload = self.body(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['method'], 'passkey')
        self.assertEqual(payload['options']['rpId'], 'localhost')
        # No code sent: the member has a credential, so there is nothing to email.
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(**WEBAUTHN_SETTINGS)
    def test_the_challenge_offers_only_that_members_credentials(self):
        member = self.make_member()
        self.make_passkey(member, b'ours')
        self.make_passkey(self.make_member('other@example.com'), b'theirs')

        payload = self.body(self.start('member@example.com'))
        allowed = [wa.decode(item['id']) for item in payload['options']['allowCredentials']]

        self.assertEqual(allowed, [b'ours'])

    @override_settings(**WEBAUTHN_SETTINGS)
    def test_the_challenge_is_stored_pinned_to_the_member(self):
        """Regression guard. ``user_id`` has to survive a round trip through the
        session, which is serialised to JSON -- and JSON has no UUID type, so a
        raw ``user.pk`` here raises on the way out and every passkey sign-in
        becomes a 500.
        """
        member = self.make_member()
        self.make_passkey(member)

        self.start('member@example.com')
        stored = self.client.session[wa.LOGIN_CHALLENGE_KEY]

        self.assertEqual(stored['user_id'], str(member.pk))
        self.assertTrue(stored['challenge'])

    @override_settings(**WEBAUTHN_SETTINGS)
    def test_a_suspended_member_with_a_passkey_is_still_only_offered_a_code(self):
        member = self.make_member(status=UserStatus.SUSPENDED)
        self.make_passkey(member)

        self.assertEqual(self.body(self.start('member@example.com'))['method'], 'otp')


class OtpStartTests(ApiTestCase):
    def start(self, email):
        return self.post('/api/auth/otp/start', {'email': email})

    def test_a_member_is_sent_a_code(self):
        self.make_member()

        response = self.start('member@example.com')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(EmailOtp.objects.usable().count(), 1)

    def test_an_unknown_address_gets_the_same_reply_and_no_email(self):
        known = self.start('nobody@example.com')
        self.make_member()
        cache.clear()
        real = self.start('member@example.com')

        self.assertEqual(self.body(known), self.body(real))
        self.assertEqual(len(mail.outbox), 1)

    def test_the_reply_is_deliberately_conditional(self):
        response = self.start('nobody@example.com')

        self.assertIn('If that address belongs to a member', self.body(response)['detail'])

    def test_asking_again_supersedes_the_first_code(self):
        """The resend path. Two emails, but only ever one code that works."""
        self.make_member()

        self.start('member@example.com')
        first = code_from_last_email()
        self.start('member@example.com')

        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(EmailOtp.objects.usable().count(), 1)
        self.assertEqual(
            self.post('/api/auth/otp/verify',
                      {'email': 'member@example.com', 'code': first}).status_code,
            401,
        )


class OtpVerifyTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member(first_name='Craig', nickname='Bean')
        self.post('/api/auth/otp/start', {'email': 'member@example.com'})
        self.code = code_from_last_email()

    def verify(self, code, email='member@example.com'):
        return self.post('/api/auth/otp/verify', {'email': email, 'code': code})

    def test_a_valid_code_opens_a_session(self):
        response = self.verify(self.code)

        self.assertEqual(response.status_code, 200)
        self.assert_signed_in_as(self.member)

    def test_the_member_is_returned(self):
        payload = self.body(self.verify(self.code))

        self.assertEqual(payload['email'], 'member@example.com')
        self.assertEqual(payload['display_name'], 'Bean')
        self.assertEqual(payload['status'], UserStatus.ACTIVE)
        self.assertFalse(payload['is_staff'])

    def test_the_identity_number_never_crosses_the_wire(self):
        """It is encrypted at rest and has no business in a browser."""
        self.member.capture_sa_id_number('8001015009087')
        self.member.save()

        raw = self.verify(self.code).content.decode()

        self.assertNotIn('id_number', raw)
        self.assertNotIn('8001015009087', raw)

    def test_a_wrong_code_is_refused(self):
        wrong = '000000' if self.code != '000000' else '111111'

        self.assertEqual(self.verify(wrong).status_code, 401)
        self.assert_signed_out()

    def test_surrounding_whitespace_is_tolerated(self):
        """People paste codes out of emails."""
        self.assertEqual(self.verify(f'  {self.code} ').status_code, 200)

    def test_a_code_cannot_be_spent_twice(self):
        self.assertEqual(self.verify(self.code).status_code, 200)
        self.client.post('/api/auth/logout')

        self.assertEqual(self.verify(self.code).status_code, 401)

    def test_an_unknown_address_is_refused_the_same_way(self):
        unknown = self.verify(self.code, email='nobody@example.com')
        wrong = self.verify('000000' if self.code != '000000' else '111111')

        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(self.body(unknown), self.body(wrong))

    def test_another_members_code_does_not_work(self):
        self.make_member('other@example.com')
        cache.clear()

        response = self.verify(self.code, email='other@example.com')

        self.assertEqual(response.status_code, 401)

    def test_a_member_suspended_after_the_code_was_sent_cannot_use_it(self):
        self.member.deactivate()

        self.assertEqual(self.verify(self.code).status_code, 401)


class StaffPasswordLoginTests(ApiTestCase):
    """Retained for staff, who need a password for Django admin."""

    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            email='staff@example.com', password=STAFF_PASSWORD
        )

    def login(self, email, password):
        return self.post('/api/auth/login', {'email': email, 'password': password})

    def test_correct_credentials_open_a_session(self):
        response = self.login('staff@example.com', STAFF_PASSWORD)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.body(response)['is_staff'])
        self.assert_signed_in_as(self.staff)

    def test_a_wrong_password_is_refused(self):
        self.assertEqual(self.login('staff@example.com', 'wrong').status_code, 401)
        self.assert_signed_out()

    def test_an_unknown_address_is_refused_identically(self):
        unknown = self.login('nobody@example.com', STAFF_PASSWORD)
        wrong = self.login('staff@example.com', 'wrong')

        self.assertEqual(self.body(unknown), self.body(wrong))

    def test_a_suspended_account_is_refused(self):
        self.staff.deactivate()

        self.assertEqual(self.login('staff@example.com', STAFF_PASSWORD).status_code, 401)

    def test_a_member_holding_no_password_cannot_be_signed_in_with_a_blank_one(self):
        """Members get an unusable password, which must match nothing at all."""
        self.make_member()

        self.assertEqual(self.login('member@example.com', '').status_code, 401)


class SessionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.post('/api/auth/otp/start', {'email': 'member@example.com'})
        self.post(
            '/api/auth/otp/verify',
            {'email': 'member@example.com', 'code': code_from_last_email()},
        )

    def test_me_needs_a_session(self):
        self.client.post('/api/auth/logout')

        self.assertEqual(self.get('/api/auth/me').status_code, 401)

    def test_me_returns_the_signed_in_member(self):
        self.assert_signed_in_as(self.member)

    def test_logout_ends_the_session(self):
        response = self.client.post('/api/auth/logout')

        self.assertEqual(response.status_code, 200)
        self.assert_signed_out()

    def test_logout_is_harmless_without_a_session(self):
        self.client.post('/api/auth/logout')

        self.assertEqual(self.client.post('/api/auth/logout').status_code, 200)

    def test_erasing_the_account_ends_the_live_session(self):
        """An already signed-in browser is signed out, not left to expire."""
        self.member.soft_delete()

        self.assert_signed_out()


@override_settings(**WEBAUTHN_SETTINGS)
class PasskeyEnrolmentTests(ApiTestCase):
    """Enrolment requires a session: a passkey is added by a member who has
    already proved who they are some other way."""

    def setUp(self):
        super().setUp()
        self.member = self.make_member(nickname='Bean')
        self.post('/api/auth/otp/start', {'email': 'member@example.com'})
        self.post(
            '/api/auth/otp/verify',
            {'email': 'member@example.com', 'code': code_from_last_email()},
        )

    def verified_registration(self, credential_id=b'new-credential'):
        return SimpleNamespace(
            credential_id=credential_id,
            credential_public_key=b'a-public-key',
            sign_count=0,
            aaguid='00000000-0000-0000-0000-000000000000',
            credential_backed_up=True,
            credential_device_type=SimpleNamespace(value='multi_device'),
        )

    def register(self, payload=None):
        return self.post('/api/auth/passkeys', payload or {'credential': {'id': 'x'}})

    def test_options_need_a_session(self):
        signed_out = Client()

        self.assertEqual(
            self.post('/api/auth/passkeys/options', client=signed_out).status_code, 401
        )

    def test_options_are_returned(self):
        response = self.post('/api/auth/passkeys/options')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.body(response)['options']['rp']['id'], 'localhost')

    def test_options_mint_a_user_handle_once(self):
        self.post('/api/auth/passkeys/options')
        self.post('/api/auth/passkeys/options')

        self.assertEqual(PasskeyUserHandle.objects.filter(user=self.member).count(), 1)

    def test_the_handle_is_not_the_account_id(self):
        """It syncs into a password manager, so it must not key anything else."""
        self.post('/api/auth/passkeys/options')
        handle = PasskeyUserHandle.objects.get(user=self.member)

        self.assertNotEqual(str(handle.handle), str(self.member.pk))

    def test_options_exclude_the_passkeys_already_held(self):
        self.make_passkey(self.member, b'already-here')

        payload = self.body(self.post('/api/auth/passkeys/options'))
        excluded = [wa.decode(item['id']) for item in payload['options']['excludeCredentials']]

        self.assertEqual(excluded, [b'already-here'])

    def test_options_park_a_challenge_under_the_enrolment_key(self):
        self.post('/api/auth/passkeys/options')

        self.assertIn(wa.REGISTER_CHALLENGE_KEY, self.client.session.keys())
        self.assertNotIn(wa.LOGIN_CHALLENGE_KEY, self.client.session.keys())

    def test_registering_without_a_challenge_is_refused(self):
        response = self.register()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PasskeyCredential.objects.count(), 0)

    def test_a_verified_credential_is_stored(self):
        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration', return_value=self.verified_registration()
        ):
            response = self.register({'credential': {'id': 'x'}, 'name': 'Work laptop'})

        self.assertEqual(response.status_code, 200)
        credential = PasskeyCredential.objects.get()
        self.assertEqual(credential.user, self.member)
        self.assertEqual(wa.decode(credential.credential_id), b'new-credential')
        self.assertEqual(credential.name, 'Work laptop')
        self.assertTrue(credential.backed_up)
        self.assertEqual(credential.device_type, 'multi_device')

    def test_an_unnamed_credential_gets_a_default_label(self):
        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration', return_value=self.verified_registration()
        ):
            self.register({'credential': {'id': 'x'}, 'name': '   '})

        self.assertEqual(PasskeyCredential.objects.get().name, 'Passkey')

    def test_a_long_label_is_truncated_rather_than_rejected(self):
        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration', return_value=self.verified_registration()
        ):
            self.register({'credential': {'id': 'x'}, 'name': 'z' * 200})

        self.assertEqual(len(PasskeyCredential.objects.get().name), 64)

    def test_a_credential_that_fails_verification_is_not_stored(self):
        from webauthn.helpers.exceptions import InvalidRegistrationResponse

        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration',
            side_effect=InvalidRegistrationResponse('nope'),
        ):
            response = self.register()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PasskeyCredential.objects.count(), 0)

    def test_a_credential_already_registered_is_refused(self):
        self.make_passkey(self.member, b'new-credential')
        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration', return_value=self.verified_registration()
        ):
            response = self.register()

        self.assertEqual(response.status_code, 409)
        self.assertEqual(PasskeyCredential.objects.count(), 1)

    def test_a_credential_belonging_to_someone_else_is_refused_too(self):
        """Unique across all accounts, so it cannot be claimed twice."""
        self.make_passkey(self.make_member('other@example.com'), b'new-credential')
        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration', return_value=self.verified_registration()
        ):
            self.assertEqual(self.register().status_code, 409)

    def test_the_challenge_is_spent_even_by_a_failed_enrolment(self):
        from webauthn.helpers.exceptions import InvalidRegistrationResponse

        self.put_challenge(wa.REGISTER_CHALLENGE_KEY)

        with patch(
            'app.authn.webauthn.verify_registration',
            side_effect=InvalidRegistrationResponse('nope'),
        ):
            self.register()

        self.assertNotIn(wa.REGISTER_CHALLENGE_KEY, self.client.session.keys())


@override_settings(**WEBAUTHN_SETTINGS)
class PasskeyManagementTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.other = self.make_member('other@example.com')
        self.mine = self.make_passkey(self.member, b'mine', name='Phone')
        self.theirs = self.make_passkey(self.other, b'theirs', name='Their phone')
        self.post('/api/auth/otp/start', {'email': 'member@example.com'})
        self.post(
            '/api/auth/otp/verify',
            {'email': 'member@example.com', 'code': code_from_last_email()},
        )

    def test_listing_needs_a_session(self):
        self.assertEqual(self.get('/api/auth/passkeys', client=Client()).status_code, 401)

    def test_listing_shows_only_the_members_own(self):
        payload = self.body(self.get('/api/auth/passkeys'))

        self.assertEqual([item['name'] for item in payload], ['Phone'])

    def test_the_listing_never_includes_the_public_key(self):
        raw = self.get('/api/auth/passkeys').content.decode()

        self.assertNotIn('public_key', raw)
        self.assertNotIn('credential_id', raw)

    def test_a_member_can_revoke_their_own(self):
        response = self.client.delete(f'/api/auth/passkeys/{self.mine.pk}')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PasskeyCredential.objects.filter(pk=self.mine.pk).exists())

    def test_revoking_someone_elses_is_a_404(self):
        """Not a 403: whether that id exists at all is not the caller's business."""
        response = self.client.delete(f'/api/auth/passkeys/{self.theirs.pk}')

        self.assertEqual(response.status_code, 404)
        self.assertTrue(PasskeyCredential.objects.filter(pk=self.theirs.pk).exists())

    def test_revoking_an_unknown_id_is_a_404(self):
        self.assertEqual(
            self.client.delete('/api/auth/passkeys/999999').status_code, 404
        )

    def test_revoking_needs_a_session(self):
        self.assertEqual(
            Client().delete(f'/api/auth/passkeys/{self.mine.pk}').status_code, 401
        )


@override_settings(**WEBAUTHN_SETTINGS)
class PasskeyLoginTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.credential = self.make_passkey(self.member, b'mine', sign_count=4)

    def verified_authentication(self, new_sign_count=5):
        return SimpleNamespace(new_sign_count=new_sign_count, credential_backed_up=True)

    def attempt(self, credential_id=None):
        return self.post(
            '/api/auth/login/passkey',
            {
                'email': 'member@example.com',
                'credential': {'id': credential_id or self.credential.credential_id},
            },
        )

    def test_a_full_round_trip_opens_a_session(self):
        """The first half issues the challenge; the second half spends it."""
        self.post('/api/auth/login/start', {'email': 'member@example.com'})

        with patch(
            'app.authn.webauthn.verify_authentication',
            return_value=self.verified_authentication(),
        ):
            response = self.attempt()

        self.assertEqual(response.status_code, 200)
        self.assert_signed_in_as(self.member)

    def test_an_attempt_with_no_challenge_is_refused(self):
        response = self.attempt()

        self.assertEqual(response.status_code, 400)
        self.assert_signed_out()

    def test_an_expired_challenge_is_refused(self):
        session = self.client.session
        session[wa.LOGIN_CHALLENGE_KEY] = {
            'challenge': wa.encode(b'stale'),
            'expires': (timezone.now() - timedelta(seconds=1)).timestamp(),
            'user_id': str(self.member.pk),
        }
        session.save()

        self.assertEqual(self.attempt().status_code, 400)

    def test_an_unknown_credential_is_refused(self):
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))

        response = self.attempt(credential_id=wa.encode(b'never-seen'))

        self.assertEqual(response.status_code, 401)
        self.assert_signed_out()

    def test_a_credential_belonging_to_another_account_is_refused(self):
        """The challenge is pinned to a user, so someone else's passkey cannot
        be presented against it."""
        theirs = self.make_passkey(self.make_member('other@example.com'), b'theirs')
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))

        with patch(
            'app.authn.webauthn.verify_authentication',
            return_value=self.verified_authentication(),
        ):
            response = self.attempt(credential_id=theirs.credential_id)

        self.assertEqual(response.status_code, 401)
        self.assert_signed_out()

    def test_the_two_refusals_are_indistinguishable(self):
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))
        unknown = self.attempt(credential_id=wa.encode(b'never-seen'))

        theirs = self.make_passkey(self.make_member('other@example.com'), b'theirs')
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))
        wrong_owner = self.attempt(credential_id=theirs.credential_id)

        self.assertEqual(self.body(unknown), self.body(wrong_owner))

    def test_a_signature_that_fails_verification_is_refused(self):
        from webauthn.helpers.exceptions import InvalidAuthenticationResponse

        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))

        with patch(
            'app.authn.webauthn.verify_authentication',
            side_effect=InvalidAuthenticationResponse('nope'),
        ):
            response = self.attempt()

        self.assertEqual(response.status_code, 401)
        self.assert_signed_out()

    def test_the_replay_counter_moves(self):
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))

        with patch(
            'app.authn.webauthn.verify_authentication',
            return_value=self.verified_authentication(new_sign_count=9),
        ):
            self.attempt()

        self.credential.refresh_from_db()
        self.assertEqual(self.credential.sign_count, 9)
        self.assertIsNotNone(self.credential.last_used_at)

    def test_the_challenge_is_single_use(self):
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))

        with patch(
            'app.authn.webauthn.verify_authentication',
            return_value=self.verified_authentication(),
        ):
            self.assertEqual(self.attempt().status_code, 200)
            self.client.post('/api/auth/logout')
            self.assertEqual(self.attempt().status_code, 400)

    def test_an_account_suspended_after_the_challenge_was_issued_is_refused(self):
        """Checked here as well as in login_start: a challenge issued moments
        before a suspension must not still open a session."""
        self.put_challenge(wa.LOGIN_CHALLENGE_KEY, user_id=str(self.member.pk))
        self.member.deactivate()

        with patch(
            'app.authn.webauthn.verify_authentication',
            return_value=self.verified_authentication(),
        ):
            response = self.attempt()

        self.assertEqual(response.status_code, 403)
        self.assert_signed_out()

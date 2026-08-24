"""Tests for the emailed sign-in code.

This is the only route into a new account -- a member with no passkey yet has
to get in some other way before they can enrol one -- so the code is a
first-class credential, not a back door. Three properties make a six-digit
secret defensible, and all three are invisible when they break: the code is
hashed at rest, it expires, and it is burned after a handful of wrong guesses.
A regression in any of them leaves the endpoint answering exactly as before
while the code becomes brute-forceable.

The tests are ``async def`` because the service is: Django runs an async test
method through ``async_to_sync``, inside the same transaction the surrounding
``TestCase`` opened.
"""
import re
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from app.authn import otp as otp_service
from app.accounts.models import User, UserStatus
from app.authn.models import EmailOtp

# The code as it appears in the email body: the only run of exactly six digits.
CODE_IN_EMAIL = re.compile(r'\b(\d{6})\b')


def code_from_last_email():
    """The code the member was actually sent, read back out of the message."""
    match = CODE_IN_EMAIL.search(mail.outbox[-1].body)
    assert match is not None, f'No six-digit code in:\n{mail.outbox[-1].body}'
    return match.group(1)


class CodeGenerationTests(TestCase):
    def test_code_is_the_configured_number_of_digits(self):
        for _ in range(200):
            code = EmailOtp.generate_code()
            self.assertEqual(len(code), settings.OTP_CODE_LENGTH)
            self.assertTrue(code.isdigit())

    def test_low_codes_keep_their_leading_zeros(self):
        """Truncating '000123' to '123' would narrow the space codes are drawn from.

        A tenth of all codes begin with a zero, so 500 draws that produce none
        is not luck -- it is a formatting bug.
        """
        codes = [EmailOtp.generate_code() for _ in range(500)]

        self.assertTrue(any(code.startswith('0') for code in codes))
        self.assertTrue(all(len(code) == settings.OTP_CODE_LENGTH for code in codes))

    def test_successive_codes_differ(self):
        """A constant here would be catastrophic and silent."""
        codes = {EmailOtp.generate_code() for _ in range(50)}
        self.assertGreater(len(codes), 1)

    def test_default_expiry_is_the_configured_ttl(self):
        remaining = EmailOtp.default_expiry() - timezone.now()

        self.assertAlmostEqual(
            remaining.total_seconds(), settings.OTP_TTL_SECONDS, delta=5
        )


class IssueTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com', status=UserStatus.ACTIVE, nickname='Bean'
        )

    async def test_issue_creates_exactly_one_live_code(self):
        await otp_service.issue(self.user)

        self.assertEqual(await EmailOtp.objects.acount(), 1)
        self.assertEqual(await EmailOtp.objects.usable().acount(), 1)

    async def test_the_code_is_hashed_at_rest(self):
        """A six-digit secret in plaintext is no secret in a database dump."""
        await otp_service.issue(self.user)
        code = code_from_last_email()

        stored = await EmailOtp.objects.afirst()
        self.assertNotIn(code, stored.code_hash)
        self.assertTrue(check_password(code, stored.code_hash))

    async def test_the_code_is_emailed_to_the_member(self):
        await otp_service.issue(self.user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['member@example.com'])
        self.assertIn('sign-in code', mail.outbox[0].subject)
        # The greeting uses the short name, which for this member is the nickname.
        self.assertIn('Bean', mail.outbox[0].body)

    async def test_the_email_says_how_long_the_code_lasts(self):
        await otp_service.issue(self.user)

        self.assertIn('5 minutes', mail.outbox[0].body)

    async def test_a_fresh_code_supersedes_the_previous_one(self):
        """Only ever one live code, so asking again cannot widen the target."""
        await otp_service.issue(self.user)
        first = code_from_last_email()

        await otp_service.issue(self.user)
        second = code_from_last_email()

        self.assertEqual(await EmailOtp.objects.acount(), 2)
        self.assertEqual(await EmailOtp.objects.usable().acount(), 1)
        self.assertFalse(await otp_service.verify(self.user, first))
        self.assertTrue(await otp_service.verify(self.user, second))

    async def test_superseding_does_not_touch_another_member(self):
        other = await sync_to_async(User.objects.create_user)(
            email='other@example.com', status=UserStatus.ACTIVE
        )
        await otp_service.issue(other)
        await otp_service.issue(self.user)

        self.assertEqual(
            await EmailOtp.objects.usable().filter(user=other).acount(), 1
        )


class VerifyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com', status=UserStatus.ACTIVE
        )

    async def issue_and_read(self):
        await otp_service.issue(self.user)
        return code_from_last_email()

    async def test_the_right_code_verifies(self):
        code = await self.issue_and_read()

        self.assertTrue(await otp_service.verify(self.user, code))

    async def test_a_verified_code_is_consumed(self):
        code = await self.issue_and_read()
        await otp_service.verify(self.user, code)

        otp = await EmailOtp.objects.afirst()
        self.assertIsNotNone(otp.consumed_at)
        self.assertEqual(await EmailOtp.objects.usable().acount(), 0)

    async def test_the_same_code_cannot_be_used_twice(self):
        code = await self.issue_and_read()

        self.assertTrue(await otp_service.verify(self.user, code))
        self.assertFalse(await otp_service.verify(self.user, code))

    async def test_a_wrong_code_is_refused(self):
        code = await self.issue_and_read()
        wrong = '000000' if code != '000000' else '111111'

        self.assertFalse(await otp_service.verify(self.user, wrong))

    async def test_a_wrong_code_does_not_consume_the_right_one(self):
        code = await self.issue_and_read()
        await otp_service.verify(self.user, '000000' if code != '000000' else '111111')

        self.assertTrue(await otp_service.verify(self.user, code))

    async def test_every_attempt_is_counted(self):
        code = await self.issue_and_read()
        wrong = '000000' if code != '000000' else '111111'

        await otp_service.verify(self.user, wrong)
        await otp_service.verify(self.user, wrong)

        otp = await EmailOtp.objects.afirst()
        self.assertEqual(otp.attempts, 2)

    async def test_the_right_code_is_counted_too(self):
        """The counter bounds attempts, not failures, so it moves either way."""
        code = await self.issue_and_read()
        await otp_service.verify(self.user, code)

        otp = await EmailOtp.objects.afirst()
        self.assertEqual(otp.attempts, 1)

    async def test_the_code_is_burned_after_the_attempt_limit(self):
        """Without this, six digits is a few thousand requests, not a secret."""
        code = await self.issue_and_read()
        wrong = '000000' if code != '000000' else '111111'

        for _ in range(settings.OTP_MAX_ATTEMPTS):
            self.assertFalse(await otp_service.verify(self.user, wrong))

        # The correct code no longer works: the attempts are spent, not the guesses.
        self.assertFalse(await otp_service.verify(self.user, code))

    async def test_a_burned_code_stops_being_counted(self):
        code = await self.issue_and_read()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(settings.OTP_MAX_ATTEMPTS + 1):
            await otp_service.verify(self.user, wrong)

        otp = await EmailOtp.objects.afirst()
        # Capped at the limit: once unusable the row is never loaded again.
        self.assertEqual(otp.attempts, settings.OTP_MAX_ATTEMPTS)

    async def test_an_expired_code_is_refused(self):
        await EmailOtp.objects.acreate(
            user=self.user,
            code_hash=make_password('123456'),
            expires_at=timezone.now() - timedelta(seconds=1),
        )

        self.assertFalse(await otp_service.verify(self.user, '123456'))

    async def test_a_member_with_no_code_verifies_nothing(self):
        self.assertFalse(await otp_service.verify(self.user, '123456'))

    async def test_another_members_code_does_not_work(self):
        other = await sync_to_async(User.objects.create_user)(
            email='other@example.com', status=UserStatus.ACTIVE
        )
        await otp_service.issue(other)
        code = code_from_last_email()

        self.assertFalse(await otp_service.verify(self.user, code))


class UsableQuerySetTests(TestCase):
    """``usable()`` is the single definition of 'this code still counts'."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com', status=UserStatus.ACTIVE
        )

    def make(self, **overrides):
        fields = {
            'user': self.user,
            'code_hash': make_password('123456'),
            'expires_at': EmailOtp.default_expiry(),
        }
        fields.update(overrides)
        return EmailOtp.objects.create(**fields)

    def test_a_fresh_code_is_usable(self):
        otp = self.make()
        self.assertTrue(otp.is_usable)
        self.assertEqual(EmailOtp.objects.usable().count(), 1)

    def test_a_consumed_code_is_not(self):
        otp = self.make(consumed_at=timezone.now())
        self.assertFalse(otp.is_usable)
        self.assertEqual(EmailOtp.objects.usable().count(), 0)

    def test_an_expired_code_is_not(self):
        otp = self.make(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(otp.is_usable)
        self.assertEqual(EmailOtp.objects.usable().count(), 0)

    def test_a_code_at_the_attempt_limit_is_not(self):
        otp = self.make(attempts=settings.OTP_MAX_ATTEMPTS)
        self.assertFalse(otp.is_usable)
        self.assertEqual(EmailOtp.objects.usable().count(), 0)

    def test_a_code_one_below_the_limit_still_is(self):
        otp = self.make(attempts=settings.OTP_MAX_ATTEMPTS - 1)
        self.assertTrue(otp.is_usable)
        self.assertEqual(EmailOtp.objects.usable().count(), 1)

    def test_the_property_and_the_queryset_agree(self):
        """Two definitions of the same rule, so they are checked against each other."""
        rows = [
            self.make(),
            self.make(consumed_at=timezone.now()),
            self.make(expires_at=timezone.now() - timedelta(seconds=1)),
            self.make(attempts=settings.OTP_MAX_ATTEMPTS),
        ]
        usable_pks = set(EmailOtp.objects.usable().values_list('pk', flat=True))

        for row in rows:
            with self.subTest(pk=row.pk):
                self.assertIs(row.is_usable, row.pk in usable_pks)

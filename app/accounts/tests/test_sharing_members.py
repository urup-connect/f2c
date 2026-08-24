"""Tests for the sharing member: the account somebody else creates for you.

A sharing member is the only record on this platform that a person does not make
for themselves, and almost everything worth testing here follows from that.

**They must never become able to sign in.** Today they cannot, because they hold
no email address — which is a property of the data, not of the code, and would
stop being true the moment somebody typed an address into the admin. So the
assertions go at the constraint (`sharing_member_never_signs_in`) and at
`activate()`, not at the absence of an address.

**They must never exist without a lawful basis.** The cultivator's attestation
is the club's POPIA justification for holding a third party's name and identity
number, so a registration without it must write nothing at all — asserted as an
absence of rows, because a half-written record is what this would look like if it
regressed.

**A duplicate identity number must be refused without naming the record.** The
uniqueness rule and the cultivator's need to be told the registration failed
pull against each other, and the compromise is a vague refusal. `RefusalTests`
pins the wording down, because "it says too much" is not something a functional
test notices.

**Erasure has to keep working on them.** They are the records most likely to be
erased — registered by somebody else, on a third party's word — and
`soft_delete` blanks the nickname that `sharing_member_is_complete` requires.
`ErasureTests` is what holds the constraint's exemption for erased rows in place.
"""
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from app.accounts import services
from app.accounts.models import User, UserRole, UserStatus
from app.accounts.roles import (
    SHARING_CONSENT_VERSION,
    ROLE_GROUP_NAMES,
    permissions_for,
)
from app.common.validators import luhn_is_valid


def sa_id_for(born, sequence='5009', citizenship='0'):
    """A well-formed RSA ID number encoding ``born``, check digit included.

    The same helper as ``membership/tests/support.py``, repeated rather than
    imported: a test in ``accounts`` reaching into ``membership``'s scaffolding
    would make this app's suite depend on an app that depends on it.
    """
    body = f'{born:%y%m%d}{sequence}{citizenship}8'
    for candidate in '0123456789':
        if luhn_is_valid(body + candidate):
            return body + candidate
    raise AssertionError(f'No check digit completes {body}')


ADULT_BORN = date(1988, 4, 11)
ADULT_ID = sa_id_for(ADULT_BORN)
SECOND_ADULT_ID = sa_id_for(date(1979, 11, 3), sequence='5311')
CHILD_ID = sa_id_for(date(2015, 6, 1), sequence='5422')


class SharingMemberTestCase(TestCase):
    """A cultivator who may register, and a valid submission for them to make."""

    def setUp(self):
        self.cultivator = User.objects.create_user(
            email='grower@example.com',
            nickname='GreenThumb',
            role=UserRole.CULTIVATOR,
            status=UserStatus.ACTIVE,
        )

    def submission(self, **overrides):
        fields = {
            'cultivator': self.cultivator,
            'first_name': 'Nomsa',
            'last_name': 'Dlamini',
            'nickname': 'SunLeaf',
            'id_number': ADULT_ID,
            'consent_attested': True,
        }
        fields.update(overrides)
        return fields

    def register(self, **overrides):
        return services.register_sharing_member(**self.submission(**overrides))


class RegistrationTests(SharingMemberTestCase):
    def test_a_sharing_member_is_written_with_the_role_and_status(self):
        result = self.register()

        self.assertEqual(result.user.role, UserRole.SHARING_MEMBER)
        self.assertEqual(result.user.status, UserStatus.SHARING)
        self.assertTrue(result.user.is_sharing_member)

    def test_a_sharing_member_is_not_a_member(self):
        """The club calls them a member; the platform must not confuse the two.

        They pay no subscription and agreed to no club document themselves, so
        anything keyed on ``is_member`` -- billing, document re-acceptance -- has
        to leave them out.
        """
        result = self.register()

        self.assertFalse(result.user.is_member)

    def test_a_sharing_member_holds_no_email_and_no_mobile(self):
        """There is nothing to authenticate and nowhere to send a code."""
        result = self.register()

        self.assertIsNone(result.user.email)
        self.assertEqual(result.user.mobile, '')

    def test_a_sharing_member_cannot_sign_in(self):
        """Checked where Django actually enforces it, not on the column."""
        result = self.register()

        self.assertFalse(result.user.is_active)
        self.assertFalse(result.user.has_usable_password())

    def test_a_sharing_member_holds_no_permissions(self):
        """Twice over: an empty role set, and a status that is not Active."""
        result = self.register()

        self.assertEqual(permissions_for(result.user), frozenset())

    def test_the_identity_number_is_encrypted_and_indexed(self):
        result = self.register()

        self.assertEqual(result.user.id_number, ADULT_ID)
        self.assertNotIn(ADULT_ID, result.user.id_number_encrypted)
        self.assertTrue(
            User.objects.by_id_number(ADULT_ID).filter(pk=result.user.pk).exists()
        )

    def test_the_date_of_birth_comes_off_the_document(self):
        result = self.register()

        self.assertEqual(result.user.date_of_birth, ADULT_BORN)

    def test_the_date_of_birth_is_not_marked_verified(self):
        """The cultivator attested to consent, not to having matched a document.

        Recording this as verified would make the field mean nothing on the day
        the club relies on it.
        """
        result = self.register()

        self.assertIsNone(result.user.date_of_birth_verified_at)

    def test_the_cultivator_is_recorded_on_the_record(self):
        result = self.register()

        self.assertEqual(result.user.registered_by, self.cultivator)
        self.assertEqual(
            list(self.cultivator.sharing_members.all()), [result.user]
        )

    def test_the_attestation_is_recorded_with_who_and_when(self):
        before = timezone.now()
        result = self.register()

        self.assertEqual(
            result.user.sharing_consent_attested_by, self.cultivator
        )
        self.assertGreaterEqual(result.user.sharing_consent_attested_at, before)
        self.assertEqual(
            result.user.sharing_consent_version, SHARING_CONSENT_VERSION
        )

    def test_the_plant_allocation_is_reported_rather_than_created(self):
        """Four plants, and no plant model to create them in.

        Returned so the caller does not hard-code the number, and asserted so
        that the limit members live under and the allocation a sharing member
        receives cannot drift apart unnoticed.
        """
        result = self.register()

        self.assertEqual(result.allocation, 4)
        self.assertEqual(
            result.allocation, services.SHARING_MEMBER_PLANT_ALLOCATION
        )

    def test_the_record_lands_in_the_sharing_member_group(self):
        result = self.register()

        self.assertEqual(
            list(result.user.groups.values_list('name', flat=True)),
            [ROLE_GROUP_NAMES[UserRole.SHARING_MEMBER]],
        )


class AuthorisationTests(SharingMemberTestCase):
    def test_a_member_may_not_register_one(self):
        member = User.objects.create_user(
            email='member@example.com', status=UserStatus.ACTIVE
        )

        with self.assertRaises(PermissionDenied):
            self.register(cultivator=member)

        self.assertFalse(User.objects.with_role(UserRole.SHARING_MEMBER).exists())

    def test_a_club_administrator_may_not_register_one_either(self):
        """The action belongs to cultivators. An administrator uses the admin."""
        boss = User.objects.create_user(
            email='boss@example.com',
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
        )

        with self.assertRaises(PermissionDenied):
            self.register(cultivator=boss)

    def test_a_suspended_cultivator_may_not_register_one(self):
        """Authority is gated on status, and this is where that pays off.

        Nothing in this service checks ``status``: it asks for the permission,
        and ``permissions_for`` refuses an inactive account before it looks at
        the role.
        """
        self.cultivator.deactivate()

        with self.assertRaises(PermissionDenied):
            self.register()

    def test_a_missing_cultivator_is_refused_rather_than_crashing(self):
        with self.assertRaises(PermissionDenied):
            self.register(cultivator=None)

    def test_a_superuser_may_register_one(self):
        """It asks for the permission, not for the Cultivator role.

        Django grants a superuser every permission, so this follows -- and it is
        asserted because the alternative implementation, checking
        ``role == CULTIVATOR``, would pass every other test in this class.
        """
        root = User.objects.create_superuser(
            email='root@example.com', password='Str0ng-Passphrase!'
        )

        result = self.register(cultivator=root)

        self.assertEqual(result.user.registered_by, root)


class ConsentTests(SharingMemberTestCase):
    def test_without_the_attestation_nothing_is_written(self):
        """The attestation is the lawful basis, so there is nothing to store.

        Asserted as an absence of rows: a half-written record is what a
        regression here would look like.
        """
        before = User.objects.count()

        with self.assertRaises(ValidationError) as refused:
            self.register(consent_attested=False)

        self.assertEqual(refused.exception.code, 'consent_not_attested')
        self.assertEqual(User.objects.count(), before)

    def test_the_attestation_is_checked_before_the_fields(self):
        """A submission with no lawful basis is not a submission to correct.

        The identity number here is malformed as well. Reporting the field first
        would invite a caller to fix it and resubmit, when the thing that is
        missing is the club's reason to hold any of it.
        """
        with self.assertRaises(ValidationError) as refused:
            self.register(consent_attested=False, id_number='123')

        self.assertEqual(refused.exception.code, 'consent_not_attested')

    def test_a_record_cannot_be_written_without_an_attestation_at_all(self):
        """The database backstop, reached the way a stray write would reach it.

        The service refuses first. This is what stops a fixture, a data
        migration or the admin from leaving a record the club cannot justify
        holding.
        """
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(
                nickname='Unattested',
                role=UserRole.SHARING_MEMBER,
                status=UserStatus.SHARING,
                registered_by=self.cultivator,
            )


class CompletenessTests(SharingMemberTestCase):
    def test_a_sharing_member_needs_a_cultivator(self):
        """Otherwise the stock belongs to nobody."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(
                nickname='Orphan',
                role=UserRole.SHARING_MEMBER,
                status=UserStatus.SHARING,
                sharing_consent_attested_by=self.cultivator,
                sharing_consent_attested_at=timezone.now(),
            )

    def test_a_sharing_member_needs_a_nickname(self):
        """The swap zone shows a nickname; a blank one is unnamed stock."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(
                role=UserRole.SHARING_MEMBER,
                status=UserStatus.SHARING,
                registered_by=self.cultivator,
                sharing_consent_attested_by=self.cultivator,
                sharing_consent_attested_at=timezone.now(),
            )

    def test_a_blank_nickname_is_refused_by_the_service_first(self):
        with self.assertRaises(ValidationError):
            self.register(nickname='')

    def test_the_constraint_leaves_every_other_role_alone(self):
        """None of the three other roles carries a cultivator or an attestation."""
        for role in (UserRole.ADMIN, UserRole.CULTIVATOR, UserRole.MEMBER):
            with self.subTest(role=role):
                user = User.objects.create_user(
                    email=f'{role.value}@example.com', role=role
                )
                self.assertIsNone(user.registered_by)
                self.assertIsNone(user.sharing_consent_attested_at)


class SignInTests(SharingMemberTestCase):
    def test_the_role_cannot_be_active(self):
        """"Never signs in" as a fact about the database, not a convention.

        They hold no email address today, so nothing could authenticate them --
        but that is a property of the data, and somebody adding an address in
        the admin would silently turn stock into an account.
        """
        result = self.register()

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=result.user.pk).update(
                status=UserStatus.ACTIVE, is_active=True
            )

    def test_activate_refuses_politely(self):
        """Before the constraint does, so a bulk admin action stays usable."""
        result = self.register()

        with self.assertRaises(ValueError):
            result.user.activate()

        result.user.refresh_from_db()
        self.assertEqual(result.user.status, UserStatus.SHARING)

    def test_they_can_still_be_suspended(self):
        """A sharing member registered in error has to be stoppable.

        Which is why the constraint refuses Active specifically rather than
        pinning the status to Sharing.
        """
        result = self.register()

        result.user.deactivate()

        result.user.refresh_from_db()
        self.assertEqual(result.user.status, UserStatus.SUSPENDED)


class RefusalTests(SharingMemberTestCase):
    def test_an_identity_number_already_on_file_is_refused(self):
        User.objects.create_user(
            email='member@example.com', nickname='Already'
        ).capture_sa_id_number(ADULT_ID)
        existing = User.objects.get(email='member@example.com')
        existing.capture_sa_id_number(ADULT_ID)
        existing.save()

        with self.assertRaises(services.IdentityNumberUnavailable):
            self.register()

    def test_the_refusal_does_not_say_the_person_is_a_member(self):
        """The compromise, pinned down.

        One account per identity document has to be enforced, and the cultivator
        has to be told the registration failed -- so a leak is unavoidable. What
        is avoidable is naming the record, the role or the other cultivator, and
        that is what this asserts.
        """
        member = User.objects.create_user(
            email='member@example.com', nickname='Already'
        )
        member.capture_sa_id_number(ADULT_ID)
        member.save()

        with self.assertRaises(services.IdentityNumberUnavailable) as refused:
            self.register()

        message = str(refused.exception).lower()
        # Not the bare word "member": the message names the role being
        # registered, which is the cultivator's own submission coming back to
        # them and discloses nothing. What must not appear is a claim about the
        # record that already exists, or anything identifying it.
        for leak in (
            'already', 'exists', 'is a member', 'in use', 'taken', 'duplicate',
            'cultivator', ADULT_ID, 'member@example.com', 'Already',
        ):
            with self.subTest(leak=leak):
                self.assertNotIn(leak.lower(), message)

    def test_a_second_sharing_member_cannot_share_an_identity_document(self):
        self.register()

        with self.assertRaises(services.IdentityNumberUnavailable):
            self.register(nickname='OtherLeaf')

    def test_a_taken_nickname_is_refused_and_named(self):
        """Disclosed, unlike the identity number: it is a claim against others."""
        self.register()

        with self.assertRaises(services.NicknameTaken) as refused:
            self.register(id_number=SECOND_ADULT_ID)

        self.assertEqual(refused.exception.nickname, 'SunLeaf')

    def test_a_nickname_taken_by_a_member_is_refused_too(self):
        """One namespace, so nobody in the swap zone wears another's name."""
        User.objects.create_user(email='member@example.com', nickname='SunLeaf')

        with self.assertRaises(services.NicknameTaken):
            self.register()

    def test_somebody_under_age_is_refused_on_the_document(self):
        """Cannabis. That the plants are the club's stock changes nothing."""
        with self.assertRaises(ValidationError) as refused:
            self.register(id_number=CHILD_ID, today=date(2026, 8, 24))

        self.assertEqual(refused.exception.code, 'under_age')

    def test_a_malformed_identity_number_is_refused(self):
        with self.assertRaises(ValidationError):
            self.register(id_number='1234567890123')

    def test_nothing_is_written_when_a_field_is_refused(self):
        before = User.objects.count()

        with self.assertRaises(ValidationError):
            self.register(first_name='')

        self.assertEqual(User.objects.count(), before)


class ErasureTests(SharingMemberTestCase):
    def test_a_sharing_member_can_be_erased(self):
        """The POPIA route has to work on the records most likely to need it.

        ``soft_delete`` blanks the nickname that ``sharing_member_is_complete``
        requires, so without the constraint's exemption for erased rows this
        would fail at the database.
        """
        result = self.register()

        result.user.soft_delete()

        result.user.refresh_from_db()
        self.assertEqual(result.user.nickname, '')
        self.assertEqual(result.user.first_name, '')
        self.assertFalse(result.user.has_id_number)
        self.assertIsNotNone(result.user.deleted_at)

    def test_erasure_keeps_the_cultivator_and_the_attestation(self):
        """They are the cultivator's act, not this person's personal data.

        And they are what lets the club show it had a lawful basis for having
        held the record at all -- the same argument as ``email_hash``.
        """
        result = self.register()

        result.user.soft_delete()

        result.user.refresh_from_db()
        self.assertEqual(result.user.registered_by, self.cultivator)
        self.assertEqual(
            result.user.sharing_consent_attested_by, self.cultivator
        )
        self.assertIsNotNone(result.user.sharing_consent_attested_at)

    def test_the_identity_document_is_free_to_register_again(self):
        """Erasure clears the blind index, so the person is not locked out."""
        result = self.register()
        result.user.soft_delete()

        again = self.register(nickname='NewLeaf')

        self.assertNotEqual(again.user.pk, result.user.pk)

    def test_a_cultivator_with_sharing_members_cannot_be_hard_deleted(self):
        """PROTECT, so deleting a grower does not delete people.

        The routine answer is erasure, which keeps the row -- asserted in the
        same test so the refusal reads as a redirection rather than a dead end.
        """
        self.register()

        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError), transaction.atomic():
            self.cultivator.delete()

        self.cultivator.soft_delete()
        self.assertIsNotNone(self.cultivator.deleted_at)

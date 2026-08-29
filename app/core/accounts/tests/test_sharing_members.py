"""Tests for the sharing member: a placeholder, not a person.

**C6 decided what one is, and this module is most of the evidence of it.** It
used to test a person: a name, an encrypted identity number, an age read off the
document, and a cultivator's POPIA attestation standing in for a consent the
person never gave. All of that is gone from the schema, so all of it is gone
from here.

What is left is small, and the smallness is the finding. A placeholder is a
nickname, the producer whose stock it holds, and an account that authenticates
nobody.

Four things are still worth asserting, and the first is new.

**Only the producer's own primary may create one.** Holding
``platform.register_sharing_member`` says somebody is a primary *somewhere*; it
does not say they are the primary of the farm this placeholder will belong to.
That second question is the object-level rule ``roles-and-permissions.md``
carried as risk 9 and C13 for as long as there was nothing to join against.
``AuthorisationTests`` is the first place in the codebase that makes the check,
and the shape the rest should follow.

**They must never become able to sign in.** They hold no email address, which is
a property of the data and would stop being true the moment somebody typed one
into the admin. So the assertions go at ``UserStatus.NON_AUTHENTICATING``, at the
``is_active`` constraint over it, and at ``activate()``.

**A placeholder must never accumulate personal data.** ``AbsenceTests`` asserts
what C6 removed rather than trusting it stayed removed — an identity number
quietly reappearing on one of these is a POPIA problem no functional test would
notice, because everything would still work.

**A nickname collision is still refused, and still named.** It is the one
disclosure this service makes on purpose: a nickname is a claim against other
people in the swap zone, so a taken one has to be replaced, and knowing it is
spoken for reveals nothing about who holds it. The identity-number leak that
``RefusalTests`` used to pin down is gone — dissolved rather than solved, because
no identity number is collected.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.club.membership.models import ClubMembership, MembershipStatus
from app.commerce.producers.models import ProducerRole
from app.core.accounts import services
from app.core.accounts.models import User, UserStatus
from app.core.accounts.roles import permissions_for
from f2c.testing import (
    make_account,
    make_administrator,
    make_cultivator,
    make_member,
    make_producer,
)


class SharingMemberTestCase(TestCase):
    """A producer, its primary, and a submission for them to make."""

    def setUp(self):
        self.primary, self.producer = make_cultivator(
            'grower@example.com', trading_name='Kloof Farm'
        )

    def register(self, **overrides):
        fields = {
            'actor': self.primary,
            'producer': self.producer,
            'nickname': 'SunLeaf',
        }
        fields.update(overrides)
        return services.register_sharing_member(**fields)


class RegistrationTests(SharingMemberTestCase):
    def test_a_placeholder_is_written_as_two_rows(self):
        """An account that authenticates nobody, and the club's record of it."""
        result = self.register()

        self.assertEqual(result.user.status, UserStatus.NON_AUTHENTICATING)
        self.assertEqual(result.membership.status, MembershipStatus.SHARING)
        self.assertTrue(result.user.is_sharing_member)

    def test_the_nickname_is_on_the_membership(self):
        """Where its uniqueness index lives, and where the swap zone reads it."""
        result = self.register()

        self.assertEqual(result.membership.nickname, 'SunLeaf')
        self.assertEqual(result.user.club_nickname, 'SunLeaf')

    def test_the_producer_is_recorded(self):
        """The one thing a placeholder cannot be without.

        Points at the organisation, not at the person who keyed it in, so the
        stock is not orphaned when that person leaves.
        """
        result = self.register()

        self.assertEqual(result.membership.registered_by, self.producer)

    def test_a_placeholder_cannot_sign_in(self):
        result = self.register()

        self.assertIsNone(result.user.email)
        self.assertFalse(result.user.is_active)
        self.assertFalse(result.user.has_usable_password())

    def test_a_placeholder_holds_no_permissions(self):
        """It is an identity, not an actor.

        Twice over: the membership is `SHARING` rather than active, and the
        account is not `ACTIVE`, so `permissions_for` refuses before it reaches
        either relationship.
        """
        result = self.register()
        loaded = User.objects.with_platform_roles().get(pk=result.user.pk)

        self.assertEqual(permissions_for(loaded), frozenset())

    def test_the_plant_allocation_is_reported_rather_than_created(self):
        """There is no plant model here to allocate against.

        The number is returned so a caller does not hard-code it. Under C6 it
        is also no longer obviously the right number — the limit exists per
        person, and a placeholder is not one — which is the swap zone's to
        settle.
        """
        result = self.register()

        self.assertEqual(result.allocation, services.SHARING_MEMBER_PLANT_ALLOCATION)


class AbsenceTests(SharingMemberTestCase):
    """What C6 removed, asserted so it cannot quietly come back.

    Every one of these would still *work* if it regressed. A placeholder with a
    name and an identity number breaks no feature; it is personal data collected
    for no lawful purpose, which is a problem only a test like this notices.
    """

    def test_a_placeholder_has_no_name(self):
        result = self.register()

        self.assertEqual(result.user.first_name, '')
        self.assertEqual(result.user.last_name, '')

    def test_a_placeholder_has_no_identity_number(self):
        result = self.register()

        self.assertFalse(result.user.has_id_number)
        self.assertIsNone(result.user.id_number_hash)

    def test_a_placeholder_has_no_date_of_birth(self):
        """There is no document, and nobody to be under age."""
        result = self.register()

        self.assertIsNone(result.user.date_of_birth)
        self.assertIsNone(result.user.date_of_birth_verified_at)

    def test_a_placeholder_has_no_contact_details(self):
        result = self.register()

        self.assertIsNone(result.user.email)
        self.assertEqual(result.user.mobile, '')

    def test_the_service_takes_no_identity_number_or_attestation(self):
        """The signature itself, so a caller cannot pass one by accident."""
        with self.assertRaises(TypeError):
            services.register_sharing_member(
                actor=self.primary,
                producer=self.producer,
                nickname='Leaf',
                id_number='9004115009087',
            )
        with self.assertRaises(TypeError):
            services.register_sharing_member(
                actor=self.primary,
                producer=self.producer,
                nickname='Leaf',
                consent_attested=True,
            )


class AuthorisationTests(SharingMemberTestCase):
    def test_a_member_may_not_create_one(self):
        with self.assertRaises(PermissionDenied):
            self.register(actor=make_member('member@example.com'))

    def test_a_club_administrator_may_not_create_one_either(self):
        """Creating records for other people has exactly one route.

        Granting it to administrators as well would make the club's own staff a
        second way to create accounts through the API.
        """
        with self.assertRaises(PermissionDenied):
            self.register(actor=make_administrator('boss@example.com'))

    def test_an_appointed_hand_may_not_create_one(self):
        """Only the primary. `member-roles` says so, and C28 made it sayable."""
        hand, _ = make_cultivator(
            'hand@example.com',
            producer=self.producer,
            role=ProducerRole.LIMITED,
        )
        with self.assertRaises(PermissionDenied):
            self.register(actor=hand)

    def test_the_primary_of_another_producer_may_not_create_one_here(self):
        """**The object-level half, and the point of this class.**

        This caller holds `platform.register_sharing_member` — they are a
        primary. They are not the primary of *this* farm, and before C28 there
        was no row to ask. Creating a placeholder against somebody else's stock
        is exactly what that gap allowed.
        """
        other_primary, _ = make_cultivator(
            'other@example.com', trading_name='Tygerberg'
        )

        with self.assertRaises(PermissionDenied):
            self.register(actor=other_primary)

        self.assertFalse(
            ClubMembership.objects.filter(status=MembershipStatus.SHARING).exists()
        )

    def test_a_suspended_primary_may_not_create_one(self):
        """Status gates authority before any relationship is consulted."""
        self.primary.deactivate()
        with self.assertRaises(PermissionDenied):
            self.register(actor=self.primary)

    def test_a_missing_actor_is_refused_rather_than_crashing(self):
        with self.assertRaises(PermissionDenied):
            self.register(actor=None)

    def test_a_superuser_may_create_one(self):
        """Exempt from the object-level check, as from every other one."""
        root = User.objects.create_superuser(
            email='root@example.com', password='Str0ng-Passphrase!'
        )
        result = self.register(actor=root)

        self.assertEqual(result.membership.registered_by, self.producer)


class CompletenessTests(SharingMemberTestCase):
    def test_a_placeholder_needs_a_producer(self):
        """Orphaned stock was always the real failure this guarded against."""
        with self.assertRaises(ValidationError):
            self.register(producer=None)

    def test_the_constraint_refuses_one_written_around_the_service(self):
        """The backstop for a write that never went near `services`."""
        user = make_account('ghost@example.com', status=UserStatus.NON_AUTHENTICATING)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClubMembership.objects.create(
                    user=user,
                    nickname='Orphan',
                    status=MembershipStatus.SHARING,
                    registered_by=None,
                )

    def test_the_constraint_leaves_an_ordinary_membership_alone(self):
        """It applies to sharing rows and nothing else.

        A member has no `registered_by` and must not be asked for one.
        """
        member = make_member('member@example.com', 'Thabo')

        self.assertIsNone(member.club_membership.registered_by)

    def test_a_blank_nickname_is_refused_by_the_service(self):
        """The swap zone shows a nickname; a blank one is unnamed stock."""
        with self.assertRaises(ValidationError):
            self.register(nickname='')


class SignInTests(SharingMemberTestCase):
    def test_the_account_cannot_be_active(self):
        """Said in SQL, not left to the absence of an email address.

        `is_active` is derived from `status` under a check constraint, and
        `NON_AUTHENTICATING` is not `ACTIVE` — so somebody typing an address
        into the admin cannot turn stock into a sign-in-capable account.
        """
        result = self.register()
        result.user.refresh_from_db()

        self.assertEqual(result.user.status, UserStatus.NON_AUTHENTICATING)
        self.assertFalse(result.user.is_active)

    def test_activate_refuses_politely(self):
        """So a bulk admin action says something useful instead of failing on
        an index name."""
        result = self.register()

        with self.assertRaises(ValueError) as caught:
            result.user.activate()

        self.assertIn('never signs in', str(caught.exception))

    def test_they_can_still_be_suspended(self):
        """One created in error has to be stoppable."""
        result = self.register()
        result.user.deactivate()
        result.user.refresh_from_db()

        self.assertEqual(result.user.status, UserStatus.SUSPENDED)
        self.assertFalse(result.user.is_active)


class RefusalTests(SharingMemberTestCase):
    def test_a_taken_nickname_is_refused_and_named(self):
        """The one disclosure this service makes on purpose."""
        self.register(nickname='SunLeaf')

        with self.assertRaises(services.NicknameTaken) as caught:
            self.register(nickname='SunLeaf')

        self.assertEqual(caught.exception.nickname, 'SunLeaf')

    def test_a_nickname_taken_by_a_member_is_refused_too(self):
        """One nickname namespace. Two people wearing one name in the swap zone
        is impersonation rather than a collision — which is the surviving reason
        a placeholder is a `User` row at all."""
        make_member('member@example.com', 'SunLeaf')

        with self.assertRaises(services.NicknameTaken):
            self.register(nickname='SunLeaf')

    def test_the_comparison_is_case_insensitive(self):
        self.register(nickname='SunLeaf')

        with self.assertRaises(services.NicknameTaken):
            self.register(nickname='sunleaf')

    def test_nothing_is_written_when_the_nickname_is_refused(self):
        """A half-written placeholder is what a regression would look like."""
        self.register(nickname='SunLeaf')
        before = User.objects.count()

        with self.assertRaises(services.NicknameTaken):
            self.register(nickname='SunLeaf')

        self.assertEqual(User.objects.count(), before)


class ProducerLifecycleTests(SharingMemberTestCase):
    def test_a_producer_with_placeholders_cannot_be_hard_deleted(self):
        """PROTECT on `registered_by`.

        Deleting the farm would take its placeholders' provenance with it, and
        the stock they hold would point at nothing.
        """
        self.register()

        with self.assertRaises(Exception):
            with transaction.atomic():
                self.producer.delete()

    def test_two_producers_may_each_have_placeholders(self):
        """The rows are scoped to the farm, not to the platform."""
        other = make_producer('Tygerberg')
        other_primary, _ = make_cultivator(
            'other@example.com', producer=other
        )

        self.register(nickname='Kloof-One')
        services.register_sharing_member(
            actor=other_primary, producer=other, nickname='Tygerberg-One'
        )

        self.assertEqual(
            ClubMembership.objects.filter(
                status=MembershipStatus.SHARING
            ).count(),
            2,
        )

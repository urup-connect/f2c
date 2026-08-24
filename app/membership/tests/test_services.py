"""Tests for the registration write.

Three properties dominate, and none of them is visible in a return value.

The first is that a registered member **cannot sign in**. That is the whole
point of ``PENDING_PAYMENT``, and it is asserted through the authentication
stack rather than by reading the column, because ``is_active`` is what Django
filters on and a status that failed to derive it would still look right in a
database row.

The second is that a duplicate **writes nothing and says nothing**. The
assertions are about what did not happen: no second row, and a return value
indistinguishable in shape from a success. A regression there is silent -- every
response still looks correct, and the form has quietly become a way to ask
whether a named person is a member here.

The third is that the member and their agreements are **one write**. A member
with no agreements, or an agreement against a member who does not exist, are
both worse than a failed registration.
"""
from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError

from app.accounts.models import User, UserRole, UserStatus
from app.accounts.roles import MEMBER_ACTIONS, permissions_for
from app.common import crypto
from app.documents import services as document_services
from app.documents.models import DocumentConsent
from app.membership import services

from .support import (
    ADULT_BORN,
    ADULT_ID,
    REQUIRED_DOCUMENTS,
    SECOND_ADULT_ID,
    RegistrationTestCase,
    sa_id_for,
)


def permissions_once_active(user):
    """What this account will hold when a payment activates it.

    ``permissions_for`` refuses an inactive account before it looks at the
    role, and a registration deliberately leaves one inactive -- so asking it
    directly answers "nothing" whatever role was granted, and would prove
    nothing about which one was. Flipped in memory only; nothing is saved.
    """
    user.status = UserStatus.ACTIVE
    user.is_active = True
    return permissions_for(user)


class RegisterMemberTests(RegistrationTestCase):
    def test_a_registration_lands_at_pending_payment(self):
        result = services.register_member(**self.submission())

        self.assertTrue(result.created)
        self.assertEqual(result.user.status, UserStatus.PENDING_PAYMENT)

    def test_a_registration_makes_a_member_and_only_a_member(self):
        """The one role sign-up can grant.

        Asserted against the role *and* against what it carries, because the
        second is the part that matters: a form that could hand out cultivation
        or administrative authority would be a way to claim it.
        """
        result = services.register_member(**self.submission())

        self.assertEqual(result.user.role, UserRole.MEMBER)
        self.assertEqual(
            permissions_once_active(result.user), frozenset(MEMBER_ACTIONS)
        )

    def test_a_registered_member_holds_nothing_until_payment(self):
        """PENDING_PAYMENT is not Active, so the role confers nothing yet.

        The role is on the row from the moment of registration; the authority
        arrives with the status change a payment will make.
        """
        result = services.register_member(**self.submission())

        self.assertEqual(permissions_for(result.user), frozenset())

    def test_a_registered_member_cannot_sign_in(self):
        """The requirement, checked where Django actually enforces it."""
        result = services.register_member(**self.submission())

        self.assertFalse(result.user.is_active)
        self.assertFalse(
            User.objects.active_by_email('thandiwe@example.com').exists()
        )

    def test_a_registered_member_holds_no_password(self):
        result = services.register_member(**self.submission())

        self.assertFalse(result.user.has_usable_password())

    def test_the_details_are_normalised_rather_than_stored_as_typed(self):
        result = services.register_member(
            **self.submission(
                first_name='  Thandiwe   Nomsa ',
                email='  Thandiwe@Example.COM ',
                mobile='(082) 123-4567',
            )
        )

        self.assertEqual(result.user.first_name, 'Thandiwe Nomsa')
        self.assertEqual(result.user.email, 'thandiwe@example.com')
        self.assertEqual(result.user.mobile, '+27821234567')

    def test_the_nickname_keeps_the_capitalisation_the_member_chose(self):
        result = services.register_member(**self.submission(nickname='GrowerOne'))

        self.assertEqual(result.user.nickname, 'GrowerOne')


class IdentityNumberTests(RegistrationTestCase):
    def test_the_number_is_encrypted_and_blind_indexed(self):
        result = services.register_member(**self.submission())
        stored = User.objects.get(pk=result.user.pk)

        # Never in the clear, and not equal to its own ciphertext.
        self.assertNotIn(ADULT_ID, stored.id_number_encrypted)
        self.assertEqual(stored.id_number, ADULT_ID)
        self.assertEqual(
            stored.id_number_hash,
            crypto.blind_index(ADULT_ID, User.ID_NUMBER_CONTEXT),
        )

    def test_the_date_of_birth_is_read_off_the_document(self):
        """Not retyped, so the two cannot disagree."""
        result = services.register_member(**self.submission())

        self.assertEqual(result.user.date_of_birth, ADULT_BORN)

    def test_the_date_of_birth_is_not_marked_verified(self):
        """Nobody has looked at a document; a check digit is not a verification.

        If this ever passes as verified, the field the club would rely on later
        means nothing.
        """
        result = services.register_member(**self.submission())

        self.assertIsNone(result.user.date_of_birth_verified_at)

    def test_a_malformed_number_is_refused(self):
        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(id_number='1234567890123'))

    def test_someone_under_age_is_refused_on_the_document(self):
        """The age gate is a cookie in the frontend; this is the rule server-side."""
        with self.assertRaises(ValidationError) as refused:
            services.register_member(
                **self.submission(id_number=sa_id_for(date(2015, 6, 1))),
                today=date(2026, 8, 24),
            )

        self.assertEqual(refused.exception.code, 'under_age')
        self.assertEqual(User.objects.count(), 0)

    def test_the_day_before_an_eighteenth_birthday_is_refused(self):
        born = date(2008, 8, 25)

        with self.assertRaises(ValidationError):
            services.register_member(
                **self.submission(id_number=sa_id_for(born)),
                today=date(2026, 8, 24),
            )

    def test_the_eighteenth_birthday_itself_is_accepted(self):
        born = date(2008, 8, 24)

        result = services.register_member(
            **self.submission(id_number=sa_id_for(born)),
            today=date(2026, 8, 24),
        )

        self.assertTrue(result.created)


class ConsentTests(RegistrationTestCase):
    def test_an_agreement_is_written_for_every_document(self):
        result = services.register_member(**self.submission())

        recorded = DocumentConsent.objects.filter(user=result.user)
        self.assertEqual(recorded.count(), len(REQUIRED_DOCUMENTS))
        self.assertEqual(
            {consent.version.document.slug for consent in recorded},
            set(REQUIRED_DOCUMENTS),
        )

    def test_an_agreement_records_that_it_came_from_sign_up(self):
        result = services.register_member(**self.submission())

        for consent in DocumentConsent.objects.filter(user=result.user):
            self.assertEqual(consent.source, DocumentConsent.Source.SIGNUP)

    def test_an_agreement_copies_the_digests_rather_than_joining_them(self):
        """The copy is the evidence: a later disagreement is the tamper signal."""
        result = services.register_member(**self.submission())

        for consent in DocumentConsent.objects.filter(user=result.user):
            self.assertEqual(consent.file_sha256, consent.version.sha256)
            self.assertNotEqual(consent.file_sha256, '')

    def test_a_revision_published_while_the_form_was_open_is_refused(self):
        submitted = self.consents()
        self.supersede('club-rules', label='2')

        with self.assertRaises(services.ConsentSuperseded) as refused:
            services.register_member(**self.submission(consents=submitted))

        self.assertEqual(refused.exception.documents, ['club-rules'])
        self.assertEqual(User.objects.count(), 0)

    def test_a_missing_agreement_is_refused(self):
        submitted = [
            entry for entry in self.consents() if entry['document'] != 'annexures'
        ]

        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(consents=submitted))

        self.assertEqual(User.objects.count(), 0)

    def test_a_document_with_no_published_revision_stops_registration(self):
        self.document(slug='code-of-conduct', position=3, required_at_signup=True)

        with self.assertRaises(document_services.DocumentsNotReady):
            services.register_member(**self.submission())

        self.assertEqual(User.objects.count(), 0)

    def test_the_member_and_the_agreements_are_one_write(self):
        """A member with no agreements is worse than a failed registration."""
        with patch.object(
            document_services, 'record_consents', side_effect=RuntimeError('boom')
        ):
            with self.assertRaises(RuntimeError):
                services.register_member(**self.submission())

        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(DocumentConsent.objects.count(), 0)


class NicknameTests(RegistrationTestCase):
    """A nickname collision is the one refusal a registration discloses.

    Every test here gives the second person a fresh address, identity number
    *and* mobile number. All three are duplicate keys and all three are checked
    before the nickname, so carrying any one of them over would answer with a
    silent success and never reach the nickname at all.
    """

    def newcomer(self, **overrides):
        """A second person who shares nothing with the member above."""
        return self.submission(
            email='other@example.com',
            id_number=SECOND_ADULT_ID,
            mobile='083 555 1234',
            **overrides,
        )

    def test_a_taken_nickname_is_refused(self):
        services.register_member(**self.submission())

        with self.assertRaises(services.NicknameTaken):
            services.register_member(**self.newcomer(nickname='Grower'))

    def test_case_is_not_a_way_round_it(self):
        """`Grower` and `grower` read as the same member to everyone but SQL."""
        services.register_member(**self.submission(nickname='Grower'))

        with self.assertRaises(services.NicknameTaken):
            services.register_member(**self.newcomer(nickname='GROWER'))

    def test_a_reserved_nickname_is_refused(self):
        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(nickname='support'))

    def test_a_nickname_outside_the_permitted_alphabet_is_refused(self):
        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(nickname='Grоwer'))

    def test_a_suspended_member_keeps_their_nickname(self):
        """Suspension is reversible, so their display name stays theirs."""
        first = services.register_member(**self.submission()).user
        first.deactivate()

        with self.assertRaises(services.NicknameTaken):
            services.register_member(**self.newcomer())

    def test_submitting_the_same_form_twice_is_not_a_taken_nickname(self):
        """A double click must not be told the nickname it just took is taken."""
        services.register_member(**self.submission())

        result = services.register_member(**self.submission())

        self.assertFalse(result.created)
        self.assertEqual(User.objects.count(), 1)

    def test_an_erased_member_does_not_hold_their_nickname(self):
        """Erasure blanks it, so the blank rows must not collide either."""
        first = services.register_member(**self.submission()).user
        first.soft_delete()

        result = services.register_member(**self.newcomer())

        self.assertTrue(result.created)
        self.assertEqual(result.user.nickname, 'Grower')


class DuplicateTests(RegistrationTestCase):
    def test_a_registered_address_writes_nothing(self):
        """Everything else fresh, so this tests the address and nothing else."""
        services.register_member(**self.submission())

        result = services.register_member(
            **self.submission(
                nickname='Grower2',
                id_number=SECOND_ADULT_ID,
                mobile='083 555 1234',
            )
        )

        self.assertFalse(result.created)
        self.assertIsNone(result.user)
        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_identity_number_writes_nothing(self):
        services.register_member(**self.submission())

        result = services.register_member(
            **self.submission(nickname='Grower2', email='other@example.com')
        )

        self.assertFalse(result.created)
        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_mobile_number_writes_nothing(self):
        services.register_member(**self.submission())

        result = services.register_member(
            **self.submission(
                nickname='Grower2',
                email='other@example.com',
                id_number=SECOND_ADULT_ID,
            )
        )

        self.assertFalse(result.created)
        self.assertEqual(User.objects.count(), 1)

    def test_a_registered_mobile_written_differently_is_still_a_duplicate(self):
        """Otherwise the punctuation a member happens to use decides the rule."""
        services.register_member(**self.submission(mobile='0821234567'))

        for written in ('082 123 4567', '+27821234567', '(082) 123-4567'):
            with self.subTest(written=written):
                result = services.register_member(
                    **self.submission(
                        nickname='Grower2',
                        email='other@example.com',
                        id_number=SECOND_ADULT_ID,
                        mobile=written,
                    )
                )

                self.assertFalse(result.created)
                self.assertEqual(User.objects.count(), 1)

    def test_each_of_the_three_keys_is_enough_on_its_own(self):
        """Address, identity document, handset. Any one already held is a duplicate.

        Written as one test over three keys rather than three tests, because
        what matters is that no key was left out -- and a key added later
        belongs in this list.
        """
        services.register_member(**self.submission())

        fresh = {
            'nickname': 'Grower2',
            'email': 'other@example.com',
            'id_number': SECOND_ADULT_ID,
            'mobile': '083 555 1234',
        }

        # Everything fresh but one value carried over from the member above.
        for key in ('email', 'id_number', 'mobile'):
            with self.subTest(key=key):
                overrides = dict(fresh)
                del overrides[key]

                result = services.register_member(**self.submission(**overrides))

                self.assertFalse(result.created, f'{key} did not count as a duplicate')
                self.assertEqual(User.objects.count(), 1)

    def test_all_three_fresh_is_a_new_member(self):
        """The control for the test above: nothing carried over, so a row is written."""
        services.register_member(**self.submission())

        result = services.register_member(
            **self.submission(
                nickname='Grower2',
                email='other@example.com',
                id_number=SECOND_ADULT_ID,
                mobile='083 555 1234',
            )
        )

        self.assertTrue(result.created)
        self.assertEqual(User.objects.count(), 2)

    def test_a_duplicate_writes_no_further_agreements(self):
        first = services.register_member(**self.submission()).user
        before = DocumentConsent.objects.filter(user=first).count()

        services.register_member(
            **self.submission(
                nickname='Grower2',
                id_number=SECOND_ADULT_ID,
                mobile='083 555 1234',
            )
        )

        self.assertEqual(DocumentConsent.objects.filter(user=first).count(), before)

    def test_an_erased_member_may_register_again(self):
        """`email_hash` outlives erasure and is deliberately not unique."""
        first = services.register_member(**self.submission()).user
        first.soft_delete()

        result = services.register_member(**self.submission())

        self.assertTrue(result.created)
        self.assertNotEqual(result.user.pk, first.pk)
        self.assertEqual(User.objects.count(), 2)

    def test_a_suspended_member_is_still_a_duplicate(self):
        """Suspension is reversible, so the address is still spoken for.

        A different nickname, because a suspended member keeps theirs -- which
        the nickname tests cover separately. This one is about the address.
        """
        first = services.register_member(**self.submission()).user
        first.deactivate()

        result = services.register_member(**self.submission(nickname='Grower2'))

        self.assertFalse(result.created)
        self.assertEqual(User.objects.count(), 1)


class FieldTests(RegistrationTestCase):
    def test_a_blank_name_is_refused(self):
        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(first_name='   '))

    def test_a_name_that_is_not_a_name_is_refused(self):
        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(last_name='<script>'))

    def test_a_name_the_frontend_permits_is_permitted_here(self):
        """The floor must not be narrower than the rule a member actually meets."""
        for name in ("O'Brien", 'Van der Merwe', 'Ngcobo-Zulu', 'Nkosi', 'Sr.'):
            with self.subTest(name=name):
                User.objects.all().delete()
                result = services.register_member(**self.submission(last_name=name))
                self.assertEqual(result.user.last_name, name)

    def test_a_malformed_address_is_refused(self):
        with self.assertRaises(ValidationError):
            services.register_member(**self.submission(email='not-an-address'))

    def test_a_number_that_is_not_a_handset_is_refused(self):
        for mobile in ('086 123 4567', '021 123 4567', '082 123 456'):
            with self.subTest(mobile=mobile):
                with self.assertRaises(ValidationError):
                    services.register_member(**self.submission(mobile=mobile))

    def test_a_number_written_any_accepted_way_reaches_one_stored_form(self):
        for mobile in ('0821234567', '+27 82 123 4567', '0027821234567', '082-123-4567'):
            with self.subTest(mobile=mobile):
                User.objects.all().delete()
                result = services.register_member(**self.submission(mobile=mobile))
                self.assertEqual(result.user.mobile, '+27821234567')

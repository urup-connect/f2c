"""Tests for the member record: identity, status, and erasure.

Two things here are worth testing precisely because they are invisible when they
go wrong. A denormalised ``is_active`` that drifts from ``status`` locks members
out, or lets suspended ones back in. And an erasure that misses a field leaves
personal data on a record the collective has promised to clear.

``SoftDeleteTests`` reaches into ``authn`` for the credentials erasure has to
revoke. That is the one place the two apps meet, and the assertion that all
three tables end up empty is what holds the reverse-relation contract in
``User.soft_delete`` in place.
"""
import importlib
from datetime import date

from django.apps import apps
from django.contrib.auth import authenticate
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase, TransactionTestCase

from app.accounts.models import User, UserStatus
from app.authn.models import EmailOtp, PasskeyCredential, PasskeyUserHandle
from app.common.tests import VALID_SA_ID


class UserCreationTests(TestCase):
    def test_email_is_the_identifier_and_is_lower_cased(self):
        user = User.objects.create_user(email='  Member@Example.COM ')
        self.assertEqual(user.email, 'member@example.com')
        self.assertEqual(user.get_username(), 'member@example.com')

    def test_case_variants_cannot_both_register(self):
        User.objects.create_user(email='member@example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email='MEMBER@EXAMPLE.COM')

    def test_new_member_starts_pending_and_cannot_sign_in(self):
        user = User.objects.create_user(email='member@example.com')
        self.assertEqual(user.status, UserStatus.PENDING)
        self.assertFalse(user.is_active)

    def test_member_without_password_cannot_be_authenticated(self):
        User.objects.create_user(email='member@example.com', status=UserStatus.ACTIVE)
        self.assertIsNone(
            authenticate(username='member@example.com', password='')
        )

    def test_superuser_is_active_staff(self):
        user = User.objects.create_superuser(
            email='staff@example.com', password='Str0ng-Passphrase!'
        )
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email='  ')

    def test_primary_key_is_time_ordered(self):
        """UUIDv7, so successive rows sort in creation order."""
        first = User.objects.create_user(email='a@example.com')
        second = User.objects.create_user(email='b@example.com')
        self.assertLess(str(first.id), str(second.id))

class StatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com',
            password='Str0ng-Passphrase!',
            status=UserStatus.ACTIVE,
        )

    def test_is_active_follows_status(self):
        """Every status, not a list of them.

        Walking the whole enum rather than naming four values is what stops a
        status added later -- Pending payment was -- from arriving with nothing
        asserting whether it grants access. Exactly one value may.
        """
        for status in UserStatus:
            with self.subTest(status=status):
                self.user.status = status
                self.user.save()
                self.user.refresh_from_db()
                self.assertIs(self.user.is_active, status == UserStatus.ACTIVE)

    def test_only_an_active_account_is_reachable_for_sign_in(self):
        """The lookup every sign-in route goes through, over every status.

        ``active_by_email`` is what ``authn`` resolves an address with, so this
        is the same rule as the test above seen from where it is enforced.
        """
        for status in UserStatus:
            with self.subTest(status=status):
                self.user.status = status
                self.user.save()

                found = User.objects.active_by_email('member@example.com').exists()

                self.assertIs(found, status == UserStatus.ACTIVE)

    def test_partial_save_still_syncs_is_active(self):
        self.user.status = UserStatus.SUSPENDED
        self.user.save(update_fields=['status'])
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_bulk_update_that_skips_the_model_is_refused(self):
        """The check constraint is the backstop for writes that bypass save()."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=self.user.pk).update(status=UserStatus.SUSPENDED)

    def test_only_an_active_account_authenticates(self):
        self.assertIsNotNone(
            authenticate(username='member@example.com', password='Str0ng-Passphrase!')
        )
        self.user.deactivate()
        self.assertIsNone(
            authenticate(username='member@example.com', password='Str0ng-Passphrase!')
        )

    def test_active_by_email_ignores_non_active_accounts(self):
        self.assertTrue(User.objects.active_by_email('MEMBER@example.com').exists())
        self.user.deactivate()
        self.assertFalse(User.objects.active_by_email('member@example.com').exists())

    def test_updated_at_moves_on_a_full_save(self):
        before = self.user.updated_at
        self.user.nickname = 'Bean'
        self.user.save()
        self.assertGreater(self.user.updated_at, before)

class IdNumberTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='member@example.com')

    def test_round_trip_through_the_property(self):
        self.user.id_number = VALID_SA_ID
        self.user.save()
        self.assertEqual(User.objects.get(pk=self.user.pk).id_number, VALID_SA_ID)

    def test_plaintext_is_not_in_the_column(self):
        self.user.id_number = VALID_SA_ID
        self.user.save()
        stored = User.objects.values_list('id_number_encrypted', flat=True).get(
            pk=self.user.pk
        )
        self.assertNotIn(VALID_SA_ID, stored)

    def test_lookup_by_blind_index(self):
        self.user.id_number = VALID_SA_ID
        self.user.save()
        self.assertEqual(User.objects.by_id_number(VALID_SA_ID).get(), self.user)
        self.assertEqual(User.objects.by_id_number('800101 5009 087').get(), self.user)

    def test_one_account_per_id_number(self):
        self.user.id_number = VALID_SA_ID
        self.user.save()
        other = User.objects.create_user(email='other@example.com')
        other.id_number = VALID_SA_ID
        with self.assertRaises(IntegrityError), transaction.atomic():
            other.save()

    def test_capture_sa_id_fills_birth_date_from_the_document(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()
        self.assertEqual(self.user.date_of_birth, date(1980, 1, 1))
        self.assertIsNotNone(self.user.date_of_birth_verified_at)

    def test_capture_rejects_a_bad_number_without_storing_it(self):
        with self.assertRaises(ValidationError):
            self.user.capture_sa_id_number('8001015009088')
        self.assertFalse(self.user.has_id_number)

    def test_clearing_removes_both_columns(self):
        self.user.id_number = VALID_SA_ID
        self.user.save()
        self.user.id_number = ''
        self.user.save()
        self.assertFalse(self.user.has_id_number)
        self.assertIsNone(self.user.id_number_hash)

    def test_two_accounts_may_both_hold_no_id_number(self):
        """The unique index is on a nullable column, so blanks do not collide."""
        User.objects.create_user(email='other@example.com')
        self.assertEqual(User.objects.filter(id_number_hash__isnull=True).count(), 2)

class SoftDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com',
            password='Str0ng-Passphrase!',
            first_name='Craig',
            last_name='Mabaso',
            nickname='Bean',
            status=UserStatus.ACTIVE,
        )
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

        PasskeyCredential.objects.create(
            user=self.user, credential_id='cred-1', public_key='key'
        )
        EmailOtp.objects.create(
            user=self.user,
            code_hash='hashed',
            expires_at=EmailOtp.default_expiry(),
        )
        PasskeyUserHandle.objects.create(user=self.user)

    def test_identifying_fields_are_cleared(self):
        self.user.soft_delete()
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')
        self.assertEqual(self.user.last_name, '')
        self.assertEqual(self.user.nickname, '')
        self.assertIsNone(self.user.email)
        self.assertFalse(self.user.has_id_number)
        self.assertIsNone(self.user.id_number_hash)

    def test_status_and_timestamps_move(self):
        before = self.user.updated_at
        self.user.soft_delete()
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, UserStatus.INACTIVE)
        self.assertFalse(self.user.is_active)
        self.assertIsNotNone(self.user.deleted_at)
        self.assertGreater(self.user.updated_at, before)

    def test_the_row_survives(self):
        pk = self.user.pk
        self.user.soft_delete()
        self.assertTrue(User.objects.filter(pk=pk).exists())

    def test_email_digest_outlives_the_address(self):
        self.user.soft_delete()
        self.user.refresh_from_db()
        self.assertIsNone(self.user.email)
        self.assertTrue(self.user.email_hash)
        self.assertTrue(User.objects.has_been_seen('member@example.com'))

    def test_the_address_can_be_registered_again(self):
        self.user.soft_delete()
        returning = User.objects.create_user(email='member@example.com')
        self.assertNotEqual(returning.pk, self.user.pk)

    def test_credentials_are_revoked(self):
        self.user.soft_delete()
        self.assertEqual(PasskeyCredential.objects.count(), 0)
        self.assertEqual(EmailOtp.objects.count(), 0)
        self.assertEqual(PasskeyUserHandle.objects.count(), 0)

    def test_live_sessions_are_cut(self):
        client = Client()
        self.assertTrue(
            client.login(username='member@example.com', password='Str0ng-Passphrase!')
        )
        self.assertEqual(Session.objects.count(), 1)
        self.user.soft_delete()
        self.assertEqual(Session.objects.count(), 0)

    def test_the_account_cannot_sign_in_afterwards(self):
        self.user.soft_delete()
        self.assertIsNone(
            authenticate(username='member@example.com', password='Str0ng-Passphrase!')
        )
        self.assertFalse(User.objects.active_by_email('member@example.com').exists())

    def test_erased_account_cannot_be_reactivated(self):
        self.user.soft_delete()
        with self.assertRaises(ValueError):
            self.user.activate()

    def test_unsaved_user_cannot_be_erased(self):
        with self.assertRaises(ValueError):
            User(email='ghost@example.com').soft_delete()

class DeactivateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com',
            password='Str0ng-Passphrase!',
            first_name='Craig',
            status=UserStatus.ACTIVE,
        )

    def test_deactivate_keeps_the_data_and_ends_sessions(self):
        client = Client()
        client.login(username='member@example.com', password='Str0ng-Passphrase!')
        self.user.deactivate()
        self.user.refresh_from_db()
        self.assertEqual(self.user.status, UserStatus.SUSPENDED)
        self.assertEqual(self.user.first_name, 'Craig')
        self.assertIsNone(self.user.deleted_at)
        self.assertEqual(Session.objects.count(), 0)

    def test_a_suspended_account_can_come_back(self):
        self.user.deactivate()
        self.user.activate()
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

class DisplayNameTests(TestCase):
    def test_falls_back_in_order(self):
        user = User.objects.create_user(email='member@example.com')
        self.assertEqual(user.display_name, 'member@example.com')
        user.first_name, user.last_name = 'Craig', 'Mabaso'
        self.assertEqual(user.display_name, 'Craig Mabaso')
        user.nickname = 'Bean'
        self.assertEqual(user.display_name, 'Bean')

    def test_an_erased_account_still_has_something_to_print(self):
        user = User.objects.create_user(email='member@example.com')
        user.soft_delete()
        self.assertEqual(user.display_name, 'Member')
        self.assertIn('Erased member', str(user))


class MobileNumberTests(TestCase):
    """One stored form, whatever form it arrived in.

    The point is not the formatting. It is that the same handset written two
    ways must not become two members, and that the column cannot end up holding
    something the rule would refuse.
    """

    def test_every_accepted_form_reaches_the_same_stored_value(self):
        for written in (
            '0821234567',
            '082 123 4567',
            '(082) 123-4567',
            '+27821234567',
            '+27 82 123 4567',
            '0027821234567',
            '27821234567',
        ):
            with self.subTest(written=written):
                user = User(email='member@example.com', mobile=written)
                user.save()
                self.assertEqual(user.mobile, '+27821234567')
                user.delete()

    def test_a_number_that_is_not_a_handset_is_refused_on_save(self):
        """Loudly, rather than stored unnormalised. See User.save."""
        for written in ('086 123 4567', '021 123 4567', '082 123 456', 'not a number'):
            with self.subTest(written=written):
                with self.assertRaises(ValidationError):
                    User(email='member@example.com', mobile=written).save()

    def test_no_number_is_allowed(self):
        """Staff have none, and neither does an erased member."""
        user = User.objects.create_user(email='member@example.com')

        self.assertEqual(user.mobile, '')

    def test_erasure_takes_the_number_with_it(self):
        user = User.objects.create_user(
            email='member@example.com', mobile='0821234567'
        )

        user.soft_delete()

        self.assertEqual(user.mobile, '')

    def test_two_members_cannot_share_a_handset(self):
        """One handset, one member -- the club's rule, enforced by the database."""
        User.objects.create_user(email='one@example.com', mobile='0821234567')

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email='two@example.com', mobile='0821234567')

    def test_punctuation_is_not_a_way_round_it(self):
        """The reason the column is normalised before the index sees it.

        `082 123 4567` and `+27821234567` are one handset. A unique index over
        the raw text a member typed would let every other spelling through.
        """
        User.objects.create_user(email='one@example.com', mobile='0821234567')

        for written in ('082 123 4567', '+27821234567', '(082) 123-4567', '0027821234567'):
            with self.subTest(written=written):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    User.objects.create_user(email='two@example.com', mobile=written)

    def test_blank_numbers_do_not_collide(self):
        """Staff have none, and erasure blanks the field."""
        User.objects.create_user(email='one@example.com')
        User.objects.create_user(email='two@example.com')

        self.assertEqual(User.objects.filter(mobile='').count(), 2)

    def test_erasing_a_member_frees_their_number(self):
        first = User.objects.create_user(email='one@example.com', mobile='0821234567')
        first.soft_delete()

        second = User.objects.create_user(email='two@example.com', mobile='0821234567')

        self.assertEqual(second.mobile, '+27821234567')

    def test_the_manager_answers_the_same_question_as_the_constraint(self):
        """A queryset and the database must not disagree about who holds what."""
        User.objects.create_user(email='one@example.com', mobile='0821234567')

        self.assertTrue(User.objects.by_mobile('0821234567').exists())
        self.assertTrue(User.objects.by_mobile('+27 82 123 4567').exists())
        self.assertFalse(User.objects.by_mobile('0835551234').exists())

    def test_a_number_the_rule_refuses_is_held_by_nobody(self):
        """Asking who holds a malformed number is not the same as refusing it."""
        User.objects.create_user(email='one@example.com', mobile='0821234567')

        for written in ('', '   ', 'not a number', '086 123 4567'):
            with self.subTest(written=written):
                self.assertFalse(User.objects.by_mobile(written).exists())


class NicknameUniquenessTests(TestCase):
    """A nickname is an identity claim against other members, so it is unique.

    Case-insensitively, because ``Grower`` and ``grower`` read as the same
    person to everyone but the database.
    """

    def test_the_same_nickname_cannot_be_taken_twice(self):
        User.objects.create_user(email='one@example.com', nickname='Grower')

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email='two@example.com', nickname='Grower')

    def test_case_is_not_a_way_round_it(self):
        User.objects.create_user(email='one@example.com', nickname='Grower')

        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(email='two@example.com', nickname='GROWER')

    def test_the_capitalisation_the_member_chose_is_what_is_stored(self):
        user = User.objects.create_user(email='one@example.com', nickname='GrowerOne')

        self.assertEqual(user.nickname, 'GrowerOne')

    def test_blank_nicknames_do_not_collide(self):
        """Staff have none, and erasure blanks the field."""
        User.objects.create_user(email='one@example.com')
        User.objects.create_user(email='two@example.com')

        self.assertEqual(User.objects.filter(nickname='').count(), 2)

    def test_erasing_a_member_frees_their_nickname(self):
        first = User.objects.create_user(email='one@example.com', nickname='Grower')
        first.soft_delete()

        second = User.objects.create_user(email='two@example.com', nickname='Grower')

        self.assertEqual(second.nickname, 'Grower')

    def test_the_manager_answers_the_same_question_as_the_constraint(self):
        """A queryset and the database must not disagree about who holds what."""
        User.objects.create_user(email='one@example.com', nickname='Grower')

        self.assertTrue(User.objects.nickname_is_taken('grower'))
        self.assertTrue(User.objects.nickname_is_taken('  GROWER '))
        self.assertFalse(User.objects.nickname_is_taken('Grower2'))
        self.assertFalse(User.objects.nickname_is_taken('   '))

    def test_a_member_does_not_hold_their_nickname_against_themselves(self):
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        self.assertFalse(
            User.objects.nickname_is_taken('Grower', exclude_pk=user.pk)
        )


class MobileDuplicateGuardTests(TransactionTestCase):
    """The check that runs in front of the mobile constraint in migration 0003.

    It exists so a deploy against a database that already holds a shared
    handset fails with a sentence somebody can act on, rather than with an
    ``IntegrityError`` naming an index. That makes it a *failure* path, which is
    the kind most likely to be wrong and least likely to be noticed -- so it is
    tested, and tested by actually creating the state it is meant to catch.

    Creating that state means dropping the constraint first, because the whole
    point of the constraint is that this state cannot exist while it is there.
    ``TransactionTestCase`` rather than ``TestCase``: schema changes inside a
    transaction that is rolled back leave SQLite's table definition in a state
    the rest of the suite would inherit.
    """

    #: Imported by path, because a module whose name starts with a digit cannot
    #: be written as a normal import statement.
    guard = staticmethod(
        importlib.import_module(
            'app.accounts.migrations.0003_mobile_unique'
        ).refuse_existing_duplicates
    )

    def setUp(self):
        super().setUp()
        # `user_mobile_key_unique` since 0007 moved the rule off `mobile` and
        # onto the derived `mobile_key`, because the conditional index this used
        # to be is one MySQL will not build. The guard under test is still 0003's
        # and still counts duplicates on `mobile` itself, which is the column it
        # was written against. `design/backend.md` section 8.2.
        self.constraint = next(
            constraint
            for constraint in User._meta.constraints
            if constraint.name == 'user_mobile_key_unique'
        )

    def without_the_constraint(self):
        """A context in which two accounts may share a handset, as before 0003."""
        return _DroppedConstraint(self.constraint)

    def test_it_passes_when_no_number_is_shared(self):
        User.objects.create_user(email='one@example.com', mobile='0821234567')
        User.objects.create_user(email='two@example.com', mobile='0835551234')

        # Raises if it fires. No assertion needed beyond not raising.
        self.guard(apps, None)

    def test_it_passes_when_several_accounts_hold_no_number(self):
        """Staff and erased members. The constraint excludes blanks; so must this."""
        User.objects.create_user(email='one@example.com')
        User.objects.create_user(email='two@example.com')
        User.objects.create_user(email='three@example.com')

        self.guard(apps, None)

    def test_it_refuses_when_two_accounts_share_a_handset(self):
        with self.without_the_constraint():
            User.objects.create_user(email='one@example.com', mobile='0821234567')
            User.objects.create_user(email='two@example.com', mobile='082 123 4567')

            with self.assertRaises(RuntimeError) as refused:
                self.guard(apps, None)

        self.assertIn('more than one account', str(refused.exception))

    def test_the_refusal_never_names_a_number(self):
        """A migration that printed one would write it into every deploy log."""
        with self.without_the_constraint():
            User.objects.create_user(email='one@example.com', mobile='0821234567')
            User.objects.create_user(email='two@example.com', mobile='0821234567')

            with self.assertRaises(RuntimeError) as refused:
                self.guard(apps, None)

        message = str(refused.exception)
        self.assertNotIn('+27821234567', message)
        self.assertNotIn('0821234567', message)
        self.assertNotIn('821234567', message)

    def test_it_counts_numbers_rather_than_accounts(self):
        """Three accounts over two numbers is two clashes to resolve, not three."""
        with self.without_the_constraint():
            User.objects.create_user(email='one@example.com', mobile='0821234567')
            User.objects.create_user(email='two@example.com', mobile='0821234567')
            User.objects.create_user(email='three@example.com', mobile='0821234567')
            User.objects.create_user(email='four@example.com', mobile='0835551234')
            User.objects.create_user(email='five@example.com', mobile='0835551234')

            with self.assertRaises(RuntimeError) as refused:
                self.guard(apps, None)

        self.assertIn('2 mobile number(s)', str(refused.exception))


class _DroppedConstraint:
    """Removes a constraint for the duration of a block, then puts it back.

    Only for the guard tests above, which have to create the state the
    constraint exists to prevent.

    **It hides the constraint from the model as well as from the schema**, and
    that is not belt and braces. SQLite cannot drop a table-level constraint in
    place: Django rebuilds the whole table and regenerates its definition from
    ``model._meta``, so a constraint still declared there comes straight back and
    ``remove_constraint`` is a no-op that raises nothing. The rows this context
    exists to create then fail on a constraint the caller believes it dropped.

    This did not arise while the constraint carried a ``condition``, because a
    partial unique constraint is a separate ``CREATE UNIQUE INDEX`` and dropping
    one is a ``DROP INDEX`` that never consults the model. Migration 0007 made it
    unconditional -- MySQL builds no partial index (``design/backend.md`` section
    8.2) -- and that changed how it is dropped.
    """

    def __init__(self, constraint):
        self.constraint = constraint

    def _without_the_constraint(self):
        return [
            constraint
            for constraint in User._meta.constraints
            if constraint.name != self.constraint.name
        ]

    @staticmethod
    def _clear_rebuild_leftovers():
        """Drop the ``new__`` tables SQLite's table rebuild leaves behind.

        The rebuild creates a shadow copy of the table and of every
        many-to-many through table beside it -- ``new__accounts_user_groups``
        and ``new__accounts_user_user_permissions`` here -- and does not remove
        the latter two. One rebuild is fine; the second fails with *table
        already exists*, and this context manager does two.

        Only ever true of SQLite, which is the only backend that rebuilds a
        table to change a constraint.
        """
        if connection.vendor != 'sqlite':
            return
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name LIKE 'new\\_\\_%' ESCAPE '\\'"
            )
            leftovers = [name for (name,) in cursor.fetchall()]
            for name in leftovers:
                cursor.execute(f'DROP TABLE "{name}"')

    def __enter__(self):
        self.declared = User._meta.constraints
        # Before the schema edit, because the table rebuild reads this.
        User._meta.constraints = self._without_the_constraint()
        self._clear_rebuild_leftovers()
        with connection.schema_editor() as editor:
            editor.remove_constraint(User, self.constraint)
        return self

    def __exit__(self, *exc_info):
        User.objects.all().delete()
        User._meta.constraints = self.declared
        self._clear_rebuild_leftovers()
        with connection.schema_editor() as editor:
            editor.add_constraint(User, self.constraint)
        self._clear_rebuild_leftovers()
        return False

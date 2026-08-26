"""The two uniqueness keys, and the constraints that keep them honest.

``design/backend.md`` section 8.2. ``nickname_key`` and ``mobile_key`` exist
because the rules they carry used to be partial unique indexes, which MySQL will
not build and Django omits without saying so. Moving a rule onto a derived column
buys portability and takes on the risk every denormalised column has: it can go
stale, and a stale uniqueness key is worse than a missing one, because a member
renamed by hand still occupies their old name and can be handed somebody else's.

So the assertions here come in three kinds, and the third is the one that matters
most:

* the keys are derived on every write, including a partial save;
* the rules they carry are enforced -- case-insensitively for the nickname, and
  with any number of blanks allowed to coexist;
* **a write that goes around ``save`` is refused by the database.** Those tests
  use a raw queryset ``.update()`` deliberately, because that is the write the
  check constraints exist for, and it is the only way to know the rule is in the
  schema rather than only in Python.

One of those tests would have passed against a constraint that could never fire.
The first version of ``live_for_user_matches_status`` in ``payments`` compared a
nullable column with ``=``, and a SQL comparison against null is *unknown* --
which a ``CHECK`` treats as satisfied. The same trap applies to both constraints
here, and ``test_a_stale_*`` is what closes it.
"""
from django.db import IntegrityError, models, transaction
from django.test import TestCase

from ..models import User


class NicknameKeyTests(TestCase):
    def test_the_key_is_the_folded_nickname(self):
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        self.assertEqual(user.nickname_key, 'grower')

    def test_a_blank_nickname_leaves_a_null_key(self):
        """A null, not an empty string. It is what lets blanks coexist."""
        user = User.objects.create_user(email='one@example.com')

        self.assertIsNone(user.nickname_key)

    def test_the_key_follows_a_rename(self):
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        user.nickname = 'Kloof'
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.nickname_key, 'kloof')

    def test_the_key_follows_a_partial_save(self):
        """Where a derived column normally gets left behind."""
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        user.nickname = 'Kloof'
        user.save(update_fields=['nickname'])

        user.refresh_from_db()
        self.assertEqual(user.nickname_key, 'kloof')

    def test_a_nickname_is_trimmed_before_it_is_stored(self):
        """So that the key really is ``LOWER(nickname)``, which is what the
        check constraint compares. Without this the constraint would refuse the
        model's own write."""
        user = User.objects.create_user(email='one@example.com', nickname='  Grower  ')

        self.assertEqual(user.nickname, 'Grower')
        self.assertEqual(user.nickname_key, 'grower')

    def test_two_accounts_cannot_share_a_nickname(self):
        User.objects.create_user(email='one@example.com', nickname='Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(email='two@example.com', nickname='Grower')

    def test_the_comparison_is_case_insensitive(self):
        """`Grower` and `grower` read as the same person to everyone but the
        database."""
        User.objects.create_user(email='one@example.com', nickname='Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(email='two@example.com', nickname='grower')

    def test_any_number_of_accounts_may_hold_no_nickname(self):
        """Staff have none, and erasure blanks it. This is the case the old
        partial index used a condition for, and the condition is what MySQL
        could not build."""
        User.objects.create_user(email='one@example.com')
        User.objects.create_user(email='two@example.com')
        User.objects.create_user(email='three@example.com')

        self.assertEqual(User.objects.filter(nickname_key__isnull=True).count(), 3)

    def test_erasure_frees_the_nickname(self):
        user = User.objects.create_user(email='one@example.com', nickname='Grower')
        user.soft_delete()

        user.refresh_from_db()
        self.assertIsNone(user.nickname_key)
        # And the name is available again.
        User.objects.create_user(email='two@example.com', nickname='Grower')

    def test_a_stale_key_is_refused_by_the_database(self):
        """The backstop. A raw update is the write this constraint exists for.

        Without it, renaming a member with a queryset would leave them holding
        their old name for uniqueness purposes while displaying the new one --
        and every read goes through the key, so nothing would show it.
        """
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.filter(pk=user.pk).update(nickname='Kloof')

    def test_a_null_key_beside_a_nickname_is_refused(self):
        """The three-valued-logic case. A CHECK passes when its condition is
        unknown, and a comparison against null is unknown -- so this needs the
        explicit null test in the constraint to fail at all."""
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.filter(pk=user.pk).update(nickname_key=None)

    def test_by_nickname_matches_what_the_constraint_indexes(self):
        """A queryset and the database must not disagree about who holds a name."""
        user = User.objects.create_user(email='one@example.com', nickname='Grower')

        self.assertEqual(list(User.objects.by_nickname('  GROWER ')), [user])
        self.assertTrue(User.objects.nickname_is_taken('grower'))
        self.assertFalse(User.objects.nickname_is_taken('kloof'))


class MobileKeyTests(TestCase):
    def test_the_key_mirrors_the_normalised_number(self):
        user = User.objects.create_user(email='one@example.com', mobile='082 123 4567')

        self.assertEqual(user.mobile, '+27821234567')
        self.assertEqual(user.mobile_key, '+27821234567')

    def test_a_blank_number_leaves_a_null_key(self):
        user = User.objects.create_user(email='one@example.com')

        self.assertIsNone(user.mobile_key)

    def test_the_key_follows_a_partial_save(self):
        user = User.objects.create_user(email='one@example.com', mobile='0821234567')

        user.mobile = '0835551234'
        user.save(update_fields=['mobile'])

        user.refresh_from_db()
        self.assertEqual(user.mobile_key, '+27835551234')

    def test_two_accounts_cannot_share_a_handset_however_it_is_typed(self):
        User.objects.create_user(email='one@example.com', mobile='0821234567')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    email='two@example.com', mobile='+27 82 123 4567'
                )

    def test_any_number_of_accounts_may_hold_no_number(self):
        User.objects.create_user(email='one@example.com')
        User.objects.create_user(email='two@example.com')

        self.assertEqual(User.objects.filter(mobile_key__isnull=True).count(), 2)

    def test_a_stale_key_is_refused_by_the_database(self):
        user = User.objects.create_user(email='one@example.com', mobile='0821234567')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.filter(pk=user.pk).update(mobile='+27835551234')

    def test_a_null_key_beside_a_number_is_refused(self):
        user = User.objects.create_user(email='one@example.com', mobile='0821234567')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.filter(pk=user.pk).update(mobile_key=None)


class PortabilityTests(TestCase):
    """That the rules are stated in a form every backend actually builds.

    This is the test the whole of section 8 is for. It asserts the *shape* of
    the constraints rather than their effect, because the effect is identical on
    SQLite whether or not MySQL could build them -- so nothing else in this
    suite can tell the difference, and the suite runs on SQLite.
    """

    def unique_constraints(self):
        return [
            constraint
            for constraint in User._meta.constraints
            if isinstance(constraint, models.UniqueConstraint)
        ]

    def test_no_unique_constraint_is_a_partial_index(self):
        conditional = [
            constraint.name
            for constraint in self.unique_constraints()
            if constraint.condition is not None
        ]

        self.assertEqual(conditional, [])

    def test_no_unique_constraint_is_an_expression_index(self):
        expressions = [
            constraint.name
            for constraint in self.unique_constraints()
            if constraint.expressions
        ]

        self.assertEqual(expressions, [])

    def test_the_rules_are_still_there(self):
        """Guarding the two tests above, which would also pass if somebody
        deleted the constraints rather than making them portable."""
        names = {constraint.name for constraint in self.unique_constraints()}

        self.assertIn('user_nickname_key_unique', names)
        self.assertIn('user_mobile_key_unique', names)

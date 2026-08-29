"""The derived uniqueness keys, and the constraints that keep them honest.

**There are five of these now, and they are on four different tables.** This
module covers the two that started it — ``mobile_key`` on ``User`` and
``nickname_key``, which moved to ``membership.ClubMembership`` under C27 — plus
a portability check that sweeps every model rather than only ``User``. Sweeping
is the point: ``live_for_user``, ``primary_for_producer`` and
``trading_name_key`` were all written after this module, each using the same
trick, and a per-model test would have covered none of them.

``design/backend.md`` section 8.2. These columns exist
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
which a ``CHECK`` treats as satisfied. The same trap applies to the constraints
here, and ``test_a_null_key_beside_*`` is what closes it.
"""
from django.apps import apps
from django.db import IntegrityError, models, transaction
from django.test import TestCase

from app.club.membership.models import ClubMembership
from f2c.testing import make_account, make_member

from ..models import User


class NicknameKeyTests(TestCase):
    """The nickname key, which lives on the membership since C27.

    It is a property of belonging to the club, not of being a person — a
    produce-market customer has a name and no nickname — so the column, its
    unique index and its check constraint all moved to ``ClubMembership``
    together. The rules are unchanged; only the table is different.
    """

    def membership(self, email, nickname):
        return make_member(email, nickname).club_membership

    def test_the_key_is_the_folded_nickname(self):
        membership = self.membership('one@example.com', 'Grower')

        self.assertEqual(membership.nickname_key, 'grower')

    def test_a_blank_nickname_leaves_a_null_key(self):
        """A null, not an empty string. It is what lets blanks coexist."""
        membership = ClubMembership.objects.create(
            user=make_account('one@example.com'), nickname=''
        )

        self.assertIsNone(membership.nickname_key)

    def test_the_key_follows_a_rename(self):
        membership = self.membership('one@example.com', 'Grower')

        membership.nickname = 'Kloof'
        membership.save()

        membership.refresh_from_db()
        self.assertEqual(membership.nickname_key, 'kloof')

    def test_the_key_follows_a_partial_save(self):
        """Where a derived column normally gets left behind."""
        membership = self.membership('one@example.com', 'Grower')

        membership.nickname = 'Kloof'
        membership.save(update_fields=['nickname'])

        membership.refresh_from_db()
        self.assertEqual(membership.nickname_key, 'kloof')

    def test_a_nickname_is_trimmed_before_it_is_stored(self):
        """So that the key really is ``LOWER(nickname)``, which is what the
        check constraint compares. Without this the constraint would refuse the
        model's own write."""
        membership = self.membership('one@example.com', ' Grower ')

        self.assertEqual(membership.nickname, 'Grower')
        self.assertEqual(membership.nickname_key, 'grower')

    def test_two_accounts_cannot_share_a_nickname(self):
        make_member('one@example.com', 'Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_member('two@example.com', 'Grower')

    def test_the_comparison_is_case_insensitive(self):
        """`Grower` and `grower` read as the same person to everyone but the
        database."""
        make_member('one@example.com', 'Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_member('two@example.com', 'grower')

    def test_any_number_of_memberships_may_hold_no_nickname(self):
        """Erasure blanks it. This is the case the old partial index used a
        condition for, and the condition is what MySQL could not build."""
        for name in ('one', 'two', 'three'):
            ClubMembership.objects.create(
                user=make_account(f'{name}@example.com'), nickname=''
            )

        self.assertEqual(
            ClubMembership.objects.filter(nickname_key__isnull=True).count(), 3
        )

    def test_erasure_frees_the_nickname(self):
        """`soft_delete` clears the nickname one table away, in the same
        transaction. The name is personal data and the erasure has to reach it
        even though it no longer lives on the account."""
        user = make_member('one@example.com', 'Grower')
        user.soft_delete()

        user.club_membership.refresh_from_db()
        self.assertIsNone(user.club_membership.nickname_key)
        # And the name is available again.
        make_member('two@example.com', 'Grower')

    def test_a_stale_key_is_refused_by_the_database(self):
        """The backstop. A raw update is the write this constraint exists for.

        Without it, renaming a member with a queryset would leave them holding
        their old name for uniqueness purposes while displaying the new one --
        and every read goes through the key, so nothing would show it.
        """
        membership = self.membership('one@example.com', 'Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClubMembership.objects.filter(pk=membership.pk).update(
                    nickname='Kloof'
                )

    def test_a_null_key_beside_a_nickname_is_refused(self):
        """The three-valued-logic case. A CHECK passes when its condition is
        unknown, and a comparison against null is unknown -- so this needs the
        explicit null test in the constraint to fail at all."""
        membership = self.membership('one@example.com', 'Grower')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClubMembership.objects.filter(pk=membership.pk).update(
                    nickname_key=None
                )

    def test_by_nickname_matches_what_the_constraint_indexes(self):
        """A queryset and the database must not disagree about who holds a name."""
        membership = self.membership('one@example.com', 'Grower')

        self.assertEqual(
            list(ClubMembership.objects.by_nickname('  GROWER ')), [membership]
        )
        self.assertTrue(ClubMembership.objects.nickname_is_taken('grower'))
        self.assertFalse(ClubMembership.objects.nickname_is_taken('kloof'))


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

    **It sweeps every model, not only ``User``.** It used to check one, which
    was right when one model carried derived keys. Three more have been written
    since -- ``live_for_user``, ``primary_for_producer``, ``trading_name_key``
    -- each reaching for the same trick, and a per-model test would have covered
    none of them. The next one is covered before it is written.
    """

    def unique_constraints(self):
        return [
            (model._meta.label, constraint)
            for model in apps.get_models()
            for constraint in model._meta.constraints
            if isinstance(constraint, models.UniqueConstraint)
        ]

    def test_no_unique_constraint_is_a_partial_index(self):
        conditional = [
            f'{label}.{constraint.name}'
            for label, constraint in self.unique_constraints()
            if constraint.condition is not None
        ]

        self.assertEqual(conditional, [])

    def test_no_unique_constraint_is_an_expression_index(self):
        expressions = [
            f'{label}.{constraint.name}'
            for label, constraint in self.unique_constraints()
            if constraint.expressions
        ]

        self.assertEqual(expressions, [])

    def test_every_derived_key_rule_is_still_there(self):
        """Guarding the two tests above, which would also pass if somebody
        deleted the constraints rather than making them portable.

        All five, named, because "no partial indexes" is trivially satisfied by
        having no constraints at all.
        """
        names = {constraint.name for _label, constraint in self.unique_constraints()}

        for name in (
            'user_mobile_key_unique',
            'club_membership_nickname_key_unique',
            'one_live_subscription_per_member',
            'producer_membership_one_primary',
            'producer_trading_name_key_unique',
        ):
            with self.subTest(constraint=name):
                self.assertIn(name, names)

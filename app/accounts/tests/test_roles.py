"""Tests for roles: the column, the catalogue, and the group that mirrors it.

Roles fail quietly in two directions, and both are here.

**Too little.** An account that stops holding an action it should hold does not
crash: the API refuses a request, the frontend hides a menu item, and it looks
like a feature that was never built. So ``CatalogueTests`` asserts the shape of
the catalogue itself -- every granted codename described, every role non-empty,
no role holding an action the design document did not give it -- rather than
only spot-checking one permission.

**Too much.** An account that holds an action it should not hold produces no
error at all until somebody uses it. So the assertions that matter most are
negative: a member holds no administrative action, a cultivator cannot purchase
or swap, an inactive account holds nothing whatever its role, and the Admin role
does not open the Django admin.

``GroupMirrorTests`` covers the one piece of derived state here. It is the same
hazard as ``is_active`` drifting from ``status``, with one important difference,
which the last test in the class pins down: group membership grants no platform
action, so drift there cannot escalate anybody. That is the reason the mirror is
allowed to be best-effort rather than constrained in SQL.
"""
from django.contrib import admin as django_admin
from django.contrib.auth.models import AnonymousUser, Group
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.accounts import roles
from app.accounts.backends import RoleBackend
from app.accounts.models import User, UserRole, UserStatus
from app.accounts.roles import (
    ADMIN_ACTIONS,
    CULTIVATOR_ACTIONS,
    MEMBER_ACTIONS,
    PLATFORM_ACTIONS,
    ROLE_GROUP_NAMES,
    ROLE_PERMISSIONS,
)

PASSWORD = 'Str0ng-Passphrase!'


def active(email, role=UserRole.MEMBER, **extra):
    """An account that can actually exercise a permission.

    Active, because ``permissions_for`` refuses an inactive account before it
    looks at the role -- which is the subject of its own test below, and would
    silently make every other assertion here vacuous if it were assumed.
    """
    return User.objects.create_user(
        email=email, role=role, status=UserStatus.ACTIVE, **extra
    )


class CatalogueTests(TestCase):
    """The catalogue's own shape. No database involved."""

    def test_every_granted_action_is_described(self):
        """A codename nobody described is a codename nobody can review."""
        for role, granted in ROLE_PERMISSIONS.items():
            for codename in granted:
                with self.subTest(role=role, codename=codename):
                    self.assertIn(codename, PLATFORM_ACTIONS)
                    self.assertTrue(roles.describe(codename))

    def test_every_role_holds_something(self):
        for role in UserRole:
            with self.subTest(role=role):
                self.assertTrue(ROLE_PERMISSIONS[role])

    def test_every_role_has_an_entry(self):
        """A role with no entry resolves to nothing, which is a silent lockout."""
        self.assertEqual(set(ROLE_PERMISSIONS), set(UserRole))

    def test_every_role_has_a_group_name(self):
        self.assertEqual(set(ROLE_GROUP_NAMES), set(UserRole))
        self.assertEqual(len(set(ROLE_GROUP_NAMES.values())), len(UserRole))

    def test_every_codename_is_namespaced(self):
        """Django splits a permission on its first dot to find the app label."""
        for codename in PLATFORM_ACTIONS:
            with self.subTest(codename=codename):
                self.assertTrue(
                    codename.startswith(f'{roles.PERMISSION_NAMESPACE}.')
                )
                self.assertEqual(codename.count('.'), 1)

    def test_the_three_groups_do_not_overlap(self):
        """Each action is described once, in the group that owns it."""
        self.assertEqual(
            len(PLATFORM_ACTIONS),
            len(ADMIN_ACTIONS) + len(CULTIVATOR_ACTIONS) + len(MEMBER_ACTIONS),
        )

    def test_no_administrative_action_reaches_the_other_roles(self):
        """The negative half, and the one that matters.

        Every administrative action -- disabling accounts, refunding money,
        cancelling memberships -- is held by the Admin role alone. A regression
        here escalates every member on the platform and raises no error.
        """
        for role in (UserRole.CULTIVATOR, UserRole.MEMBER):
            with self.subTest(role=role):
                self.assertEqual(
                    ROLE_PERMISSIONS[role] & frozenset(ADMIN_ACTIONS),
                    frozenset(),
                )

    def test_a_cultivator_cannot_transact_as_a_member(self):
        """One role per account, so a cultivator is not also a buyer.

        Recorded as an accepted limitation in the design document: somebody who
        both grows and buys needs a second account. Asserted rather than merely
        documented, because the tempting fix -- quietly widening the cultivator
        set -- would change the club's rule without anybody deciding to.
        """
        cultivator = ROLE_PERMISSIONS[UserRole.CULTIVATOR]
        self.assertNotIn('platform.purchase_plants', cultivator)
        self.assertNotIn('platform.use_swap_zone', cultivator)
        self.assertNotIn('platform.offer_inventory_for_swap', cultivator)


class RoleColumnTests(TestCase):
    def test_a_new_account_is_a_member(self):
        """The safe default: it grants nothing over anybody else's records."""
        user = User.objects.create_user(email='member@example.com')
        self.assertEqual(user.role, UserRole.MEMBER)
        self.assertTrue(user.is_member)

    def test_a_superuser_is_created_as_an_administrator(self):
        """A default at creation, not a derivation from is_staff."""
        user = User.objects.create_superuser(
            email='founder@example.com', password=PASSWORD
        )
        self.assertEqual(user.role, UserRole.ADMIN)

    def test_a_superuser_role_can_be_overridden_at_creation(self):
        user = User.objects.create_superuser(
            email='founder@example.com',
            password=PASSWORD,
            role=UserRole.MEMBER,
        )
        self.assertEqual(user.role, UserRole.MEMBER)

    def test_an_unknown_role_is_refused_by_the_database(self):
        """The check constraint, reached the way a stray write would reach it.

        ``choices`` is a form-level rule. A queryset ``.update()`` walks past
        it, and without the constraint the account would simply stop being able
        to do anything, with nothing to say why.
        """
        user = User.objects.create_user(email='member@example.com')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.filter(pk=user.pk).update(role='overlord')

    def test_set_role_refuses_an_unknown_role_before_the_database_does(self):
        user = User.objects.create_user(email='member@example.com')
        with self.assertRaises(ValueError):
            user.set_role('overlord')
        user.refresh_from_db()
        self.assertEqual(user.role, UserRole.MEMBER)

    def test_set_role_moves_the_account(self):
        user = User.objects.create_user(email='grower@example.com')
        user.set_role(UserRole.CULTIVATOR)

        user.refresh_from_db()
        self.assertEqual(user.role, UserRole.CULTIVATOR)
        self.assertTrue(user.is_cultivator)

    def test_with_role_ignores_status(self):
        """A suspended cultivator is still a cultivator."""
        active('grower@example.com', role=UserRole.CULTIVATOR)
        suspended = User.objects.create_user(
            email='paused@example.com',
            role=UserRole.CULTIVATOR,
            status=UserStatus.SUSPENDED,
        )
        active('member@example.com')

        found = User.objects.with_role(UserRole.CULTIVATOR)
        self.assertEqual(found.count(), 2)
        self.assertIn(suspended, found)

    def test_the_role_survives_erasure(self):
        """It is a fact about the collective, not about the person.

        And it confers nothing on an erased account, which is Inactive -- the
        assertion beside it is what makes keeping the role defensible.
        """
        user = active('grower@example.com', role=UserRole.CULTIVATOR)
        user.soft_delete()

        self.assertEqual(user.role, UserRole.CULTIVATOR)
        self.assertEqual(roles.permissions_for(user), frozenset())

    def test_is_club_admin_is_not_staff(self):
        """The two are independent by decision, in both directions."""
        club_admin = active('boss@example.com', role=UserRole.ADMIN)
        self.assertTrue(club_admin.is_club_admin)
        self.assertFalse(club_admin.is_staff)

        staffer = active('desk@example.com', is_staff=True)
        self.assertTrue(staffer.is_staff)
        self.assertFalse(staffer.is_club_admin)


class PermissionsForTests(TestCase):
    def test_an_anonymous_visitor_holds_nothing(self):
        self.assertEqual(roles.permissions_for(AnonymousUser()), frozenset())

    def test_a_missing_user_holds_nothing(self):
        self.assertEqual(roles.permissions_for(None), frozenset())

    def test_a_member_holds_the_member_actions(self):
        user = active('member@example.com')
        self.assertEqual(
            roles.permissions_for(user), frozenset(MEMBER_ACTIONS)
        )

    def test_an_inactive_account_holds_nothing_whatever_its_role(self):
        """Status gates authority, so nothing else has to remember to check it.

        Suspension and erasure both land here, and neither had to be taught
        about permissions to do so.
        """
        for status in UserStatus:
            with self.subTest(status=status):
                user = User(
                    email=f'{status.value}@example.com',
                    role=UserRole.ADMIN,
                    status=status,
                )
                user.is_active = status == UserStatus.ACTIVE
                held = roles.permissions_for(user)
                if status == UserStatus.ACTIVE:
                    self.assertTrue(held)
                else:
                    self.assertEqual(held, frozenset())

    def test_an_active_superuser_holds_everything(self):
        """The same answer Django's own permission framework gives."""
        user = User.objects.create_superuser(
            email='root@example.com', password=PASSWORD, role=UserRole.MEMBER
        )
        self.assertEqual(
            roles.permissions_for(user), frozenset(PLATFORM_ACTIONS)
        )

    def test_an_unrecognised_role_holds_nothing_rather_than_raising(self):
        """Belt and braces behind the check constraint.

        A write that bypassed the model should leave an account powerless, not
        crash the next request that reads it.
        """
        user = User(email='odd@example.com', role='overlord')
        user.is_active = True
        self.assertEqual(roles.permissions_for(user), frozenset())


class HasPermTests(TestCase):
    """The catalogue through Django's own permission call.

    Every test here goes through ``user.has_perm`` rather than
    ``permissions_for`` directly, because ``has_perm`` is what a view will call
    and the backend registration in settings is part of what has to work.
    """

    def test_a_member_holds_a_member_action(self):
        user = active('member@example.com')
        self.assertTrue(user.has_perm('platform.purchase_plants'))

    def test_a_member_does_not_hold_an_administrative_action(self):
        user = active('member@example.com')
        self.assertFalse(user.has_perm('platform.refund_transaction'))
        self.assertFalse(user.has_perm('platform.cancel_membership'))

    def test_a_cultivator_holds_a_cultivation_action(self):
        user = active('grower@example.com', role=UserRole.CULTIVATOR)
        self.assertTrue(user.has_perm('platform.change_plant_status'))
        self.assertFalse(user.has_perm('platform.purchase_plants'))

    def test_an_administrator_holds_an_administrative_action(self):
        user = active('boss@example.com', role=UserRole.ADMIN)
        self.assertTrue(user.has_perm('platform.cancel_membership'))

    def test_an_unknown_codename_is_refused(self):
        user = active('member@example.com')
        self.assertFalse(user.has_perm('platform.mint_money'))

    def test_a_suspended_account_holds_nothing(self):
        user = active('member@example.com')
        user.deactivate()
        self.assertFalse(user.has_perm('platform.purchase_plants'))

    def test_django_model_permissions_still_resolve(self):
        """The point of using a backend: one call covers both kinds.

        A per-account ``auth.Permission`` grant has to keep working alongside
        the catalogue, or adding roles would have quietly broken every ordinary
        Django permission check.
        """
        from django.contrib.auth.models import Permission

        user = active('desk@example.com', is_staff=True)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='accounts', codename='change_user'
            )
        )
        user = User.objects.get(pk=user.pk)

        self.assertTrue(user.has_perm('accounts.change_user'))
        self.assertTrue(user.has_perm('platform.purchase_plants'))

    def test_object_level_questions_are_refused(self):
        """A role says nothing about one record, so it must not answer for one.

        Answering from the role would be wrong in the dangerous direction: "may
        this cultivator edit *this* listing" would come back yes for every
        listing on the platform.
        """
        user = active('grower@example.com', role=UserRole.CULTIVATOR)
        backend = RoleBackend()
        self.assertFalse(
            backend.has_perm(user, 'platform.change_plant_status', obj=user)
        )
        self.assertEqual(
            backend.get_all_permissions(user, obj=user), set()
        )

    def test_the_backend_authenticates_nobody(self):
        """ModelBackend stays the only way into a session."""
        self.assertIsNone(
            RoleBackend().authenticate(None, username='a@b.c', password='x')
        )
        self.assertIsNone(RoleBackend().get_user('anything'))

    async def test_the_async_permission_call_answers_the_same(self):
        """Every endpoint in ``authn.api`` is ``async def``.

        ``ahas_perm`` is what Django's async auth stack calls, and a backend
        missing the async half fails at request time rather than here -- which
        is how the first version of this class shipped broken.
        """
        user = await User.objects.acreate(
            email='member@example.com',
            role=UserRole.MEMBER,
            status=UserStatus.ACTIVE,
        )
        backend = RoleBackend()

        self.assertTrue(
            await backend.ahas_perm(user, 'platform.purchase_plants')
        )
        self.assertFalse(
            await backend.ahas_perm(user, 'platform.cancel_membership')
        )

    def test_module_permissions_are_confined_to_the_namespace(self):
        """A role must not decide which real apps appear in the admin."""
        user = active('boss@example.com', role=UserRole.ADMIN)
        backend = RoleBackend()
        self.assertTrue(backend.has_module_perms(user, 'platform'))
        self.assertFalse(backend.has_module_perms(user, 'accounts'))


class GroupMirrorTests(TestCase):
    def test_a_new_account_lands_in_its_role_group(self):
        user = User.objects.create_user(email='member@example.com')
        self.assertEqual(
            list(user.groups.values_list('name', flat=True)),
            [ROLE_GROUP_NAMES[UserRole.MEMBER]],
        )

    def test_changing_the_role_moves_the_group(self):
        user = User.objects.create_user(email='grower@example.com')
        user.set_role(UserRole.CULTIVATOR)

        self.assertEqual(
            list(user.groups.values_list('name', flat=True)),
            [ROLE_GROUP_NAMES[UserRole.CULTIVATOR]],
        )

    def test_a_group_added_by_hand_survives_a_role_change(self):
        """The mirror is bookkeeping; somebody else's group is a decision."""
        courier, _ = Group.objects.get_or_create(name='Couriers')
        user = User.objects.create_user(email='grower@example.com')
        user.groups.add(courier)

        user.set_role(UserRole.CULTIVATOR)

        self.assertEqual(
            set(user.groups.values_list('name', flat=True)),
            {'Couriers', ROLE_GROUP_NAMES[UserRole.CULTIVATOR]},
        )

    def test_a_deleted_group_is_recreated_rather_than_failing_the_save(self):
        Group.objects.filter(name=ROLE_GROUP_NAMES[UserRole.MEMBER]).delete()

        user = User.objects.create_user(email='member@example.com')

        self.assertEqual(
            list(user.groups.values_list('name', flat=True)),
            [ROLE_GROUP_NAMES[UserRole.MEMBER]],
        )

    def test_an_ordinary_save_does_not_touch_the_group(self):
        """The reason ``save`` compares against the stored role first.

        Without the comparison every status change, every login timestamp and
        every erasure would pay for a group write it does not need.
        """
        user = User.objects.create_user(email='member@example.com')
        user = User.objects.get(pk=user.pk)

        with self.assertNumQueries(1):
            user.status = UserStatus.ACTIVE
            user.save(update_fields=['status', 'updated_at'])

    def test_a_partial_save_that_omits_the_role_does_not_mirror_it(self):
        """An unsaved assignment must not reach the group.

        Otherwise the group would describe a role the row does not hold, which
        is the drift this mirror exists to avoid.
        """
        user = User.objects.create_user(email='member@example.com')
        user = User.objects.get(pk=user.pk)

        user.role = UserRole.ADMIN
        user.save(update_fields=['status', 'updated_at'])

        user.refresh_from_db()
        self.assertEqual(user.role, UserRole.MEMBER)
        self.assertEqual(
            list(user.groups.values_list('name', flat=True)),
            [ROLE_GROUP_NAMES[UserRole.MEMBER]],
        )

    def test_group_membership_grants_no_platform_action(self):
        """Why the mirror is allowed to be best-effort.

        The catalogue is resolved from the ``role`` column, never from group
        membership, so a group edited by hand -- or left behind by a queryset
        ``.update()`` -- cannot grant anybody anything.
        """
        user = active('member@example.com')
        user.groups.add(Group.objects.get(name=ROLE_GROUP_NAMES[UserRole.ADMIN]))
        user = User.objects.get(pk=user.pk)

        self.assertFalse(user.has_perm('platform.cancel_membership'))

    def test_the_migration_seeded_all_three_groups(self):
        """They exist before anybody holds the role, so the admin can show them."""
        self.assertEqual(
            Group.objects.filter(
                name__in=list(ROLE_GROUP_NAMES.values())
            ).count(),
            len(UserRole),
        )


class AdminPageTests(TestCase):
    """The member change page, which is where a role is actually appointed.

    Two things here fail invisibly. A read-only panel built from a callable
    raises on render rather than at import, so a mistake in it takes down the
    page a member of staff needs -- and nothing else notices. And if ``groups``
    stopped being read-only, the admin's ``save_m2m()`` would overwrite the role
    mirror with whatever was rendered before the role changed: the page would
    still save, and the group would quietly describe the previous role.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            email='staff@example.com', password=PASSWORD
        )
        cls.member = active('member@example.com', role=UserRole.CULTIVATOR)

    def setUp(self):
        self.client.force_login(self.staff)

    def change_page(self, user):
        return self.client.get(
            f'/admin/accounts/user/{user.pk}/change/'
        )

    def test_the_page_lists_what_the_role_permits(self):
        response = self.change_page(self.member)

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('platform.change_plant_status', body)
        self.assertIn('Move a plant between preflowering', body)

    def test_a_superuser_is_called_out_rather_than_listed(self):
        """Django grants a superuser everything before any backend is asked.

        Printing the role's set beside an account that is not bound by it would
        be a lie of omission.
        """
        body = self.change_page(self.staff).content.decode()

        self.assertIn('Superuser: every action on the platform', body)

    def member_form(self):
        """The change form as the registered admin builds it.

        Taken from ``site._registry`` rather than instantiated here, so this
        exercises the admin that is actually deployed rather than a second one
        configured by the test.
        """
        model_admin = django_admin.site.get_model_admin(User)
        return model_admin.get_form(None, self.member, change=True)

    def test_groups_cannot_be_edited_from_the_member_page(self):
        """Or the mirror would be overwritten on every save. See the docstring."""
        self.assertNotIn('groups', self.member_form().base_fields)

    def test_the_role_can_be_appointed_from_the_page(self):
        """The admin is the only route to Cultivator or Admin."""
        self.assertIn('role', self.member_form().base_fields)

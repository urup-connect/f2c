"""Tests for authority: the catalogue, the relationships that grant, the backend.

Authority fails quietly in two directions, and both are here.

**Too little.** An account that stops holding an action it should hold does not
crash: the API refuses a request, the frontend hides a menu item, and it looks
like a feature that was never built. So ``CatalogueTests`` asserts the shape of
the catalogue itself -- every granted codename described, no set holding an
action the design document did not give it -- rather than only spot-checking one
permission.

**Too much.** An account that holds an action it should not hold produces no
error at all until somebody uses it. So the assertions that matter most are
negative: a bare account holds nothing, an unpaid membership holds nothing, a
limited appointment cannot appoint, an inactive account holds nothing whatever
it is related to, and ``is_staff`` grants nothing here at all.

**What changed, and what it cost this module.** There was a ``role`` column, and
a ``GroupMirrorTests`` class covering the Django group that mirrored it. C28
retired the column and the groups went with it, so that class is gone rather
than adapted -- there is no derived state left for it to guard.
``RoleColumnTests`` went the same way.

What replaced them is the class of assertion the column made impossible:
:meth:`UnionTests.test_an_administrator_who_is_also_a_member_holds_both`. The
design document carried "somebody who does both needs a second account" as an
accepted limitation for as long as authority was one value. It is not a
limitation now, and that test is what says so.
"""
from django.contrib import admin as django_admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from app.club.membership.models import MembershipStatus
from app.commerce.producers.models import ProducerRole
from app.core.accounts import roles
from app.core.accounts.backends import RoleBackend
from app.core.accounts.models import User, UserStatus
from app.core.accounts.roles import (
    ADMINISTRATOR_ACTIONS,
    CLUB_ADMINISTRATOR_PERMISSIONS,
    MARKET_ADMINISTRATOR_PERMISSIONS,
    MEMBER_ACTIONS,
    MEMBER_PERMISSIONS,
    PLATFORM_ACTIONS,
    PRODUCER_ACTIONS,
    PRODUCER_BASE_PERMISSIONS,
    PRODUCER_FULL_PERMISSIONS,
    PRODUCER_PRIMARY_PERMISSIONS,
)
from app.core.storefronts.models import Storefront
from f2c.testing import (
    make_account,
    make_administrator,
    make_cultivator,
    make_member,
)

PASSWORD = 'Str0ng-Passphrase!'


def held(user):
    """What this account may do, with the relationships loaded.

    Through ``with_platform_roles()`` because that is how the application reads
    it, and because a test that let the relations load lazily would pass while
    the endpoint serialising the same set raised ``SynchronousOnlyOperation``.
    That is exactly the defect this suite failed to catch the first time.
    """
    return roles.permissions_for(
        User.objects.with_platform_roles().get(pk=user.pk)
    )


class CatalogueTests(TestCase):
    """The catalogue's own shape. No database involved."""

    def test_every_granted_action_is_described(self):
        """A codename nobody described is a codename nobody can review."""
        granted = (
            CLUB_ADMINISTRATOR_PERMISSIONS
            | MARKET_ADMINISTRATOR_PERMISSIONS
            | MEMBER_PERMISSIONS
            | PRODUCER_BASE_PERMISSIONS
            | PRODUCER_FULL_PERMISSIONS
            | PRODUCER_PRIMARY_PERMISSIONS
        )
        self.assertEqual(granted - set(PLATFORM_ACTIONS), set())

    def test_every_codename_is_namespaced(self):
        """Django splits a permission on its first dot to find the app label."""
        for codename in PLATFORM_ACTIONS:
            with self.subTest(codename=codename):
                self.assertTrue(codename.startswith('platform.'))

    def test_the_groups_do_not_overlap(self):
        """Each action is described once, in the group that owns it."""
        groups = [ADMINISTRATOR_ACTIONS, PRODUCER_ACTIONS, MEMBER_ACTIONS]
        seen = set()
        for group in groups:
            with self.subTest(group=sorted(group)[:1]):
                self.assertEqual(seen & set(group), set())
                seen |= set(group)

    def test_the_uc_tier_actions_are_not_in_the_catalogue(self):
        """C29. Refunds and cancellation are done in the Django admin.

        An action in this catalogue is one an API endpoint checks. Neither of
        these is, so leaving them here would describe authority no endpoint
        grants and no screen can reach.
        """
        self.assertNotIn('platform.refund_transaction', PLATFORM_ACTIONS)
        self.assertNotIn('platform.cancel_membership', PLATFORM_ACTIONS)
        self.assertNotIn('platform.manage_administrators', PLATFORM_ACTIONS)

    def test_managing_your_own_profile_is_not_in_the_catalogue(self):
        """Retired for encoding no decision, not for being unwanted.

        ``platform.manage_own_profile`` was in three of the sets and held by
        every account that could sign in -- until the produce market, where a
        customer holds none of the three relationships and was refused their own
        name and photograph. The endpoints behind it are scoped to
        ``request.user``, so there was no object to authorise: this module's own
        rule is that a permission nobody can be refused is not a permission.

        Asserted as an absence rather than left to the absence of a test,
        because re-adding it would look like a fix. ``accounts.profile`` checks
        for an active account and that is the whole gate.
        """
        self.assertNotIn('platform.manage_own_profile', PLATFORM_ACTIONS)
        for granted in (
            MEMBER_PERMISSIONS,
            CLUB_ADMINISTRATOR_PERMISSIONS,
            PRODUCER_BASE_PERMISSIONS,
            PRODUCER_FULL_PERMISSIONS,
            PRODUCER_PRIMARY_PERMISSIONS,
        ):
            self.assertNotIn('platform.manage_own_profile', granted)

    def test_the_producer_sets_nest(self):
        """Being the primary is *more than* full rights, not an alternative.

        Asserted on the sets rather than on a resolved account, because the
        nesting is what ``permissions_for`` relies on when it adds them up.
        """
        self.assertEqual(PRODUCER_BASE_PERMISSIONS & PRODUCER_FULL_PERMISSIONS, frozenset())
        self.assertEqual(
            PRODUCER_PRIMARY_PERMISSIONS & PRODUCER_BASE_PERMISSIONS, frozenset()
        )

    def test_creating_a_sharing_member_is_the_primarys_alone(self):
        """And nobody else's, including the club administrator's.

        Creating records for other people is the one thing on this platform
        that should have exactly one route. `member-roles` gives it to the
        primary, and until C28 that was an object-level rule the catalogue
        could not express -- so it went to every cultivator instead.
        """
        for codename in (
            'platform.register_sharing_member',
            'platform.manage_sharing_members',
        ):
            with self.subTest(codename=codename):
                self.assertIn(codename, PRODUCER_PRIMARY_PERMISSIONS)
                self.assertNotIn(codename, PRODUCER_FULL_PERMISSIONS)
                self.assertNotIn(codename, PRODUCER_BASE_PERMISSIONS)
                self.assertNotIn(codename, CLUB_ADMINISTRATOR_PERMISSIONS)

    def test_the_farms_identity_is_the_primarys_alone(self):
        """C13. The cultivator organisation's front identity -- what members see
        and buy under -- belongs to the owner of the farm.

        It sat on full rights until then, so a staff appointment could rename
        the farm or unpublish it. The *offering* deliberately did not move:
        pricing and listings are what full rights exists to delegate.
        """
        self.assertIn(
            'platform.manage_own_cultivator_profile', PRODUCER_PRIMARY_PERMISSIONS
        )
        self.assertNotIn(
            'platform.manage_own_cultivator_profile', PRODUCER_FULL_PERMISSIONS
        )
        self.assertNotIn(
            'platform.manage_own_cultivator_profile', PRODUCER_BASE_PERMISSIONS
        )
        for codename in (
            'platform.manage_own_pricing',
            'platform.manage_own_strain_listings',
        ):
            with self.subTest(codename=codename):
                self.assertIn(codename, PRODUCER_FULL_PERMISSIONS)

    def test_no_administrative_action_reaches_a_member(self):
        """The negative half, and the one that matters."""
        self.assertEqual(
            MEMBER_PERMISSIONS & frozenset(ADMINISTRATOR_ACTIONS), frozenset()
        )

    def test_the_market_administrator_set_is_empty_and_present(self):
        """Deliberately present. A missing key reads as an oversight.

        The market's own actions arrive with the market vertical; until then
        administering it grants nothing, which is true rather than unfinished.
        """
        self.assertEqual(MARKET_ADMINISTRATOR_PERMISSIONS, frozenset())


class PermissionsForTests(TestCase):
    """Resolution from the relationships, which is the whole of C28."""

    def test_an_anonymous_visitor_holds_nothing(self):
        self.assertEqual(roles.permissions_for(AnonymousUser()), frozenset())

    def test_a_missing_user_holds_nothing(self):
        self.assertEqual(roles.permissions_for(None), frozenset())

    def test_a_bare_account_holds_nothing(self):
        """A produce-market customer: an account and no relationships.

        The most important new case. Before the split every account carried a
        role, so "holds nothing" was reachable only through suspension.
        """
        self.assertEqual(held(make_account('shopper@example.com')), frozenset())

    def test_an_active_membership_holds_the_member_actions(self):
        self.assertEqual(held(make_member('member@example.com')), MEMBER_PERMISSIONS)

    def test_an_unpaid_membership_holds_nothing(self):
        """They sign in perfectly well and reach the payment screen. C27.

        This is the pay-now gate at the permission layer, and it is what stops
        an unpaid member reaching the club through an endpoint rather than
        through a menu.
        """
        user = make_member(
            'owing@example.com', 'Owing', status=MembershipStatus.PENDING_PAYMENT
        )
        self.assertTrue(user.is_active)
        self.assertEqual(held(user), frozenset())

    def test_a_club_administrator_holds_the_administrator_actions(self):
        self.assertEqual(
            held(make_administrator('boss@example.com')),
            CLUB_ADMINISTRATOR_PERMISSIONS,
        )

    def test_a_market_administrator_holds_nothing_yet(self):
        user = make_administrator('market@example.com', storefront=Storefront.MARKET)
        self.assertEqual(held(user), frozenset())

    def test_a_limited_appointment_holds_the_base_actions_only(self):
        user, _ = make_cultivator('hand@example.com', role=ProducerRole.LIMITED)
        self.assertEqual(held(user), PRODUCER_BASE_PERMISSIONS)

    def test_full_rights_add_the_commercial_actions(self):
        user, _ = make_cultivator('manager@example.com', role=ProducerRole.FULL)
        self.assertEqual(
            held(user), PRODUCER_BASE_PERMISSIONS | PRODUCER_FULL_PERMISSIONS
        )

    def test_the_primary_holds_all_three(self):
        user, _ = make_cultivator('owner@example.com')
        self.assertEqual(
            held(user),
            PRODUCER_BASE_PERMISSIONS
            | PRODUCER_FULL_PERMISSIONS
            | PRODUCER_PRIMARY_PERMISSIONS,
        )

    def test_a_limited_appointment_cannot_appoint(self):
        """The negative half of the nesting, stated where it cannot be missed."""
        user, _ = make_cultivator('hand@example.com', role=ProducerRole.LIMITED)
        self.assertNotIn('platform.appoint_cultivator_staff', held(user))

    def test_an_appointment_does_not_confer_membership(self):
        """A cultivator is not thereby a buyer, and never was.

        Unchanged by C28 and worth keeping: the sets did not widen. What
        changed is that the same *person* may hold a membership as well — see
        ``UnionTests``.
        """
        user, _ = make_cultivator('grower@example.com')
        self.assertNotIn('platform.purchase_plants', held(user))

    def test_an_inactive_account_holds_nothing_whatever_it_is_related_to(self):
        """Status gates authority, so nothing else has to remember to check it.

        Suspension and erasure both land here, and neither had to be taught
        about relationships to do so.
        """
        for status in UserStatus:
            with self.subTest(status=status):
                user = make_administrator(f'{status.value}@example.com')
                make_member(f'{status.value}@example.com', str(status.value), account=user)
                user.status = status
                user.save()

                if status == UserStatus.ACTIVE:
                    self.assertTrue(held(user))
                else:
                    self.assertEqual(held(user), frozenset())

    def test_an_active_superuser_holds_everything(self):
        """The same answer Django's own permission framework gives."""
        user = User.objects.create_superuser(
            email='root@example.com', password=PASSWORD
        )
        self.assertEqual(held(user), frozenset(PLATFORM_ACTIONS))

    def test_is_staff_alone_grants_nothing_in_the_catalogue(self):
        """C29. It opens the Django admin, which does not consult this at all.

        The one assertion that keeps the platform-operator tier from leaking
        back into the API. A bookkeeper with a back-office login must not
        thereby be able to run the club through an endpoint.
        """
        user = make_account('desk@example.com', is_staff=True)
        self.assertEqual(held(user), frozenset())


class UnionTests(TestCase):
    """The limitation C28 removed, asserted rather than assumed."""

    def test_an_administrator_who_is_also_a_member_holds_both(self):
        """The design document carried this as an accepted limitation.

        > One role per account means a cultivator cannot buy or swap, and an
        > administrator cannot do either. Anyone who does both needs a second
        > account.

        It is gone, and **not because any set was widened** — this asserts the
        exact union, so a test that passed by loosening the member set would
        fail here instead.
        """
        user = make_administrator('boss@example.com')
        make_member('boss@example.com', 'Boss', account=user)

        self.assertEqual(
            held(user), CLUB_ADMINISTRATOR_PERMISSIONS | MEMBER_PERMISSIONS
        )

    def test_a_cultivator_who_is_also_a_member_holds_both(self):
        user, _ = make_cultivator('grower@example.com')
        make_member('grower@example.com', 'Kloof Grower', account=user)

        self.assertIn('platform.purchase_plants', held(user))
        self.assertIn('platform.manage_plant_stock', held(user))

    def test_two_appointments_accumulate(self):
        """Somebody appointed to two farms, limited at one and primary at the
        other, holds the primary's set — at the farm that granted it.

        Which farm is not this function's question. "May they appoint at all"
        is answered here; "may they appoint *here*" is the object-level rule,
        answered by the service that owns the record.
        """
        user, _ = make_cultivator(
            'both@example.com', role=ProducerRole.LIMITED, trading_name='One'
        )
        make_cultivator('both@example.com', account=user, trading_name='Two')

        self.assertIn('platform.appoint_cultivator_staff', held(user))


class HasPermTests(TestCase):
    """The catalogue through Django's own permission call.

    Every test here goes through ``user.has_perm`` rather than
    ``permissions_for`` directly, because ``has_perm`` is what a view will call
    and the backend registration in settings is part of what has to work.
    """

    def test_a_member_holds_a_member_action(self):
        user = make_member('member@example.com')
        self.assertTrue(user.has_perm('platform.purchase_plants'))

    def test_a_member_does_not_hold_an_administrative_action(self):
        user = make_member('member@example.com')
        self.assertFalse(user.has_perm('platform.manage_cultivators'))

    def test_a_cultivator_holds_a_cultivation_action(self):
        user, _ = make_cultivator('grower@example.com')
        self.assertTrue(user.has_perm('platform.change_plant_status'))
        self.assertFalse(user.has_perm('platform.purchase_plants'))

    def test_an_administrator_holds_an_administrative_action(self):
        user = make_administrator('boss@example.com')
        self.assertTrue(user.has_perm('platform.manage_cultivators'))

    def test_an_unknown_codename_is_refused(self):
        user = make_member('member@example.com')
        self.assertFalse(user.has_perm('platform.mint_money'))

    def test_a_suspended_account_holds_nothing(self):
        user = make_member('member@example.com')
        user.deactivate()
        self.assertFalse(user.has_perm('platform.purchase_plants'))

    def test_django_model_permissions_still_resolve(self):
        """The point of using a backend: one call covers both kinds.

        A per-account ``auth.Permission`` grant has to keep working alongside
        the catalogue, or this would have quietly broken every ordinary Django
        permission check.
        """
        from django.contrib.auth.models import Permission

        user = make_member('desk@example.com', is_staff=True)
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='accounts', codename='change_user'
            )
        )
        user = User.objects.get(pk=user.pk)

        self.assertTrue(user.has_perm('accounts.change_user'))
        self.assertTrue(user.has_perm('platform.purchase_plants'))

    def test_object_level_questions_are_refused(self):
        """A person-level set says nothing about one record.

        Answering from it would be wrong in the dangerous direction: "may this
        cultivator edit *this* listing" would come back yes for every listing on
        the platform. C28 gave the question somewhere to go —
        ``ProducerMembership`` rows — but that answer belongs to the service
        that owns the record, not here.
        """
        user, _ = make_cultivator('grower@example.com')
        backend = RoleBackend()
        self.assertFalse(
            backend.has_perm(user, 'platform.change_plant_status', obj=user)
        )
        self.assertEqual(backend.get_all_permissions(user, obj=user), set())

    def test_the_backend_authenticates_nobody(self):
        """ModelBackend stays the only way into a session."""
        self.assertIsNone(
            RoleBackend().authenticate(None, username='a@b.c', password='x')
        )
        self.assertIsNone(RoleBackend().get_user('anything'))

    def test_module_permissions_are_confined_to_the_namespace(self):
        """Authority must not decide which real apps appear in the admin."""
        user = make_administrator('boss@example.com')
        backend = RoleBackend()
        self.assertTrue(backend.has_module_perms(user, 'platform'))
        self.assertFalse(backend.has_module_perms(user, 'accounts'))


class AsyncPermissionTests(TestCase):
    """The async half, which is not optional here.

    Every endpoint in ``authn.api`` is ``async def``, and this is where the
    discipline that ``permissions_for`` depends on gets tested rather than
    trusted.
    """

    async def test_the_async_permission_call_answers_the_same(self):
        """``ahas_perm`` is what Django's async auth stack calls.

        A backend missing the async half fails at request time rather than
        here — which is how the first version of this class shipped broken.
        """
        user = await User.objects.acreate(
            email='member@example.com', status=UserStatus.ACTIVE
        )
        backend = RoleBackend()

        self.assertFalse(
            await backend.ahas_perm(user, 'platform.purchase_plants')
        )

    async def test_resolving_a_loaded_account_issues_no_query(self):
        """The rule ``permissions_for`` is written against, pinned.

        An unloaded relation here is not slow but fatal:
        ``SynchronousOnlyOperation``. This is the assertion that would have
        caught the defect where ``authn.api`` loaded only the membership while
        the resolver read three relationships — risk 11 in
        ``roles-and-permissions.md``.
        """
        user = await User.objects.acreate(
            email='member@example.com', status=UserStatus.ACTIVE
        )
        loaded = await User.objects.with_platform_roles().aget(pk=user.pk)

        # No await, no thread: if any relation were unloaded this raises.
        self.assertEqual(roles.permissions_for(loaded), frozenset())


class AdminPanelTests(TestCase):
    """The read-only panel on the member page.

    It fails invisibly: a panel built from a callable raises on render rather
    than at import, so a mistake in it takes down the page a member of staff
    needs and nothing else notices.
    """

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            email='staff@example.com', password=PASSWORD
        )
        cls.grower, _ = make_cultivator('grower@example.com')

    def setUp(self):
        self.client.force_login(self.staff)

    def change_page(self, user):
        return self.client.get(f'/admin/accounts/user/{user.pk}/change/')

    def test_the_page_lists_what_the_account_may_do(self):
        response = self.change_page(self.grower)

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('platform.change_plant_status', body)
        self.assertIn('Move a plant between preflowering', body)

    def test_a_superuser_is_called_out_rather_than_listed(self):
        """Django grants a superuser everything before any backend is asked.

        Printing a resolved set beside an account that is not bound by it would
        be a lie of omission.
        """
        body = self.change_page(self.staff).content.decode()

        self.assertIn('Superuser: every action on the platform', body)

    def member_form(self):
        """The change form as the registered admin builds it.

        Taken from ``site.get_model_admin`` rather than instantiated here, so
        this exercises the admin that is actually deployed.
        """
        request = RequestFactory().get(
            f'/admin/accounts/user/{self.grower.pk}/change/'
        )
        request.user = self.staff
        model_admin = django_admin.site.get_model_admin(User)
        return model_admin.get_form(request, self.grower, change=True)

    def test_there_is_no_role_field(self):
        """C28. Authority is three relationships, each administered elsewhere.

        A role field here would be a fourth place to grant it, and the one that
        no longer has a column behind it.
        """
        self.assertNotIn('role', self.member_form().base_fields)

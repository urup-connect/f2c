"""Tests for the storefront administrator admin.

This is the page that hands over the register, and nothing about it looks like
it: one dropdown and an autocomplete. So what is asserted here is that adding a
row is genuinely the whole of granting the administrator set -- if that ever
stops being true, ``permissions_for`` and this page have drifted and the drift
is silent in both directions.

The rest is the two rules the page imposes on itself. An appointment is granted
and revoked rather than retyped, so the appointee and the storefront freeze once
the row exists; and ``appointed_by`` is defaulted rather than forced, because it
is provenance and nothing reads it for authority.
"""
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from app.core.accounts.models import User
from app.core.accounts.roles import ADMINISTRATOR_ACTIONS
from app.core.storefronts.admin import StorefrontStaffAdmin
from app.core.storefronts.models import Storefront, StorefrontStaff
from f2c.testing import make_account, make_administrator, make_member


class GrantTests(TestCase):
    """Adding a row is the whole of making somebody an administrator."""

    def setUp(self):
        self.person = make_account('person@example.com')

    def test_an_account_with_no_appointment_holds_nothing(self):
        """The fixture the grant is measured against.

        A bare account is a produce-market customer, and the assertion is what
        makes the next test mean something.
        """
        self.assertEqual(
            set(User.objects.with_platform_roles().get(pk=self.person.pk)
                .get_all_permissions()),
            set(),
        )

    def test_a_club_appointment_grants_the_administrator_set_in_full(self):
        StorefrontStaff.objects.create(
            user=self.person, storefront=Storefront.CLUB
        )

        held = User.objects.with_platform_roles().get(pk=self.person.pk)

        self.assertTrue(
            set(ADMINISTRATOR_ACTIONS).issubset(held.get_all_permissions())
        )

    def test_a_market_appointment_grants_no_club_authority(self):
        """The whole reason the storefront is on the row rather than implied.

        A single role column said "administrator" and could not say of what.
        """
        StorefrontStaff.objects.create(
            user=self.person, storefront=Storefront.MARKET
        )

        held = User.objects.with_platform_roles().get(pk=self.person.pk)

        self.assertFalse(
            set(ADMINISTRATOR_ACTIONS) & set(held.get_all_permissions())
        )

    def test_staff_status_alone_grants_nothing(self):
        """C29. Opening this admin site is not authority over a storefront."""
        operator = make_account('operator@example.com', is_staff=True)

        held = User.objects.with_platform_roles().get(pk=operator.pk)

        self.assertEqual(set(held.get_all_permissions()), set())


class FormRuleTests(TestCase):
    """What the page will and will not let staff change."""

    def setUp(self):
        self.admin = StorefrontStaffAdmin(StorefrontStaff, AdminSite())
        self.operator = make_account('operator@example.com', is_staff=True)
        self.request = RequestFactory().get('/admin/')
        self.request.user = self.operator

    def test_the_grantor_defaults_to_whoever_is_filling_the_form_in(self):
        initial = self.admin.get_changeform_initial_data(self.request)

        self.assertEqual(initial['appointed_by'], self.operator.pk)

    def test_the_appointee_and_the_storefront_freeze_once_saved(self):
        """Retyping an appointment is two events, not a correction.

        Moving a saved row from the club to the market ends one appointment and
        begins another against a different permission set, while keeping the
        original ``appointed_at``.
        """
        appointment = StorefrontStaff.objects.create(
            user=make_account('appointee@example.com'),
            storefront=Storefront.CLUB,
        )

        readonly = self.admin.get_readonly_fields(self.request, appointment)

        self.assertIn('user', readonly)
        self.assertIn('storefront', readonly)

    def test_both_are_settable_while_the_appointment_is_being_added(self):
        readonly = self.admin.get_readonly_fields(self.request, None)

        self.assertNotIn('user', readonly)
        self.assertNotIn('storefront', readonly)

    def test_the_grantor_stays_editable_because_it_is_only_provenance(self):
        appointment = StorefrontStaff.objects.create(
            user=make_account('appointee@example.com'),
            storefront=Storefront.CLUB,
        )

        self.assertNotIn(
            'appointed_by', self.admin.get_readonly_fields(self.request, appointment)
        )


class ListTests(TestCase):
    """What the list renders, and what it costs to render it."""

    def setUp(self):
        self.admin = StorefrontStaffAdmin(StorefrontStaff, AdminSite())
        self.request = RequestFactory().get('/admin/')
        self.request.user = make_account('operator@example.com', is_staff=True)

    def test_an_administrator_who_is_also_a_member_shows_their_nickname(self):
        """The union C28 made expressible, seen from this page.

        ``display_name`` prefers the club nickname, which is what the club
        knows them by.
        """
        account = make_member('both@example.com', nickname='Thabo')
        make_administrator(account=account)

        appointment = StorefrontStaff.objects.get(user=account)

        self.assertEqual(self.admin.person(appointment), 'Thabo')

    def test_an_administrator_who_never_joined_falls_back_to_their_name(self):
        """A market administrator has no membership and no nickname at all."""
        account = make_account(
            'market@example.com', first_name='Naledi', last_name='Dube'
        )
        make_administrator(account=account, storefront=Storefront.MARKET)

        appointment = StorefrontStaff.objects.get(user=account)

        self.assertEqual(self.admin.person(appointment), 'Naledi Dube')

    def test_the_membership_behind_each_row_is_joined_not_fetched_per_row(self):
        """``person`` walks to the nickname, which is one table further out.

        Unselected this is a query per row on a page listing every
        administrator -- risk 11 in ``roles-and-permissions.md``, which is
        about exactly this relation being left lazy.
        """
        for index in range(3):
            make_administrator(
                account=make_member(f'admin{index}@example.com',
                                    nickname=f'Admin{index}')
            )

        rows = list(self.admin.get_queryset(self.request))

        with self.assertNumQueries(0):
            names = [self.admin.person(row) for row in rows]
        self.assertEqual(sorted(names), ['Admin0', 'Admin1', 'Admin2'])

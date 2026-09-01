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
from app.core.storefronts.admin import EmailDispatchAdmin, StorefrontStaffAdmin
from app.core.storefronts.models import EmailDispatch, Storefront, StorefrontStaff
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


class EmailDispatchAdminTests(TestCase):
    """The send log page. Read-only, and the reasons are not the same.

    Nothing on this page may be typed into, but the three prohibitions answer
    three different questions and are worth asserting separately: a row exists
    because a message was sent (no adding), a record of what happened is not a
    record if it can be edited (no changing), and a deletion is the one action
    here that can make the log lie (superusers only).
    """

    def setUp(self):
        self.admin = EmailDispatchAdmin(EmailDispatch, AdminSite())
        self.member = make_member('member@example.com', 'Thabo')
        self.operator = make_account('operator@example.com')
        self.requests = RequestFactory()

    def request_from(self, user):
        request = self.requests.get('/admin/')
        request.user = user
        return request

    def make(self, **overrides):
        options = {
            'kind': EmailDispatch.Kind.LOGIN_CODE,
            'storefront': Storefront.CLUB,
            'recipient': self.member,
            'subject': 'Your sign-in code',
            'trigger': EmailDispatch.Trigger.MEMBER,
        }
        options.update(overrides)
        return EmailDispatch.objects.create(**options)

    def test_nothing_can_be_added_by_hand(self):
        self.assertFalse(
            self.admin.has_add_permission(self.request_from(self.operator))
        )

    def test_nothing_can_be_edited(self):
        self.assertFalse(
            self.admin.has_change_permission(self.request_from(self.operator))
        )

    def test_every_field_is_read_only(self):
        """Asserted over ``_meta`` rather than against a list, so a column added
        later is read-only without anybody having to remember."""
        readonly = set(self.admin.get_readonly_fields(
            self.request_from(self.operator)
        ))

        self.assertEqual(
            {field.name for field in EmailDispatch._meta.fields}, readonly
        )

    def test_deleting_is_for_superusers_alone(self):
        staff = make_account('staff@example.com', is_staff=True)
        boss = make_account('boss@example.com', is_staff=True, is_superuser=True)

        self.assertFalse(
            self.admin.has_delete_permission(self.request_from(staff))
        )
        self.assertTrue(
            self.admin.has_delete_permission(self.request_from(boss))
        )

    def test_the_recipient_column_shows_the_nickname_the_club_knows(self):
        """``display_name``, as the appointment page does, and for the same
        reason: an address is not what the club calls somebody."""
        self.assertEqual('Thabo', self.admin.person(self.make()))

    def test_an_operators_send_is_attributed_to_the_operator(self):
        dispatch = self.make(
            trigger=EmailDispatch.Trigger.OPERATOR,
            triggered_by=self.operator,
        )

        self.assertEqual(
            self.operator.display_name, self.admin.caused_by(dispatch)
        )

    def test_a_send_with_nobody_to_name_shows_what_caused_it_instead(self):
        """The blank is not a gap. A sign-in code is asked for by somebody who is
        not signed in, and the column says so rather than showing nothing."""
        self.assertEqual(
            EmailDispatch.Trigger.MEMBER.label,
            self.admin.caused_by(self.make()),
        )

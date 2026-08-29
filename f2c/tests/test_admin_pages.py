"""Every admin page renders, for an account holding all three relationships.

A shallow test on purpose, and it lives in ``f2c`` for the reason
``f2c.testing`` does: it is a statement about the admin site as a whole, and no
single app owns it.

``manage.py check`` already runs Django's admin checks, and they are good at
what they cover -- a field named in ``fieldsets`` that is not on the model, a
``list_filter`` entry that does not resolve. What they do not cover is anything
that only happens while a page is being drawn: a ``@admin.display`` method that
raises on a value it did not expect, a ``reverse()`` to a route that is no
longer registered, an ``autocomplete_fields`` entry pointing at an admin with no
``search_fields``. All three are 500s on a page that passed every check.

The fixture is deliberately the most-connected account there is -- a member who
also administers the club and is appointed to a farm. C28 made that expressible
and the panels that render it walk all three relationships, so it exercises more
of every page than three single-relationship accounts would.

This asserts that a page renders, and nothing about what is on it. What each
page *says* is tested beside the admin it belongs to.
"""
from django.test import TestCase
from django.urls import reverse

from app.club.membership.models import ClubMembership
from app.core.storefronts.models import StorefrontStaff
from f2c.testing import (
    make_account,
    make_administrator,
    make_cultivator,
    make_member,
    make_producer,
    make_sharing_placeholder,
)


class AdminPageTests(TestCase):
    def setUp(self):
        # A superuser, because this is about whether the pages draw at all --
        # who may reach which page is a different question, tested where the
        # permission is resolved.
        self.operator = make_account(
            'operator@example.com', is_staff=True, is_superuser=True
        )
        self.client.force_login(self.operator)

        self.person = make_member('member@example.com', nickname='Thabo')
        make_administrator(account=self.person)
        _, self.producer = make_cultivator(
            account=self.person, trading_name='Kloof Farm'
        )

    def test_the_three_identity_pages_render(self):
        """The pages C27 and C28 split the account into.

        Two of them did not exist before Block 0.5, and the third lost its
        nickname field and its Sharing member panel to them.
        """
        membership = ClubMembership.objects.get(user=self.person)
        appointment = StorefrontStaff.objects.get(user=self.person)

        for name, args in (
            ('admin:index', ()),
            ('admin:accounts_user_changelist', ()),
            ('admin:accounts_user_change', (self.person.pk,)),
            ('admin:accounts_user_add', ()),
            ('admin:membership_clubmembership_changelist', ()),
            ('admin:membership_clubmembership_change', (membership.pk,)),
            ('admin:membership_clubmembership_add', ()),
            ('admin:storefronts_storefrontstaff_changelist', ()),
            ('admin:storefronts_storefrontstaff_change', (appointment.pk,)),
            ('admin:storefronts_storefrontstaff_add', ()),
            ('admin:producers_producer_change', (self.producer.pk,)),
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args), follow=True)
                self.assertEqual(response.status_code, 200)

    def test_a_produce_market_customer_renders_too(self):
        """The account shape that did not exist before the split.

        No membership, no appointment, nothing to join to — so every panel on
        the account page takes its empty branch, which is the half a fixture
        holding all three relationships never reaches.
        """
        customer = make_account('customer@example.com')

        response = self.client.get(
            reverse('admin:accounts_user_change', args=(customer.pk,))
        )

        self.assertEqual(response.status_code, 200)

    def test_a_sharing_placeholder_renders_on_the_membership_page(self):
        """C6: no name, no email address, no identity number.

        Every display method on both pages falls back for this row, and a
        placeholder is the one record staff cannot reach any other way.
        """
        placeholder = make_sharing_placeholder(
            'Sharer', producer=make_producer('Other Farm')
        )
        membership = ClubMembership.objects.get(user=placeholder)

        for name, args in (
            ('admin:membership_clubmembership_change', (membership.pk,)),
            ('admin:accounts_user_change', (placeholder.pk,)),
        ):
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200)

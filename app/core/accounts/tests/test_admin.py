"""Tests for the account admin after the identity split.

The page lost two things in Block 0.5 and gained one. It lost the nickname
field, which moved to ``ClubMembership`` with the unique index that governs it,
and the Sharing member panel, most of which C6 deleted outright. What it gained
is the Relationships panel: the three rows that decide what an account may do,
linked rather than reproduced, because C27 split identity from membership
precisely so that one page does not answer for both.

Two of these tests are about correctness of the page and two are about what it
costs to draw. ``display_name`` prefers the club nickname, which is now one
table away, so both the list and this panel walk a reverse one-to-one --
unselected, that is a query per account on a page that shows a hundred of them.
That is risk 11 in ``design/features/roles-and-permissions.md``, and it is the
kind of regression nothing but a query count catches.
"""
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from app.commerce.producers.models import ProducerRole
from app.core.accounts.admin import UserAdmin
from app.core.accounts.models import User
from app.core.storefronts.models import Storefront
from f2c.testing import (
    make_account,
    make_administrator,
    make_cultivator,
    make_member,
    make_producer,
    make_sharing_placeholder,
)


class RelationshipPanelTests(TestCase):
    """What the panel lists, for each shape of account."""

    def setUp(self):
        self.admin = UserAdmin(User, AdminSite())
        self.request = RequestFactory().get('/admin/')
        self.request.user = make_account('operator@example.com', is_staff=True)

    def panel_for(self, user):
        return str(self.admin.relationships(
            User.objects.with_platform_roles().get(pk=user.pk)
        ))

    def test_an_account_with_no_relationships_says_so_in_a_sentence(self):
        """A produce-market customer. Not an empty panel — an explained one.

        The state that could not exist before the split, when every account was
        a member of the club by construction.
        """
        panel = self.panel_for(make_account('customer@example.com'))

        self.assertIn('joined no club', panel)
        self.assertNotIn('<li>', panel)

    def test_a_membership_is_listed_with_its_standing(self):
        panel = self.panel_for(make_member('member@example.com', nickname='Thabo'))

        self.assertIn('Club membership', panel)
        self.assertIn('Active', panel)
        self.assertIn('/membership/clubmembership/', panel)

    def test_a_storefront_appointment_names_the_storefront_it_is_over(self):
        """"Administrator" without "of what" is what C28 retired."""
        panel = self.panel_for(
            make_administrator('market@example.com', storefront=Storefront.MARKET)
        )

        self.assertIn('Produce market', panel)
        self.assertIn('/storefronts/storefrontstaff/', panel)

    def test_a_producer_appointment_names_the_farm_and_the_rights(self):
        """It links to the farm, because that is where the row is administered.

        The appointment is an inline on ``ProducerAdmin`` — an appointment with
        no farm is not an appointment — so there is no page of its own to point
        at.
        """
        user, producer = make_cultivator(
            'grower@example.com', trading_name='Kloof Farm',
            role=ProducerRole.LIMITED,
        )

        panel = self.panel_for(user)

        self.assertIn('Kloof Farm', panel)
        self.assertIn('limited', panel.lower())
        self.assertIn(f'/producers/producer/{producer.pk}/', panel)

    def test_somebody_who_holds_all_three_gets_all_three(self):
        """The union a single role column could not express, on one page.

        The case the design document carried as an accepted limitation: that
        somebody who both administers and buys needs two accounts.
        """
        account = make_member('everything@example.com', nickname='Thabo')
        make_administrator(account=account)
        make_cultivator(account=account, trading_name='Kloof Farm')

        panel = self.panel_for(account)

        self.assertEqual(panel.count('<li>'), 3)

    def test_an_unsaved_account_is_not_asked_for_relationships(self):
        """The add form renders this field before there is a row to join to."""
        self.assertIn('Saved once', str(self.admin.relationships(User())))


class PanelCostTests(TestCase):
    """The panel and the list are joins, not loops."""

    def setUp(self):
        self.admin = UserAdmin(User, AdminSite())
        self.request = RequestFactory().get('/admin/')
        self.request.user = make_account('operator@example.com', is_staff=True)

    def test_the_changelist_joins_the_membership_the_nickname_lives_on(self):
        """``display_name`` is on ``list_display`` and reads across the split.

        Without the ``select_related`` this is one query per row, and the page
        still renders correctly — which is why it is counted rather than
        looked at.
        """
        for index in range(5):
            make_member(f'member{index}@example.com', nickname=f'Member{index}')

        rows = list(self.admin.get_queryset(self.request))

        with self.assertNumQueries(0):
            names = sorted(row.display_name for row in rows)
        self.assertEqual(
            names[:5], ['Member0', 'Member1', 'Member2', 'Member3', 'Member4']
        )

    def test_an_account_with_no_membership_costs_no_extra_query_either(self):
        """A produce customer has no row to join to, and a miss is cached.

        The failure this guards is a ``select_related`` that silently stops
        covering the null case and falls back to a lazy fetch per customer.
        """
        customer = make_account('customer@example.com')

        rows = {row.pk: row for row in self.admin.get_queryset(self.request)}

        with self.assertNumQueries(0):
            self.assertEqual(
                rows[customer.pk].display_name, 'customer@example.com'
            )


class SearchTests(TestCase):
    """Staff can still find somebody by the name the club knows them by."""

    def setUp(self):
        self.admin = UserAdmin(User, AdminSite())
        self.request = RequestFactory().get('/admin/')
        self.request.user = make_account('operator@example.com', is_staff=True)

    def search(self, term):
        results, _ = self.admin.get_search_results(
            self.request, User.objects.all(), term
        )
        return list(results)

    def test_a_member_is_found_by_their_nickname_across_the_split(self):
        """The field left this table with C27; the search followed it.

        Without the relation in ``search_fields`` the nickname would simply
        stop being searchable here, which nothing else would report.
        """
        member = make_member('member@example.com', nickname='Thabo')

        self.assertEqual(self.search('Thabo'), [member])

    def test_a_placeholder_is_findable_by_the_only_name_it_has(self):
        """C6 left a placeholder with a nickname and nothing else.

        No email address, no first name, no identity number — so if the
        nickname were not searched, staff could not reach the row at all.
        """
        placeholder = make_sharing_placeholder(
            'Sharer', producer=make_producer('Kloof Farm')
        )

        self.assertEqual(self.search('Sharer'), [placeholder])

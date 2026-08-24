"""Tests for the payments admin, which is entirely about what it will not do.

The invariant is that **nothing here is editable**. A payment is a fact about
the outside world; ``paid_until`` decides whether somebody can sign in. An admin
that let either be typed would grant memberships nobody paid for and leave our
records disagreeing with Payfast's, which is the one thing a reconciliation
exists to detect.

Asserted through the admin's own permission hooks and through a real POST,
because ``readonly_fields`` alone still renders a form that accepts a submission
for anything left off the list.
"""
from decimal import Decimal

from django.contrib.admin.sites import site
from django.test import Client
from django.urls import reverse

from app.accounts.models import User
from app.payments.models import Payment, PaymentStatus, Subscription

from .support import PaymentsTestCase


class PaymentsAdminTests(PaymentsTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_superuser(
            email='staff@example.com', password='not-a-real-password'
        )
        self.client = Client()
        self.client.force_login(self.staff)
        self.payment = Payment.objects.create(
            subscription=self.subscription,
            gateway_payment_id='PF-1',
            status=PaymentStatus.COMPLETE,
            amount_gross=Decimal('150.00'),
        )

    def test_the_subscription_list_renders(self):
        response = self.client.get(
            reverse('admin:payments_subscription_changelist')
        )

        self.assertEqual(response.status_code, 200)

    def test_the_payment_list_renders(self):
        response = self.client.get(reverse('admin:payments_payment_changelist'))

        self.assertEqual(response.status_code, 200)

    def test_a_subscription_cannot_be_added(self):
        """One added here would have no member behind it and no mandate at
        Payfast."""
        self.assertFalse(
            site._registry[Subscription].has_add_permission(self._request())
        )

    def test_a_subscription_cannot_be_changed(self):
        self.assertFalse(
            site._registry[Subscription].has_change_permission(self._request())
        )

    def test_a_subscription_cannot_be_deleted(self):
        self.assertFalse(
            site._registry[Subscription].has_delete_permission(self._request())
        )

    def test_a_payment_cannot_be_added_changed_or_deleted(self):
        admin = site._registry[Payment]
        request = self._request()

        self.assertFalse(admin.has_add_permission(request))
        self.assertFalse(admin.has_change_permission(request))
        self.assertFalse(admin.has_delete_permission(request))

    def test_posting_a_new_paid_up_date_changes_nothing(self):
        """The assertion that matters: ``readonly_fields`` still renders a form.

        A staff member who submits one -- or anybody who forges the POST -- must
        not be able to extend a membership by a year.
        """
        url = reverse(
            'admin:payments_subscription_change', args=(self.subscription.pk,)
        )

        self.client.post(url, data={'paid_until': '2099-01-01'})
        self.subscription.refresh_from_db()

        self.assertIsNone(self.subscription.paid_until)

    def test_the_checkout_token_is_not_searchable(self):
        """It is a bearer credential. A searchable one ends up in a screenshot,
        and knowing it is enough to pay somebody else's subscription."""
        admin = site._registry[Subscription]

        self.assertNotIn('checkout_token', admin.search_fields)
        self.assertNotIn('gateway_token', admin.search_fields)

    def test_the_token_is_not_on_the_list_display_either(self):
        admin = site._registry[Subscription]

        self.assertNotIn('checkout_token', admin.list_display)

    def _request(self):
        from django.test import RequestFactory

        request = RequestFactory().get('/admin/')
        request.user = self.staff
        return request

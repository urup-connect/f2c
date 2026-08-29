"""Tests for the two payment endpoints.

The service tests cover what a payment does. These cover the contract, and for
the notification endpoint the contract is unusually load-bearing: **Payfast
decides whether to redeliver based on the status code**, so a wrong one is not a
cosmetic bug. A 400 where a 503 belongs drops a real payment on the floor; a 503
where a 400 belongs makes Payfast retry a forgery forever.

There is also an assertion here that exists nowhere else: the endpoint reads the
raw body rather than ``request.POST``, because Payfast signs its notification
over the fields **in the order it sent them**. ``test_field_order_is_preserved``
is the only test in the suite that would catch a regression to
``request.POST.items()``, which passes on almost every payload and fails on the
ones where a dict happens to reorder.
"""
import json
from unittest.mock import patch
from urllib.parse import urlencode

from django.core.cache import cache
from django.test import Client

from app.core.accounts.models import UserStatus
from app.core.payments import gateway
from app.core.payments.models import Payment, Subscription, SubscriptionStatus

from .support import PAYFAST, PaymentsTestCase, notification

CHECKOUT = '/api/payments/checkout/'
NOTIFY = '/api/payments/payfast/notify'

#: The test client's own address. Declared to be Payfast's for the tests that
#: need to get past the source check; the check itself is covered in
#: ``test_gateway``.
LOCAL = '127.0.0.1'


class PaymentEndpointTests(PaymentsTestCase):
    def setUp(self):
        super().setUp()
        # Limits live in the cache and are keyed on client IP, so without this
        # they carry from one test into the next.
        cache.clear()
        self.client = Client()

    def body(self, response):
        return json.loads(response.content)

    def notify(self, pairs, **extra):
        """POST a notification as form-encoded data, which is how Payfast sends it."""
        return self.client.post(
            NOTIFY,
            data=urlencode(pairs),
            content_type='application/x-www-form-urlencoded',
            **extra,
        )


class CheckoutEndpointTests(PaymentEndpointTests):
    def test_a_fresh_token_returns_a_signed_checkout(self):
        response = self.client.get(CHECKOUT + self.subscription.checkout_token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.body(response)['url'], 'https://sandbox.payfast.co.za/eng/process'
        )

    def test_the_signature_it_returns_verifies(self):
        response = self.client.get(CHECKOUT + self.subscription.checkout_token)

        fields = dict(self.body(response)['fields'])
        signature = fields.pop('signature')

        self.assertEqual(
            signature, gateway.checkout_signature(fields, PAYFAST.passphrase)
        )

    def test_it_carries_nothing_about_the_member(self):
        """The decision the whole endpoint rests on. It is reached with a bearer
        token in a URL, and a URL is shared, logged and cached."""
        response = self.client.get(CHECKOUT + self.subscription.checkout_token)
        text = response.content.decode()

        for value in (
            self.member.first_name,
            self.member.last_name,
            self.member.club_nickname,
            self.member.email,
            self.member.mobile,
            str(self.member.pk),
        ):
            with self.subTest(value=value):
                self.assertNotIn(value, text)

    def test_it_never_carries_the_identity_number(self):
        from app.club.membership.tests.support import ADULT_ID

        response = self.client.get(CHECKOUT + self.subscription.checkout_token)

        self.assertNotIn(ADULT_ID, response.content.decode())

    def test_an_unknown_token_is_404(self):
        response = self.client.get(CHECKOUT + 'no-such-token')

        self.assertEqual(response.status_code, 404)

    def test_an_unknown_token_says_nothing_about_why(self):
        """Same answer as an expired one and an already-paid one. Telling them
        apart would make this a way to probe whether a token was ever real."""
        unknown = self.body(self.client.get(CHECKOUT + 'no-such-token'))

        self.subscription.status = SubscriptionStatus.CANCELLED
        self.subscription.save(update_fields=['status'])
        cancelled = self.body(
            self.client.get(CHECKOUT + self.subscription.checkout_token)
        )

        self.assertEqual(unknown, cancelled)

    def test_it_needs_no_session(self):
        """It could not have one: the whole point of Pending payment is that the
        member cannot sign in yet."""
        response = self.client.get(CHECKOUT + self.subscription.checkout_token)

        self.assertEqual(response.status_code, 200)

    def test_reading_it_twice_gives_the_same_answer(self):
        """How a member who abandoned the Payfast page gets back."""
        first = self.client.get(CHECKOUT + self.subscription.checkout_token)
        second = self.client.get(CHECKOUT + self.subscription.checkout_token)

        self.assertEqual(self.body(first), self.body(second))

    def test_reading_it_writes_nothing(self):
        before = self.subscription.checkout_expires_at

        self.client.get(CHECKOUT + self.subscription.checkout_token)
        self.subscription.refresh_from_db()

        self.assertEqual(self.subscription.checkout_expires_at, before)


class NotifyEndpointTests(PaymentEndpointTests):
    """The endpoint that activates a membership. Status codes are the contract."""

    def setUp(self):
        super().setUp()
        # The two network checks, stood down at the boundary rather than inside
        # the service, so everything from the raw body inwards runs for real.
        self.addresses = patch.object(
            gateway, 'payfast_addresses', return_value={LOCAL}
        )
        self.confirm = patch.object(
            gateway, 'confirm_with_payfast', return_value=True
        )
        self.addresses.start()
        self.confirm.start()
        self.addCleanup(self.addresses.stop)
        self.addCleanup(self.confirm.stop)

    def test_a_good_notification_is_accepted(self):
        response = self.notify(notification(self.subscription))

        self.assertEqual(response.status_code, 200)

    def test_it_activates_the_member(self):
        self.notify(notification(self.subscription))
        subscription, member = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(member.club_membership.status, UserStatus.ACTIVE)

    def test_field_order_is_preserved_from_the_raw_body(self):
        """The one test that catches a regression to ``request.POST``.

        Payfast signs its notification over the fields in the order it sent
        them. This payload is signed in an order a mapping is likely to
        reorder, so a re-serialised body would fail the signature check and this
        would come back 400.
        """
        pairs = notification(self.subscription)
        # Signed over this exact sequence; anything that rebuilds it loses.
        self.assertEqual(pairs[0][0], 'm_payment_id')

        response = self.notify(pairs)

        self.assertEqual(response.status_code, 200)

    def test_a_repeated_delivery_is_accepted_and_changes_nothing(self):
        """Payfast retries anything it did not get a 2xx for. A non-2xx here
        would ask it to retry forever."""
        pairs = notification(self.subscription, payment_id='PF-RETRY')
        self.notify(pairs)
        self.subscription.refresh_from_db()
        paid_until = self.subscription.paid_until

        response = self.notify(pairs)
        self.subscription.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(self.subscription.paid_until, paid_until)

    def test_a_forged_notification_is_refused_finally(self):
        """400, not 503: no redelivery will make a bad signature good."""
        response = self.notify(notification(self.subscription, sign=False))

        self.assertEqual(response.status_code, 400)
        self.assertStillPendingPayment()

    def test_a_notification_from_elsewhere_is_refused(self):
        self.addresses.stop()
        with patch.object(gateway, 'payfast_addresses', return_value={'8.8.8.8'}):
            response = self.notify(notification(self.subscription))
        self.addresses.start()

        self.assertEqual(response.status_code, 400)
        self.assertStillPendingPayment()

    def test_the_wrong_amount_is_refused(self):
        response = self.notify(notification(self.subscription, amount='1.00'))

        self.assertEqual(response.status_code, 400)
        self.assertStillPendingPayment()

    def test_a_notification_payfast_denies_sending_is_refused(self):
        with patch.object(gateway, 'confirm_with_payfast', return_value=False):
            response = self.notify(notification(self.subscription))

        self.assertEqual(response.status_code, 400)
        self.assertStillPendingPayment()

    def test_a_notification_payfast_could_not_be_asked_about_asks_for_a_retry(self):
        """503, not 400. Nothing is known to be wrong, and a 400 here would drop
        a real payment on the floor."""
        with patch.object(gateway, 'confirm_with_payfast', return_value=None):
            response = self.notify(notification(self.subscription))

        self.assertEqual(response.status_code, 503)
        self.assertStillPendingPayment()

    def test_the_refusal_never_says_which_check_failed(self):
        """That reason goes to the log, where the attacker cannot read which one
        to fix next."""
        forged = self.body(self.notify(notification(self.subscription, sign=False)))
        wrong_amount = self.body(
            self.notify(notification(self.subscription, amount='1.00'))
        )

        self.assertEqual(forged, wrong_amount)

    def test_the_response_carries_nothing_about_the_member(self):
        """A notification endpoint's response is the one part of this flow an
        attacker gets to see."""
        response = self.notify(notification(self.subscription))
        text = response.content.decode()

        for value in (self.member.email, self.member.club_nickname, str(self.member.pk)):
            with self.subTest(value=value):
                self.assertNotIn(value, text)

    def test_it_needs_no_csrf_token(self):
        """Payfast has no session and no token to present. What stands in for
        both is the four-check verification."""
        response = Client(enforce_csrf_checks=True).post(
            NOTIFY,
            data=urlencode(notification(self.subscription)),
            content_type='application/x-www-form-urlencoded',
        )

        self.assertEqual(response.status_code, 200)

    def test_an_empty_body_is_refused_rather_than_crashing(self):
        response = self.client.post(
            NOTIFY, data='', content_type='application/x-www-form-urlencoded'
        )

        self.assertEqual(response.status_code, 400)

    def test_a_body_that_is_not_form_encoded_is_refused(self):
        response = self.client.post(
            NOTIFY, data='{"not": "a form"}', content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)

    def test_a_cancellation_is_accepted_and_leaves_the_member_signed_in(self):
        self.notify(notification(self.subscription, payment_id='PF-1'))

        response = self.notify(
            notification(self.subscription, status='CANCELLED', payment_id='PF-1')
        )
        subscription, member = self.reload()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        self.assertEqual(member.club_membership.status, UserStatus.ACTIVE)

    def test_it_is_not_throttled(self):
        """Every monthly subscription renews on the same day, and Payfast
        delivers them in a burst. A dropped notification is a member who paid
        and cannot sign in. See ``throttles``.
        """
        for index in range(40):
            response = self.notify(
                notification(self.subscription, payment_id=f'PF-{index}')
            )
            self.assertEqual(response.status_code, 200, f'delivery {index}')


class BehindProxyTests(PaymentEndpointTests):
    """The forwarded-header path, which is opt-in per deployment."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(gateway, 'confirm_with_payfast', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_forwarded_address_is_ignored_by_default(self):
        """Reading it unconditionally would hand an attacker the source check:
        they would simply claim to be Payfast."""
        with patch.object(
            gateway, 'payfast_addresses', return_value={'197.97.145.144'}
        ):
            response = self.notify(
                notification(self.subscription),
                HTTP_X_FORWARDED_FOR='197.97.145.144',
            )

        self.assertEqual(response.status_code, 400)
        self.assertStillPendingPayment()

    def test_the_forwarded_address_is_used_when_the_deployment_says_so(self):
        proxied = gateway.sandbox_settings(behind_proxy=True)

        with self.settings(PAYFAST=proxied):
            with patch.object(
                gateway, 'payfast_addresses', return_value={'197.97.145.144'}
            ):
                response = self.notify(
                    notification(self.subscription, config=proxied),
                    HTTP_X_FORWARDED_FOR='197.97.145.144, 10.0.0.1',
                )

        self.assertEqual(response.status_code, 200)


class RegistrationHandoffTests(PaymentEndpointTests):
    """Registration to Payfast, end to end, as the frontend walks it."""

    def test_the_token_registration_returns_resolves_to_a_checkout(self):
        response = self.client.get(
            CHECKOUT + self.registration.checkout_token
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.body(response)['fields']['m_payment_id'],
            str(Subscription.objects.get().pk),
        )

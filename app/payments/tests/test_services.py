"""Tests for what a payment does to a membership.

Four properties dominate, and none of them is visible in a return value.

The first is that **a completed payment lets the member sign in**. It is
asserted through the authentication stack rather than by reading the column,
because ``is_active`` is what Django filters on and a status that failed to
derive it would still look right in a database row.

The second is that **applying a notification twice does nothing twice**. Payfast
retries anything it did not get a 2xx for, and the retry carries the same
payment id. A regression there is silent: every response still looks correct and
the member has quietly been given a second cycle of membership for free.

The third is that **a notification that does not verify changes nothing**. Not
the subscription, not the account, not a payment row. The assertions are about
what did not happen, which is the only way to test a security control.

The fourth is that **a cancellation does not switch anybody off**. The member
keeps the time they paid for, and ``lapse_overdue`` is what eventually acts.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core import mail
from django.utils import timezone

from app.accounts.models import UserStatus
from app.payments import gateway, services
from app.payments.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)

from .support import MONTHLY_DAYS, PAYFAST, PAYFAST_IP, PaymentsTestCase, notification


class ApplyMixin:
    """Applies a notification with the two network checks stood down.

    The source address is injected and the callback to Payfast is skipped,
    because neither is what these tests are about -- both have their own tests
    in ``test_gateway``. Every other check runs for real.
    """

    def apply(self, pairs, **kwargs):
        return services.apply_notification(
            pairs,
            source_ip=PAYFAST_IP,
            addresses={PAYFAST_IP},
            confirm=False,
            **kwargs,
        )


class OpenSubscriptionTests(PaymentsTestCase):
    def test_registration_opens_exactly_one_subscription(self):
        self.assertEqual(Subscription.objects.filter(user=self.member).count(), 1)

    def test_it_starts_awaiting_payment(self):
        self.assertEqual(self.subscription.status, SubscriptionStatus.PENDING)

    def test_it_has_nothing_paid_up(self):
        self.assertIsNone(self.subscription.paid_until)

    def test_it_has_no_payfast_mandate_yet(self):
        self.assertEqual(self.subscription.gateway_token, '')

    def test_it_copies_the_configured_price_onto_the_row(self):
        """Not read back from settings later. Raising the fee must not rewrite
        what an existing member agreed to."""
        self.assertEqual(self.subscription.amount, Decimal('150.00'))
        self.assertEqual(self.subscription.frequency, gateway.FREQUENCIES['monthly'])

    def test_a_later_price_change_does_not_touch_it(self):
        raised = gateway.sandbox_settings(amount=Decimal('999.00'))

        with self.settings(PAYFAST=raised):
            self.subscription.refresh_from_db()

        self.assertEqual(self.subscription.amount, Decimal('150.00'))

    def test_the_checkout_is_usable_immediately(self):
        self.assertTrue(self.subscription.checkout_is_usable())

    def test_the_checkout_expires(self):
        self.assertGreater(self.subscription.checkout_expires_at, timezone.now())
        self.assertLess(
            self.subscription.checkout_expires_at,
            timezone.now() + timedelta(seconds=PAYFAST.checkout_ttl_seconds + 60),
        )

    def test_the_member_cannot_sign_in(self):
        self.assertStillPendingPayment()

    def test_a_second_live_subscription_is_refused_by_the_database(self):
        """Two live mandates against one account is Payfast billing twice."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            services.open_subscription(self.member)


class CheckoutTests(PaymentsTestCase):
    def test_a_fresh_token_resolves(self):
        found = services.find_checkout(self.subscription.checkout_token)

        self.assertEqual(found.pk, self.subscription.pk)

    def test_an_unknown_token_does_not(self):
        with self.assertRaises(services.CheckoutUnavailable):
            services.find_checkout('not-a-token')

    def test_an_expired_token_does_not(self):
        self.subscription.checkout_expires_at = timezone.now() - timedelta(seconds=1)
        self.subscription.save(update_fields=['checkout_expires_at'])

        with self.assertRaises(services.CheckoutUnavailable):
            services.find_checkout(self.subscription.checkout_token)

    def test_a_cancelled_subscription_has_no_checkout(self):
        self.subscription.status = SubscriptionStatus.CANCELLED
        self.subscription.save(update_fields=['status'])

        with self.assertRaises(services.CheckoutUnavailable):
            services.find_checkout(self.subscription.checkout_token)

    def test_the_checkout_names_the_subscription_to_payfast(self):
        checkout = services.checkout_for(self.subscription)

        self.assertEqual(
            checkout['fields']['m_payment_id'], str(self.subscription.pk)
        )

    def test_the_checkout_carries_the_amount_that_was_agreed(self):
        checkout = services.checkout_for(self.subscription)

        self.assertEqual(checkout['fields']['amount'], '150.00')


class CompletedPaymentTests(ApplyMixin, PaymentsTestCase):
    def test_it_records_the_payment(self):
        self.apply(notification(self.subscription, payment_id='PF-9'))

        payment = Payment.objects.get()
        self.assertEqual(payment.gateway_payment_id, 'PF-9')
        self.assertEqual(payment.status, PaymentStatus.COMPLETE)
        self.assertEqual(payment.amount_gross, Decimal('150.00'))

    def test_it_stores_the_fee_as_payfast_reported_it(self):
        """Negative in Payfast's own figures. A sign flipped on the way in is a
        reconciliation nobody can explain."""
        self.apply(notification(self.subscription))

        self.assertEqual(Payment.objects.get().amount_fee, Decimal('-5.25'))

    def test_it_makes_the_subscription_active(self):
        self.apply(notification(self.subscription))
        subscription, _ = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertIsNotNone(subscription.activated_at)

    def test_it_stores_the_payfast_mandate(self):
        self.apply(notification(self.subscription, token='the-mandate'))
        subscription, _ = self.reload()

        self.assertEqual(subscription.gateway_token, 'the-mandate')

    def test_it_pays_the_membership_up_one_cycle(self):
        self.apply(notification(self.subscription))
        subscription, _ = self.reload()

        self.assertEqual(
            subscription.paid_until,
            gateway.billing_date() + timedelta(days=MONTHLY_DAYS),
        )

    def test_it_activates_the_account(self):
        self.apply(notification(self.subscription))
        _, member = self.reload()

        self.assertEqual(member.status, UserStatus.ACTIVE)
        self.assertTrue(member.is_active)

    def test_the_member_can_now_be_authenticated(self):
        """Through the auth stack, not by reading the column: `is_active` is
        what Django filters on in SQL."""
        self.apply(notification(self.subscription))
        _, member = self.reload()

        self.assertIsNone(authenticate(username=member.email, password='wrong'))
        self.assertTrue(
            type(member).objects.active_by_email(member.email) is not None
        )

    def test_it_spends_the_checkout(self):
        """A link still sitting in an inbox must not start a second mandate."""
        self.apply(notification(self.subscription))
        subscription, _ = self.reload()

        self.assertFalse(subscription.checkout_is_usable())
        with self.assertRaises(services.CheckoutUnavailable):
            services.find_checkout(subscription.checkout_token)

    def test_the_payment_records_what_it_bought(self):
        self.apply(notification(self.subscription))
        subscription, _ = self.reload()

        self.assertEqual(Payment.objects.get().covers_until, subscription.paid_until)


class DuplicateNotificationTests(ApplyMixin, PaymentsTestCase):
    """Payfast retries. The retry must do nothing."""

    def setUp(self):
        super().setUp()
        self.pairs = notification(self.subscription, payment_id='PF-SAME')
        self.apply(self.pairs)
        self.subscription.refresh_from_db()
        self.first_paid_until = self.subscription.paid_until

    def test_the_second_delivery_reports_a_duplicate(self):
        applied = self.apply(self.pairs)

        self.assertTrue(applied.duplicate)

    def test_it_writes_no_second_payment(self):
        self.apply(self.pairs)

        self.assertEqual(Payment.objects.count(), 1)

    def test_it_does_not_extend_the_membership_again(self):
        """The regression this whole test class exists for: silent, and it hands
        out a free cycle of membership."""
        self.apply(self.pairs)
        subscription, _ = self.reload()

        self.assertEqual(subscription.paid_until, self.first_paid_until)

    def test_a_genuinely_new_payment_does_extend_it(self):
        """The other side of the rule -- otherwise the fix for the above is to
        stop renewals working."""
        self.apply(notification(self.subscription, payment_id='PF-NEXT'))
        subscription, _ = self.reload()

        self.assertEqual(
            subscription.paid_until, self.first_paid_until + timedelta(days=MONTHLY_DAYS)
        )
        self.assertEqual(Payment.objects.count(), 2)


class RenewalTests(ApplyMixin, PaymentsTestCase):
    def test_a_renewal_extends_from_the_paid_up_date_not_from_today(self):
        """An early renewal adds a cycle rather than resetting the clock."""
        self.apply(notification(self.subscription, payment_id='PF-1'))
        self.subscription.refresh_from_db()
        first = self.subscription.paid_until

        self.apply(notification(self.subscription, payment_id='PF-2'))
        subscription, _ = self.reload()

        self.assertEqual(subscription.paid_until, first + timedelta(days=MONTHLY_DAYS))

    def test_a_renewal_after_a_gap_does_not_backdate_the_gap(self):
        """Paying late buys a cycle from today, not from when it lapsed."""
        self.apply(notification(self.subscription, payment_id='PF-1'))
        self.subscription.refresh_from_db()
        self.subscription.paid_until = gateway.billing_date() - timedelta(days=90)
        self.subscription.save(update_fields=['paid_until'])

        self.apply(notification(self.subscription, payment_id='PF-2'))
        subscription, _ = self.reload()

        self.assertEqual(
            subscription.paid_until,
            gateway.billing_date() + timedelta(days=MONTHLY_DAYS),
        )

    def test_a_renewal_for_an_active_member_is_quiet(self):
        """Every renewal takes this path -- it is the majority of notifications
        this application will ever see. A warning here would bury the case that
        matters under a monthly flood."""
        self.apply(notification(self.subscription, payment_id='PF-1'))

        with self.assertNoLogs('app.payments.services', level='WARNING'):
            self.apply(notification(self.subscription, payment_id='PF-2'))

    def test_a_payment_against_an_account_awaiting_verification_is_flagged(self):
        """Recorded rather than refused -- the money moved -- and loud, because
        nothing else will tell anybody."""
        self.member.status = UserStatus.PENDING
        self.member.save(update_fields=['status'])

        with self.assertLogs('app.payments.services', level='WARNING') as logs:
            self.apply(notification(self.subscription, payment_id='PF-ODD'))

        self.assertIn('A human should look at this', logs.output[0])
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_renewal_reactivates_a_member_who_had_lapsed(self):
        self.apply(notification(self.subscription, payment_id='PF-1'))
        self.member.refresh_from_db()
        self.member.deactivate()

        self.apply(notification(self.subscription, payment_id='PF-2'))
        _, member = self.reload()

        self.assertEqual(member.status, UserStatus.ACTIVE)


class RefusedNotificationTests(ApplyMixin, PaymentsTestCase):
    """Nothing verifies, so nothing changes. Assertions are about absence."""

    def assertNothingHappened(self):
        subscription, member = self.reload()

        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(subscription.status, SubscriptionStatus.PENDING)
        self.assertIsNone(subscription.paid_until)
        self.assertEqual(member.status, UserStatus.PENDING_PAYMENT)

    def test_a_forged_signature_changes_nothing(self):
        with self.assertRaises(gateway.NotificationRejected):
            self.apply(notification(self.subscription, sign=False))

        self.assertNothingHappened()

    def test_a_notification_from_elsewhere_changes_nothing(self):
        with self.assertRaises(gateway.NotificationRejected):
            services.apply_notification(
                notification(self.subscription),
                source_ip='203.0.113.9',
                addresses={PAYFAST_IP},
                confirm=False,
            )

        self.assertNothingHappened()

    def test_a_one_rand_payment_does_not_activate_a_membership(self):
        """The check that stops a correctly signed notification for the wrong
        amount buying a membership."""
        with self.assertRaises(gateway.NotificationRejected) as raised:
            self.apply(notification(self.subscription, amount='1.00'))

        self.assertIn('amount', str(raised.exception))
        self.assertNothingHappened()

    def test_an_amount_is_checked_against_the_row_not_the_configuration(self):
        """A member who joined at R150 stays on R150 when the fee goes up.
        Reading the setting here would make every existing member's next
        renewal look like fraud."""
        raised_price = gateway.sandbox_settings(amount=Decimal('999.00'))

        with self.settings(PAYFAST=raised_price):
            self.apply(
                notification(self.subscription, amount='150.00', config=raised_price)
            )

        subscription, member = self.reload()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_a_notification_naming_no_subscription_changes_nothing(self):
        import uuid

        pairs = notification(self.subscription)
        stranger = [
            (k, str(uuid.uuid7()) if k == 'm_payment_id' else v) for k, v in pairs
        ]
        # Re-signed, so this tests the lookup rather than the signature.
        stranger = [(k, v) for k, v in stranger if k != 'signature']
        stranger.append(
            ('signature', gateway.notification_signature(stranger, PAYFAST.passphrase))
        )

        with self.assertRaises(gateway.NotificationRejected):
            self.apply(stranger)

        self.assertNothingHappened()

    def test_an_unparseable_reference_changes_nothing(self):
        pairs = [
            (k, 'not-a-uuid' if k == 'm_payment_id' else v)
            for k, v in notification(self.subscription)
            if k != 'signature'
        ]
        pairs.append(
            ('signature', gateway.notification_signature(pairs, PAYFAST.passphrase))
        )

        with self.assertRaises(gateway.NotificationRejected):
            self.apply(pairs)

        self.assertNothingHappened()

    def test_a_payment_status_nobody_planned_for_is_refused_not_guessed_at(self):
        with self.assertRaises(gateway.NotificationRejected) as raised:
            self.apply(notification(self.subscription, status='SETTLED'))

        self.assertIn('SETTLED', str(raised.exception))
        self.assertNothingHappened()

    def test_a_notification_payfast_denies_sending_is_refused(self):
        with patch.object(gateway, 'confirm_with_payfast', return_value=False):
            with self.assertRaises(gateway.NotificationRejected):
                services.apply_notification(
                    notification(self.subscription),
                    source_ip=PAYFAST_IP,
                    addresses={PAYFAST_IP},
                )

        self.assertNothingHappened()

    def test_a_notification_payfast_could_not_be_asked_about_is_held_not_refused(self):
        """Distinct from a denial: nothing is known to be wrong, so it is worth
        a retry and the endpoint asks for one."""
        with patch.object(gateway, 'confirm_with_payfast', return_value=None):
            with self.assertRaises(services.NotificationUnconfirmed):
                services.apply_notification(
                    notification(self.subscription),
                    source_ip=PAYFAST_IP,
                    addresses={PAYFAST_IP},
                )

        self.assertNothingHappened()

    def test_a_confirmed_notification_is_applied(self):
        """The other half, so the two tests above are not both passing because
        confirmation is broken outright."""
        with patch.object(gateway, 'confirm_with_payfast', return_value=True):
            services.apply_notification(
                notification(self.subscription),
                source_ip=PAYFAST_IP,
                addresses={PAYFAST_IP},
            )

        subscription, member = self.reload()
        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(member.status, UserStatus.ACTIVE)


class CancellationTests(ApplyMixin, PaymentsTestCase):
    def setUp(self):
        super().setUp()
        self.apply(notification(self.subscription, payment_id='PF-1'))
        self.subscription.refresh_from_db()
        self.paid_until = self.subscription.paid_until

    def test_it_ends_the_mandate(self):
        self.apply(notification(self.subscription, status='CANCELLED'))
        subscription, _ = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        self.assertIsNotNone(subscription.cancelled_at)

    def test_it_does_not_switch_the_member_off(self):
        """They keep the time they paid for. Taking it back is both wrong and,
        under the Consumer Protection Act, not ours to take."""
        self.apply(notification(self.subscription, status='CANCELLED'))
        _, member = self.reload()

        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_it_leaves_the_paid_up_date_alone(self):
        self.apply(notification(self.subscription, status='CANCELLED'))
        subscription, _ = self.reload()

        self.assertEqual(subscription.paid_until, self.paid_until)

    def test_it_writes_no_payment_row(self):
        """A cancellation moves no money."""
        self.apply(notification(self.subscription, status='CANCELLED'))

        self.assertEqual(Payment.objects.count(), 1)

    def test_cancelling_twice_is_harmless(self):
        self.apply(notification(self.subscription, status='CANCELLED'))
        subscription, _ = self.reload()
        first = subscription.cancelled_at

        self.apply(notification(self.subscription, status='CANCELLED'))
        subscription, _ = self.reload()

        self.assertEqual(subscription.cancelled_at, first)


class FailedChargeTests(ApplyMixin, PaymentsTestCase):
    def test_it_is_recorded(self):
        self.apply(notification(self.subscription, status='FAILED', payment_id='PF-F'))

        self.assertEqual(Payment.objects.get().status, PaymentStatus.FAILED)

    def test_it_buys_nothing(self):
        self.apply(notification(self.subscription, status='FAILED'))

        self.assertIsNone(Payment.objects.get().covers_until)

    def test_it_does_not_switch_the_member_off(self):
        """Payfast retries a failed charge on its own schedule. Cutting a member
        off on the first failure cuts them off over a card about to be replaced."""
        self.apply(notification(self.subscription, payment_id='PF-1'))
        self.apply(notification(self.subscription, status='FAILED', payment_id='PF-F'))
        _, member = self.reload()

        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_a_failure_does_not_activate_anything(self):
        self.apply(notification(self.subscription, status='FAILED'))
        subscription, member = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.PENDING)
        self.assertEqual(member.status, UserStatus.PENDING_PAYMENT)

    def test_a_failure_with_no_payment_id_is_dropped_rather_than_invented(self):
        pairs = [
            (k, v)
            for k, v in notification(self.subscription, status='FAILED')
            if k not in ('pf_payment_id', 'signature')
        ]
        pairs.append(
            ('signature', gateway.notification_signature(pairs, PAYFAST.passphrase))
        )

        applied = self.apply(pairs)

        self.assertIsNone(applied.payment)
        self.assertEqual(Payment.objects.count(), 0)


class LapseTests(ApplyMixin, PaymentsTestCase):
    def setUp(self):
        super().setUp()
        self.apply(notification(self.subscription, payment_id='PF-1'))
        self.subscription.refresh_from_db()

    def overdue_by(self, days):
        self.subscription.paid_until = gateway.billing_date() - timedelta(days=days)
        self.subscription.save(update_fields=['paid_until'])

    def test_a_paid_up_membership_does_not_lapse(self):
        self.assertEqual(services.lapse_overdue(), 0)

        _, member = self.reload()
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_a_membership_that_stopped_paying_lapses(self):
        self.overdue_by(1)

        self.assertEqual(services.lapse_overdue(), 1)

        subscription, member = self.reload()
        self.assertEqual(subscription.status, SubscriptionStatus.LAPSED)
        self.assertIsNotNone(subscription.lapsed_at)

    def test_lapsing_suspends_rather_than_erases(self):
        """Reversible: paying again undoes it, and nothing personal is touched."""
        self.overdue_by(1)
        services.lapse_overdue()
        _, member = self.reload()

        self.assertEqual(member.status, UserStatus.SUSPENDED)
        self.assertFalse(member.is_active)
        self.assertIsNone(member.deleted_at)
        self.assertTrue(member.first_name)

    def test_a_membership_paid_up_to_today_does_not_lapse(self):
        """The boundary. Off by one here withdraws access on the last day
        somebody paid for."""
        self.overdue_by(0)

        self.assertEqual(services.lapse_overdue(), 0)

    def test_a_cancelled_but_still_paid_up_membership_does_not_lapse_yet(self):
        self.apply(notification(self.subscription, status='CANCELLED'))

        self.assertEqual(services.lapse_overdue(), 0)

        _, member = self.reload()
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_lapsing_is_idempotent(self):
        self.overdue_by(1)
        services.lapse_overdue()

        self.assertEqual(services.lapse_overdue(), 0)

    def test_it_does_not_overwrite_a_suspension_staff_applied(self):
        """A member suspended for conduct is already not Active, so nothing here
        touches them -- and the reason for their suspension is not quietly
        replaced with 'did not pay'."""
        self.member.refresh_from_db()
        self.member.deactivate()
        self.overdue_by(1)

        services.lapse_overdue()
        _, member = self.reload()

        self.assertEqual(member.status, UserStatus.SUSPENDED)


class OutstandingLinkTests(PaymentsTestCase):
    """The fallback for a duplicate registration: email, never the response."""

    def send(self):
        with self.captureOnCommitCallbacks(execute=True):
            return services.email_outstanding_checkout(self.member)

    def test_a_member_awaiting_payment_is_emailed_their_link(self):
        mail.outbox.clear()

        self.assertTrue(self.send())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.subscription.checkout_token, mail.outbox[0].body)

    def test_the_link_uses_the_configured_checkout_address(self):
        mail.outbox.clear()
        self.send()

        self.assertIn(PAYFAST.checkout_url, mail.outbox[0].body)

    def test_it_says_what_is_owed(self):
        mail.outbox.clear()
        self.send()

        self.assertIn('150.00', mail.outbox[0].body)

    def test_the_email_never_carries_the_identity_number(self):
        from app.membership.tests.support import ADULT_ID

        mail.outbox.clear()
        self.send()

        self.assertNotIn(ADULT_ID, mail.outbox[0].body)

    def test_it_pushes_the_expiry_out(self):
        self.subscription.checkout_expires_at = timezone.now() - timedelta(days=2)
        self.subscription.save(update_fields=['checkout_expires_at'])

        self.send()
        self.subscription.refresh_from_db()

        self.assertTrue(self.subscription.checkout_is_usable())

    def test_it_keeps_the_token_the_member_may_already_be_holding(self):
        before = self.subscription.checkout_token

        self.send()
        self.subscription.refresh_from_db()

        self.assertEqual(self.subscription.checkout_token, before)

    def test_a_paid_member_is_emailed_nothing(self):
        """Nothing is owed, so telling a mailbox about a payment would be a lie."""
        self.subscription.status = SubscriptionStatus.ACTIVE
        self.subscription.gateway_token = 'x'
        self.subscription.paid_until = gateway.billing_date()
        self.subscription.save()
        mail.outbox.clear()

        self.assertFalse(self.send())
        self.assertEqual(mail.outbox, [])

    def test_an_unknown_address_resolves_to_nobody(self):
        self.assertIsNone(services.outstanding_for_email('nobody@example.com'))

    def test_a_registered_address_resolves_to_the_member(self):
        found = services.outstanding_for_email(self.member.email)

        self.assertEqual(found.pk, self.member.pk)

    def test_an_erased_account_resolves_to_nobody(self):
        """Its address is gone and it can never be reactivated, so there is
        nothing to email and nowhere to email it."""
        self.member.soft_delete()

        self.assertIsNone(services.outstanding_for_email('thandiwe@example.com'))

"""Tests for the two rows, and mostly for what the database refuses.

The constraints here are asserted in SQL rather than in Python, so these tests
write through ``.update()`` and ``bulk_create`` where they can -- a rule enforced
only in ``save()`` is not a rule a data migration, a repair script or a raw
``UPDATE`` is protected by, which is the same reasoning behind the check
constraint holding ``status`` and ``is_active`` together on ``User``.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from app.payments import gateway
from app.payments.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    new_checkout_token,
)

from .support import PaymentsTestCase


class CheckoutTokenTests(PaymentsTestCase):
    def test_two_tokens_are_never_the_same(self):
        self.assertNotEqual(new_checkout_token(), new_checkout_token())

    def test_a_token_is_long_enough_to_be_unguessable(self):
        """It is a bearer credential in an emailed URL. 32 bytes is 43
        URL-safe characters; this is sized to resist guessing, not to be typed."""
        self.assertGreaterEqual(len(new_checkout_token()), 43)

    def test_a_token_is_url_safe(self):
        """It goes in a path segment. A '/' or a '+' there would break the link
        rather than fail a lookup, which is harder to diagnose."""
        import re

        self.assertRegex(new_checkout_token(), r'^[A-Za-z0-9_-]+$')

    def test_a_duplicate_token_is_refused_by_the_database(self):
        """A collision would let one member pay for another's subscription."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.objects.create(
                    user=self.member,
                    status=SubscriptionStatus.CANCELLED,
                    amount=Decimal('150.00'),
                    frequency=gateway.FREQUENCIES['monthly'],
                    checkout_token=self.subscription.checkout_token,
                    checkout_expires_at=timezone.now(),
                )


class LiveSubscriptionConstraintTests(PaymentsTestCase):
    def other(self, status):
        return Subscription(
            user=self.member,
            status=status,
            amount=Decimal('150.00'),
            frequency=gateway.FREQUENCIES['monthly'],
            checkout_token=new_checkout_token(),
            checkout_expires_at=timezone.now() + timedelta(days=1),
            gateway_token='t' if status == SubscriptionStatus.ACTIVE else '',
            paid_until=(
                gateway.billing_date()
                if status == SubscriptionStatus.ACTIVE
                else None
            ),
        )

    def test_a_second_pending_subscription_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.other(SubscriptionStatus.PENDING).save()

    def test_a_second_active_subscription_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.other(SubscriptionStatus.ACTIVE).save()

    def test_a_cancelled_one_alongside_a_pending_one_is_allowed(self):
        """The constraint is on *live* subscriptions only, so a member who
        cancelled and rejoined has a history rather than a conflict."""
        self.other(SubscriptionStatus.CANCELLED).save()

        self.assertEqual(Subscription.objects.filter(user=self.member).count(), 2)

    def test_a_lapsed_one_alongside_a_pending_one_is_allowed(self):
        self.other(SubscriptionStatus.LAPSED).save()

        self.assertEqual(Subscription.objects.filter(user=self.member).count(), 2)

    def test_the_constraint_holds_against_a_raw_update(self):
        """Reviving a cancelled subscription while one is already live is
        exactly the repair somebody would attempt by hand."""
        cancelled = self.other(SubscriptionStatus.CANCELLED)
        cancelled.save()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.objects.filter(pk=cancelled.pk).update(
                    status=SubscriptionStatus.PENDING
                )


class PaidUpConstraintTests(PaymentsTestCase):
    """An active subscription has a mandate and a paid-up date. In SQL, because
    ``lapse_overdue`` trusts ``paid_until`` and a null there would silently
    exempt an account from ever lapsing."""

    def test_active_without_a_paid_up_date_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.objects.filter(pk=self.subscription.pk).update(
                    status=SubscriptionStatus.ACTIVE, gateway_token='t'
                )

    def test_active_without_a_mandate_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.objects.filter(pk=self.subscription.pk).update(
                    status=SubscriptionStatus.ACTIVE,
                    paid_until=gateway.billing_date(),
                )

    def test_active_with_both_is_allowed(self):
        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=SubscriptionStatus.ACTIVE,
            gateway_token='t',
            paid_until=gateway.billing_date(),
        )
        self.subscription.refresh_from_db()

        self.assertEqual(self.subscription.status, SubscriptionStatus.ACTIVE)

    def test_pending_needs_neither(self):
        """The status every registration starts in. Requiring either would make
        opening a subscription impossible."""
        self.assertEqual(self.subscription.status, SubscriptionStatus.PENDING)
        self.assertIsNone(self.subscription.paid_until)
        self.assertEqual(self.subscription.gateway_token, '')


class CheckoutUsabilityTests(PaymentsTestCase):
    def test_a_pending_unexpired_checkout_is_usable(self):
        self.assertTrue(self.subscription.checkout_is_usable())

    def test_an_expired_one_is_not(self):
        self.subscription.checkout_expires_at = timezone.now() - timedelta(seconds=1)

        self.assertFalse(self.subscription.checkout_is_usable())

    def test_a_paid_subscription_has_no_checkout_whatever_the_expiry_says(self):
        """Otherwise a link found in an inbox sends a paid-up member back to
        Payfast to start a second mandate."""
        self.subscription.status = SubscriptionStatus.ACTIVE
        self.subscription.checkout_expires_at = timezone.now() + timedelta(days=365)

        self.assertFalse(self.subscription.checkout_is_usable())

    def test_extending_moves_the_expiry_and_not_the_token(self):
        before = self.subscription.checkout_token

        self.subscription.extend_checkout(3600)

        self.assertEqual(self.subscription.checkout_token, before)
        self.assertGreater(self.subscription.checkout_expires_at, timezone.now())


class PaymentTests(PaymentsTestCase):
    def payment(self, **overrides):
        defaults = {
            'subscription': self.subscription,
            'gateway_payment_id': 'PF-1',
            'status': PaymentStatus.COMPLETE,
            'amount_gross': Decimal('150.00'),
        }
        return Payment.objects.create(**{**defaults, **overrides})

    def test_a_duplicate_gateway_payment_id_is_refused(self):
        """The idempotency of the whole notification endpoint rests on this."""
        self.payment()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.payment()

    def test_a_subscription_with_payments_cannot_be_deleted(self):
        """PROTECT: deleting it does not unmake the payment, it only makes the
        next reconciliation unexplainable."""
        from django.db.models import ProtectedError

        self.payment()

        with self.assertRaises(ProtectedError):
            self.subscription.delete()

    def test_the_cycle_length_comes_from_the_frequency(self):
        self.assertEqual(self.subscription.cycle_days, gateway.CYCLE_DAYS[3])

    def test_an_annual_subscription_covers_a_year(self):
        self.subscription.frequency = gateway.FREQUENCIES['annual']

        self.assertEqual(self.subscription.cycle_days, 366)


class QuerySetTests(PaymentsTestCase):
    def test_live_finds_a_pending_subscription(self):
        self.assertIn(self.subscription, Subscription.objects.live())

    def test_live_excludes_a_cancelled_one(self):
        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=SubscriptionStatus.CANCELLED
        )

        self.assertEqual(Subscription.objects.live().count(), 0)

    def test_overdue_excludes_a_subscription_with_no_paid_up_date(self):
        """A null there is a row written by something that bypassed this app, and
        lapsing a membership is not the way to report that."""
        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=SubscriptionStatus.PENDING, paid_until=None
        )

        self.assertEqual(
            Subscription.objects.overdue(gateway.billing_date()).count(), 0
        )

    def test_overdue_finds_an_active_subscription_past_its_date(self):
        Subscription.objects.filter(pk=self.subscription.pk).update(
            status=SubscriptionStatus.ACTIVE,
            gateway_token='t',
            paid_until=gateway.billing_date() - timedelta(days=1),
        )

        self.assertEqual(
            Subscription.objects.overdue(gateway.billing_date()).count(), 1
        )

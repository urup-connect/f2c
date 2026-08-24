"""Tests for the two management commands.

``lapse_memberships`` is the only thing that ever withdraws access for
non-payment, so its ``--dry-run`` is tested as carefully as its real run: a
dry-run that quietly changed something would be the worst possible bug in it.

``payfast_notify`` exists because Payfast cannot reach a localhost notify URL,
which makes the step that activates a membership the one step a developer never
sees. Two things are asserted about it. That it works -- and, more importantly,
that **it refuses to run in production**, because a command that can activate a
membership from a shell has no business existing there.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from app.accounts.models import UserStatus
from app.payments import gateway
from app.payments.models import Payment, PaymentStatus, SubscriptionStatus

from .support import MONTHLY_DAYS, PAYFAST_IP, PaymentsTestCase, notification


class LapseCommandTests(PaymentsTestCase):
    def setUp(self):
        super().setUp()
        # Paid, then let the paid-up period run out.
        from app.payments import services

        services.apply_notification(
            notification(self.subscription, payment_id='PF-1'),
            source_ip=PAYFAST_IP,
            addresses={PAYFAST_IP},
            confirm=False,
        )
        self.subscription.refresh_from_db()

    def overdue_by(self, days):
        self.subscription.paid_until = gateway.billing_date() - timedelta(days=days)
        self.subscription.save(update_fields=['paid_until'])

    def run_command(self, *args):
        out = StringIO()
        call_command('lapse_memberships', *args, stdout=out)
        return out.getvalue()

    def test_it_lapses_an_overdue_membership(self):
        self.overdue_by(1)

        output = self.run_command()
        subscription, member = self.reload()

        self.assertIn('1 membership(s) lapsed', output)
        self.assertEqual(subscription.status, SubscriptionStatus.LAPSED)
        self.assertEqual(member.status, UserStatus.SUSPENDED)

    def test_it_leaves_a_paid_up_membership_alone(self):
        output = self.run_command()
        _, member = self.reload()

        self.assertIn('0 membership(s) lapsed', output)
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_a_dry_run_reports_what_would_lapse(self):
        self.overdue_by(5)

        output = self.run_command('--dry-run')

        self.assertIn(str(self.member.pk), output)
        self.assertIn('would lapse', output)

    def test_a_dry_run_changes_nothing(self):
        """The assertion the whole flag exists for."""
        self.overdue_by(5)

        self.run_command('--dry-run')
        subscription, member = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(member.status, UserStatus.ACTIVE)

    def test_running_it_twice_lapses_nothing_the_second_time(self):
        self.overdue_by(1)
        self.run_command()

        self.assertIn('0 membership(s) lapsed', self.run_command())


class NotifyCommandTests(PaymentsTestCase):
    def run_command(self, *args, **kwargs):
        out = StringIO()
        call_command('payfast_notify', *args, stdout=out, **kwargs)
        return out.getvalue()

    @override_settings(DEBUG=True)
    def test_it_activates_a_member_by_email(self):
        self.run_command('--email', self.member.email)
        subscription, member = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(member.status, UserStatus.ACTIVE)

    @override_settings(DEBUG=True)
    def test_it_activates_a_member_by_subscription_id(self):
        self.run_command('--subscription', str(self.subscription.pk))
        subscription, _ = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.ACTIVE)

    @override_settings(DEBUG=True)
    def test_it_pays_the_membership_up_one_cycle(self):
        self.run_command('--email', self.member.email)
        subscription, _ = self.reload()

        self.assertEqual(
            subscription.paid_until,
            gateway.billing_date() + timedelta(days=MONTHLY_DAYS),
        )

    @override_settings(DEBUG=True)
    def test_it_signs_the_payload_for_real(self):
        """Not a shortcut past the verification.

        Asserted by recomputing the signature over the payload the command
        handed to the service, independently of how the command produced it. A
        test that patched ``notification_signature`` would prove nothing:
        signing and verifying go through the same function, so a broken one
        would agree with itself.
        """
        from app.payments import services

        seen = {}
        real = services.apply_notification

        def spy(pairs, **kwargs):
            seen['pairs'] = list(pairs)
            return real(pairs, **kwargs)

        with patch.object(services, 'apply_notification', side_effect=spy):
            self.run_command('--email', self.member.email)

        pairs = seen['pairs']
        signature = dict(pairs)['signature']
        body = [(key, value) for key, value in pairs if key != 'signature']

        self.assertEqual(
            signature,
            gateway.notification_signature(body, services.config().passphrase),
        )

    @override_settings(DEBUG=True)
    def test_the_payload_it_builds_is_ordered_not_a_dict(self):
        """Payfast signs in arrival order, so a command that built a mapping
        would exercise a code path the wire never takes."""
        from app.payments import services

        seen = {}
        real = services.apply_notification

        def spy(pairs, **kwargs):
            seen['pairs'] = list(pairs)
            return real(pairs, **kwargs)

        with patch.object(services, 'apply_notification', side_effect=spy):
            self.run_command('--email', self.member.email)

        self.assertEqual(seen['pairs'][0][0], 'm_payment_id')
        self.assertEqual(seen['pairs'][-1][0], 'signature')

    @override_settings(DEBUG=True)
    def test_it_can_simulate_a_cancellation(self):
        self.run_command('--email', self.member.email)
        self.run_command('--email', self.member.email, '--status', 'CANCELLED')
        subscription, member = self.reload()

        self.assertEqual(subscription.status, SubscriptionStatus.CANCELLED)
        self.assertEqual(member.status, UserStatus.ACTIVE)

    @override_settings(DEBUG=True)
    def test_it_can_simulate_a_failed_charge(self):
        self.run_command('--email', self.member.email, '--status', 'FAILED')

        self.assertEqual(Payment.objects.get().status, PaymentStatus.FAILED)
        self.assertStillPendingPayment()

    @override_settings(DEBUG=True)
    def test_a_wrong_amount_is_refused_the_same_way_a_real_one_would_be(self):
        with self.assertRaises(gateway.NotificationRejected):
            self.run_command('--email', self.member.email, '--amount', '1.00')

        self.assertStillPendingPayment()

    @override_settings(DEBUG=True)
    def test_running_it_twice_reports_a_duplicate(self):
        self.run_command('--email', self.member.email)

        self.assertIn('Already recorded', self.run_command('--email', self.member.email))

    @override_settings(DEBUG=True)
    def test_an_unknown_address_is_a_named_error(self):
        with self.assertRaises(CommandError):
            self.run_command('--email', 'nobody@example.com')

    @override_settings(DEBUG=False)
    def test_it_refuses_to_run_with_debug_off(self):
        """A command that can activate a membership from a shell has no business
        existing in production. The honest route there is "Activate selected
        accounts" in the member admin, which records an account change and
        claims no payment."""
        with self.assertRaises(CommandError) as raised:
            self.run_command('--email', self.member.email)

        self.assertIn('DJANGO_DEBUG', str(raised.exception))
        self.assertStillPendingPayment()

    @override_settings(DEBUG=True)
    def test_it_needs_a_target(self):
        with self.assertRaises(CommandError):
            self.run_command()

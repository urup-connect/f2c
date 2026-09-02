"""The nightly job that withdraws access for non-payment.

**This is the task that closes Block 0 P2.** Before it existed, nothing on this
platform ever ran ``lapse_overdue``: Payfast sends no notification for a
cancelled mandate or a card that stopped working, so an unpaid membership kept
its access indefinitely and no log line anywhere said so.

What is asserted here is the wiring, not the lapsing. Whether the right
subscriptions are found and what happens to each of them is
``test_services``'s job and is tested there against every status; repeating it
would only mean two places to update when the rule changes. What this file
proves is that the schedule reaches that service, and that the run is recorded
in a form somebody can read months later -- which is the whole reason a member
who says "I had paid" can be answered at all.

The tasks run inline here. ``f2c/test_runner.py`` pins eager execution for the
suite, so nothing below needs a broker or a worker.
"""
from datetime import timedelta

from app.club.membership.models import MembershipStatus
from app.core.payments import gateway
from app.core.payments.models import SubscriptionStatus
from app.core.payments.tasks import lapse_memberships
from app.core.scheduling.models import Outcome, ScheduledRun, ScheduledTask

from .support import PAYFAST_IP, PaymentsTestCase, notification


class LapseTaskTests(PaymentsTestCase):
    def setUp(self):
        super().setUp()
        # Paid, then let the paid-up period run out.
        from app.core.payments import services

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

    def test_it_lapses_an_overdue_membership(self):
        self.overdue_by(1)

        self.assertEqual(1, lapse_memberships())

        subscription, member = self.reload()
        self.assertEqual(SubscriptionStatus.LAPSED, subscription.status)
        self.assertEqual(MembershipStatus.LAPSED, member.club_membership.status)

    def test_it_leaves_a_paid_up_membership_alone(self):
        self.assertEqual(0, lapse_memberships())

        subscription, _ = self.reload()
        self.assertEqual(SubscriptionStatus.ACTIVE, subscription.status)

    def test_the_run_is_recorded(self):
        """The answer to "when was this member switched off, and by what?"."""
        self.overdue_by(1)

        lapse_memberships()

        run = ScheduledRun.objects.get()
        self.assertEqual(ScheduledTask.LAPSE_MEMBERSHIPS, run.task)
        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(1, run.affected)

    def test_a_night_with_nothing_overdue_is_still_recorded(self):
        """A job that ran and found nothing is not the same as a job that did
        not run, and the difference is only visible if the quiet night leaves a
        row too. Without this, "no row for last night" would be ambiguous
        between healthy and broken."""
        lapse_memberships()

        run = ScheduledRun.objects.get()
        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(0, run.affected)

    def test_running_it_twice_lapses_nothing_the_second_time(self):
        """Idempotent, which is what makes ``CELERY_TASK_ACKS_LATE`` safe: a
        worker killed mid-run has its task redelivered, and the repeat has to
        cost nothing."""
        self.overdue_by(1)
        lapse_memberships()

        self.assertEqual(0, lapse_memberships())
        self.assertEqual(2, ScheduledRun.objects.count())

    def test_it_does_not_deactivate_the_account(self):
        """C27, asserted at the task because the task is what a deployment
        actually runs. A club subscription that stopped paying must not lock a
        member out of the produce market, and must not lock them out of the one
        screen that fixes it."""
        self.overdue_by(1)

        lapse_memberships()

        _, member = self.reload()
        self.assertTrue(member.is_active)

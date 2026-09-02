"""The nightly job that enforces the send-record retention window.

**A retention policy nobody runs is a retention policy nobody has**, and until
this task existed nothing ran this one: ``EMAIL_DISPATCH_RETENTION_DAYS`` was a
number in a settings file and ``EmailDispatch`` grew a member's correspondence
history without limit.

What is asserted here is the wiring and the record, not the window arithmetic --
that belongs to ``retention``, is shared with the campaign-touch purge, and is
tested through the command in ``test_dispatch``. What this adds is that the
schedule reaches it and that the run leaves the evidence POPIA's documentation
duty wants: a row saying how many records were deleted, on which night.

Tasks run inline here; ``f2c/test_runner.py`` pins eager execution.
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from app.core.scheduling.models import Outcome, ScheduledRun, ScheduledTask
from app.core.storefronts.models import EmailDispatch, Storefront
from app.core.storefronts.tasks import purge_email_dispatch_records
from f2c.testing import make_account


class PurgeEmailDispatchTaskTests(TestCase):
    def setUp(self):
        self.member = make_account('member@example.com')

    def make(self, *, age_days):
        dispatch = EmailDispatch.objects.create(
            kind=EmailDispatch.Kind.LOGIN_CODE,
            storefront=Storefront.CLUB,
            recipient=self.member,
            subject='Subject',
            trigger=EmailDispatch.Trigger.MEMBER,
            send_status=EmailDispatch.SendStatus.SENT,
            sent_at=timezone.now(),
        )
        # `queued_at` is `auto_now_add`, so ageing a row means going round the
        # model -- the same trick, for the same reason, as the command tests.
        EmailDispatch.objects.filter(pk=dispatch.pk).update(
            queued_at=timezone.now() - timedelta(days=age_days)
        )
        return dispatch

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_it_deletes_past_the_window_and_keeps_inside_it(self):
        old = self.make(age_days=400)
        recent = self.make(age_days=30)

        self.assertEqual(1, purge_email_dispatch_records())

        surviving = set(EmailDispatch.objects.values_list('pk', flat=True))
        self.assertEqual({recent.pk}, surviving)
        self.assertNotIn(old.pk, surviving)

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_the_run_is_recorded(self):
        """The evidence that a declared retention period is an enforced one."""
        self.make(age_days=400)

        purge_email_dispatch_records()

        run = ScheduledRun.objects.get()
        self.assertEqual(ScheduledTask.PURGE_EMAIL_DISPATCHES, run.task)
        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(1, run.affected)

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=0)
    def test_zero_keeps_everything_and_the_row_says_why(self):
        """Two different zeros, told apart in the admin.

        Nothing expired, and retention is switched off, are both ``affected =
        0``. A deployment that has decided to keep the lot should be able to see
        that its schedule ran and deliberately did nothing -- so the run says so
        in ``detail``, which is the one place in this project that column is
        used for something other than a failure.
        """
        self.make(age_days=4000)

        purge_email_dispatch_records()

        run = ScheduledRun.objects.get()
        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(0, run.affected)
        self.assertIn('Nothing was deleted', run.detail)
        self.assertEqual(1, EmailDispatch.objects.count())

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_the_task_takes_no_window_of_its_own(self):
        """``--days`` is on the command, where a person is deciding something.

        A nightly job that could be scheduled with a different window than the
        deployment configured is a second place for the retention period to
        live, and the two would eventually disagree about how long a member's
        correspondence is kept.
        """
        with self.assertRaises(TypeError):
            purge_email_dispatch_records(days=7)

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_running_it_twice_deletes_nothing_the_second_time(self):
        """Idempotent, which is what makes ``CELERY_TASK_ACKS_LATE`` safe."""
        self.make(age_days=400)
        purge_email_dispatch_records()

        self.assertEqual(0, purge_email_dispatch_records())

"""The run history is readable and nothing can rewrite it.

**The tests worth naming are the three permission ones.** This page is the
evidence that a retention window is enforced and that a member's access was
withdrawn on a particular night by a particular run. A page that could edit or
delete those rows is a page that can make the evidence say whatever is
convenient, and it would be a superuser away from doing so -- Django grants
every model permission to a superuser, so read-only here has to be a property of
the admin class rather than of who is signed in. That is what these assert, with
a superuser, deliberately.

``took`` is tested because it is a ``@admin.display`` method with three branches
and one of them only ever runs for a row nothing writes on purpose: a run that
died. ``manage.py check`` cannot see inside it, and a method that raises on the
value it did not expect is a 500 on the one page somebody opens when something
has already gone wrong.
"""
from datetime import timedelta

from django.contrib.admin.sites import site
from django.test import TestCase
from django.urls import reverse

from app.core.scheduling.models import Outcome, ScheduledRun, ScheduledTask
from app.core.scheduling.runs import record
from f2c.testing import make_account


class ScheduledRunAdminTests(TestCase):
    def setUp(self):
        self.operator = make_account(
            'operator@example.com', is_staff=True, is_superuser=True
        )
        self.client.force_login(self.operator)
        self.admin = site._registry[ScheduledRun]

    def request(self):
        return self.client.get(reverse('admin:scheduling_scheduledrun_changelist')).wsgi_request

    def test_nobody_may_add_a_run(self):
        """A run is something that happened; it is not data to enter."""
        self.assertFalse(self.admin.has_add_permission(self.request()))

    def test_nobody_may_change_a_run(self):
        self.assertFalse(self.admin.has_change_permission(self.request()))

    def test_nobody_may_delete_a_run(self):
        """Nothing here is personal information, so nothing can be erased --
        which is why this is stricter than the campaign-touch admin, where a
        POPIA erasure request is sometimes answered by hand."""
        self.assertFalse(self.admin.has_delete_permission(self.request()))

    def test_the_changelist_renders(self):
        with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
            run.affected = 4

        response = self.client.get(
            reverse('admin:scheduling_scheduledrun_changelist')
        )

        self.assertEqual(200, response.status_code)
        self.assertContains(response, 'Lapse memberships')

    def test_a_run_page_renders_read_only(self):
        with record(ScheduledTask.PURGE_EMAIL_DISPATCHES):
            pass

        run = ScheduledRun.objects.get()
        response = self.client.get(
            reverse('admin:scheduling_scheduledrun_change', args=(run.pk,))
        )

        self.assertEqual(200, response.status_code)
        # No save row on a page that cannot save.
        self.assertNotContains(response, 'name="_save"')

    def test_took_reads_in_seconds_for_a_quick_run(self):
        run = ScheduledRun.objects.create(task=ScheduledTask.LAPSE_MEMBERSHIPS)
        run.finished_at = run.started_at + timedelta(seconds=3)

        self.assertEqual('3.0s', self.admin.took(run))

    def test_took_reads_in_minutes_for_a_long_run(self):
        """A nightly purge on a year of send records is minutes, not seconds,
        and a four-digit second count is a number nobody reads at a glance."""
        run = ScheduledRun.objects.create(task=ScheduledTask.PURGE_EMAIL_DISPATCHES)
        run.finished_at = run.started_at + timedelta(minutes=7, seconds=30)

        self.assertEqual('7.5m', self.admin.took(run))

    def test_took_names_a_run_that_never_came_back(self):
        """The branch that only ever runs for a row nothing writes on purpose.

        This is the failure mode the worker's own logs will not have shouted
        about, so the page has to say it in words rather than showing an empty
        cell that reads like a rendering fault.
        """
        run = ScheduledRun.objects.create(task=ScheduledTask.LAPSE_MEMBERSHIPS)

        self.assertIn('still running', self.admin.took(run))

    def test_took_is_blank_for_a_failure_with_no_finish_time(self):
        """A row can be FAILED with no ``finished_at`` only if something wrote
        it by hand -- the recorder always stamps both. It renders anyway."""
        run = ScheduledRun.objects.create(
            task=ScheduledTask.LAPSE_MEMBERSHIPS, outcome=Outcome.FAILED
        )

        self.assertEqual('—', self.admin.took(run))

    def test_the_string_form_names_the_job_and_the_outcome(self):
        """What the admin log and every dropdown show."""
        with record(ScheduledTask.PURGE_CAMPAIGN_TOUCHES) as run:
            pass

        self.assertEqual(
            'Purge campaign touches past their retention window — succeeded',
            str(run),
        )

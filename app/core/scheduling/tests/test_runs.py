"""What ``record`` writes, on both paths.

**The test worth naming is ``test_a_failure_is_recorded_and_re_raised``.** The
record is a side effect and never a substitute: if the exception stopped here,
the job would report itself broken in a table nobody is watching and healthy to
Celery, which is the only system that would otherwise notice. A run that failed
has to be both -- a row saying so, and an exception on its way up.

The second is ``test_the_row_exists_before_the_work_does``. A record written on
completion is a record that misses the case an audit trail exists for: a worker
killed mid-flight, or a database that went away. That run leaves a row still
marked ``RUNNING`` with no finish time, and nothing else anywhere says it
happened at all.
"""
from django.test import TestCase

from app.core.scheduling.models import DETAIL_LENGTH, Outcome, ScheduledRun, ScheduledTask
from app.core.scheduling.runs import record


class RecordTests(TestCase):
    def assertLogsTheFailure(self):
        """Capture the traceback ``record`` logs, and assert there is one.

        Two jobs in one, which is why every failure test below is wrapped in
        it. It keeps a deliberate exception from printing four thousand
        characters into a passing test run, and it asserts the thing the
        ``ScheduledRun`` row deliberately does not carry: the traceback. The row
        holds one line for an operator; the log holds the frames for a
        developer, and a failure that reached neither would be a failure nobody
        can diagnose.
        """
        return self.assertLogs('app.core.scheduling.runs', level='ERROR')

    def test_a_successful_run_is_recorded(self):
        with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
            run.affected = 3

        run.refresh_from_db()

        self.assertEqual(ScheduledTask.LAPSE_MEMBERSHIPS, run.task)
        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(3, run.affected)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual('', run.detail)

    def test_a_body_that_counts_nothing_means_zero(self):
        """A job that ran and found nothing to do. Legitimate and common -- a
        night on which no membership was overdue -- and not the same as a run
        that failed before it counted."""
        with record(ScheduledTask.PURGE_EMAIL_DISPATCHES) as run:
            pass

        run.refresh_from_db()

        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(0, run.affected)

    def test_the_row_exists_before_the_work_does(self):
        """See the module docstring. This is what makes a killed run visible."""
        with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
            inflight = ScheduledRun.objects.get(pk=run.pk)

            self.assertEqual(Outcome.RUNNING, inflight.outcome)
            self.assertIsNone(inflight.finished_at)

    def test_a_failure_is_recorded_and_re_raised(self):
        """The one that matters. See the module docstring."""
        with self.assertLogsTheFailure() as logs:
            with self.assertRaises(ZeroDivisionError):
                with record(ScheduledTask.PURGE_CAMPAIGN_TOUCHES):
                    1 / 0

        self.assertIn('ZeroDivisionError', str(logs.output))

        run = ScheduledRun.objects.get()

        self.assertEqual(Outcome.FAILED, run.outcome)
        self.assertIn('ZeroDivisionError', run.detail)
        self.assertIsNotNone(run.finished_at)

    def test_a_failure_keeps_what_the_body_had_already_counted(self):
        """A purge that deleted half its rows and then fell over deleted half
        its rows. Reporting zero would be wrong in the direction that matters --
        it would say nothing was touched when personal information was."""
        with self.assertLogsTheFailure():
            with self.assertRaises(RuntimeError):
                with record(ScheduledTask.PURGE_EMAIL_DISPATCHES) as run:
                    run.affected = 12
                    raise RuntimeError('the connection went away')

        run.refresh_from_db()

        self.assertEqual(12, run.affected)
        self.assertEqual(Outcome.FAILED, run.outcome)

    def test_a_long_failure_is_cut_rather_than_refused(self):
        """The failure column must not itself be able to fail the save. The
        traceback is on the logger; this is the one line a ticket quotes."""
        with self.assertLogsTheFailure():
            with self.assertRaises(ValueError):
                with record(ScheduledTask.LAPSE_MEMBERSHIPS):
                    raise ValueError('x' * (DETAIL_LENGTH * 2))

        run = ScheduledRun.objects.get()

        self.assertEqual(DETAIL_LENGTH, len(run.detail))

    def test_a_body_may_leave_a_note_on_a_successful_run(self):
        """``detail`` is normally the failure column, and the purges use it to
        say that a zero was retention being switched off rather than nothing
        having expired. A save that omitted the field would discard that."""
        with record(ScheduledTask.PURGE_EMAIL_DISPATCHES) as run:
            run.detail = 'Retention is set to 0 days.'

        run.refresh_from_db()

        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual('Retention is set to 0 days.', run.detail)

    def test_each_run_is_its_own_row(self):
        """Nothing is overwritten. The history is the point."""
        for _ in range(3):
            with record(ScheduledTask.LAPSE_MEMBERSHIPS):
                pass

        self.assertEqual(
            3, ScheduledRun.objects.for_task(ScheduledTask.LAPSE_MEMBERSHIPS).count()
        )


class ScheduledRunTests(TestCase):
    def test_duration_is_none_until_the_run_finishes(self):
        run = ScheduledRun.objects.create(task=ScheduledTask.LAPSE_MEMBERSHIPS)

        self.assertIsNone(run.duration)

    def test_duration_is_the_elapsed_time(self):
        with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
            pass

        self.assertIsNotNone(run.duration)
        self.assertGreaterEqual(run.duration.total_seconds(), 0)

    def test_unfinished_finds_the_run_that_never_came_back(self):
        """The query behind "did last night's purge finish?"."""
        died = ScheduledRun.objects.create(task=ScheduledTask.PURGE_EMAIL_DISPATCHES)
        with record(ScheduledTask.LAPSE_MEMBERSHIPS):
            pass

        self.assertEqual(
            [died.pk], list(ScheduledRun.objects.unfinished().values_list('pk', flat=True))
        )

    def test_an_unregistered_task_name_is_stored_rather_than_refused(self):
        """No check constraint, unlike every other known-values column here.

        A fourth job whose author forgot to register it would otherwise fail at
        the moment it wrote its own audit row -- so the retention purge would
        stop working because the record of the purge would not validate. The
        audit trail must never break the job it is auditing.
        """
        with record('something.nobody.registered') as run:
            run.affected = 1

        run.refresh_from_db()

        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual('something.nobody.registered', run.task)

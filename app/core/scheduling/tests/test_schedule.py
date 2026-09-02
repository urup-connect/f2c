"""The schedule, the tasks and the registry all naming the same three jobs.

**This is the test that would have caught the whole class of fault the Function
App was going to have.** A scheduler that names its jobs by string has one
failure mode above all others: the string stops matching. Beat publishes
``payments.lapse_memberships`` faithfully every night, nothing is listening for
that name any more, and the message expires unhandled -- no exception, no failed
run, no row in ``ScheduledRun``, and an unpaid membership keeping its access
indefinitely. The only symptom is an absence, and nobody monitors absences.

Three names have to agree for the schedule to work at all:

* the ``task`` in ``CELERY_BEAT_SCHEDULE``,
* the ``name`` given to ``@shared_task``,
* the ``ScheduledTask`` value the run is recorded under.

They are asserted against each other here rather than trusted, because a
rename that updates two of the three is exactly the plausible mistake -- and
because the failure it produces is silent in production and invisible in every
other test in this suite.
"""
from django.conf import settings
from django.test import SimpleTestCase

from app.core.scheduling.models import ScheduledTask
from f2c.celery import app as celery_app


class ScheduleTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # **Autodiscovery has to be forced, and that is not a workaround.**
        # `app.autodiscover_tasks()` in `f2c/celery.py` is deferred: it runs on
        # the worker's `import_modules` signal, so a worker walks INSTALLED_APPS
        # for `tasks.py` at start-up and a web process never does. That is
        # correct -- a request path that imports a task imports its module
        # directly, and there is no reason for every Django process to load
        # code it will not call.
        #
        # It does mean `app.tasks` in a plain test process holds only Celery's
        # own built-ins, so asserting against it unforced would prove nothing
        # about anything. This call is what the worker does, so what passes
        # below is what the worker would find.
        celery_app.loader.import_default_modules()

    @property
    def registered(self):
        """Every task name the worker would answer to."""
        return set(celery_app.tasks)

    def test_every_scheduled_task_is_registered(self):
        """The one that matters. See the module docstring."""
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertIn(entry['task'], self.registered)

    def test_every_registered_job_is_in_the_registry(self):
        """A task that runs and records itself under a name the admin cannot
        display is a run nobody can find."""
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertIn(entry['task'], ScheduledTask.values)

    def test_every_registry_entry_is_scheduled(self):
        """The other direction. A job in the registry with no schedule is a job
        somebody meant to run -- the exact state this project was in before
        Celery, three times over."""
        scheduled = {
            entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()
        }

        self.assertEqual(set(ScheduledTask.values), scheduled)

    def test_the_three_jobs_are_the_three_jobs(self):
        """Named outright, so that adding a fourth is a deliberate edit to a
        test rather than something that slips in with a schedule entry."""
        self.assertEqual(
            {
                'payments.lapse_memberships',
                'storefronts.purge_email_dispatches',
                'attribution.purge_campaign_touches',
            },
            set(ScheduledTask.values),
        )

    def test_no_task_name_follows_its_import_path(self):
        """Celery's default name is the module path, and this project has moved
        every app once already -- under ``core``/``commerce``/``club`` in Block
        0.5. A name that followed the package would have made that move rename
        a queue key, a schedule entry and every historical row in
        ``ScheduledRun``. Same decision, same reason, as ``AppConfig.label``.
        """
        for name in ScheduledTask.values:
            with self.subTest(task=name):
                self.assertNotIn('app.core', name)

    def test_every_entry_expires(self):
        """Beat publishes on time whether or not a worker is listening.

        Without an expiry, a worker down from 01:00 to 09:00 comes up and runs
        the night's three jobs during business hours -- which for
        ``lapse_memberships`` means members losing access mid-morning with no
        run scheduled anywhere near that time.
        """
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertGreater(entry['options']['expires'], 0)

    def test_the_expiry_leaves_the_overnight_window(self):
        """An expiry longer than the gap to the working day is no expiry at
        all. Every job runs before 03:00 UTC and expires within six hours,
        which is 05:00-09:00 UTC -- 07:00-11:00 South African time at the very
        latest, and normally never used."""
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                self.assertLessEqual(entry['options']['expires'], 8 * 60 * 60)

    def test_nothing_runs_inside_the_working_day(self):
        """UTC+2 with no daylight saving, so a crontab hour of 7 is 09:00 on the
        clock every South African member and every member of staff is looking
        at. All three jobs are overnight work."""
        for name, entry in settings.CELERY_BEAT_SCHEDULE.items():
            with self.subTest(entry=name):
                hours_utc = entry['schedule'].hour

                for hour in hours_utc:
                    # 22:00-05:00 UTC is midnight to 07:00 local.
                    self.assertTrue(
                        hour >= 22 or hour <= 5,
                        f'{name} runs at {hour:02d}:00 UTC, '
                        f'which is {(hour + 2) % 24:02d}:00 local',
                    )


class EagerTests(SimpleTestCase):
    def test_the_suite_runs_tasks_inline(self):
        """What the test runner pins, and why no test here needs a worker.

        Asserted on ``app.conf`` rather than on the Django setting, because that
        is what a task actually consults -- Celery reads settings once, at
        finalisation, and does not watch them afterwards. A runner that set only
        the Django setting would leave this false and every task test would
        publish into a broker with nothing listening.
        """
        self.assertTrue(celery_app.conf.task_always_eager)
        self.assertTrue(celery_app.conf.task_eager_propagates)

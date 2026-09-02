"""Which queue each task goes to, and why getting that wrong is a login outage.

**Nothing else in the suite can catch a routing mistake.** Under eager execution
-- which every test run uses, see ``f2c/test_runner.py`` -- a task runs inline
and no queue is ever consulted. So a task routed to the wrong queue, or to a
queue no worker consumes, passes every functional test in this project and then
fails in production in a way that looks like nothing at all: the API answers
normally, rows accumulate on ``queued``, and no member without a passkey can
sign in.

That is what this module is for. It asserts the configuration rather than any
behaviour, because the configuration is the part that has no other test.

**The arrangement being defended.** One worker runs one task at a time
(``CELERY_WORKER_PREFETCH_MULTIPLIER`` is 1, and both workers run
``--concurrency 1`` or higher but never share a slot across queues). The nightly
purges are long delete passes with a twenty-five-minute ceiling, running at
01:00 and 01:20. If a sign-in code shared their queue, one requested at 01:05
would wait behind the housekeeping. So:

* ``storefronts.deliver_email`` goes to ``mail``, consumed by its own worker.
* everything scheduled goes to ``scheduled``, which is also the default -- so a
  task added without a route lands with the nightly work rather than in front of
  a member's credential. A slow surprise beats a delayed sign-in code.
"""
from django.test import SimpleTestCase
from django.conf import settings

from app.core.scheduling.models import ScheduledTask
from app.core.storefronts.tasks import DELIVER_EMAIL
from f2c.celery import app as celery_app

MAIL_QUEUE = 'mail'
SCHEDULED_QUEUE = 'scheduled'


class RoutingTests(SimpleTestCase):
    def route_for(self, name):
        """The queue Celery would publish ``name`` to.

        Asked of the app rather than read out of ``CELERY_TASK_ROUTES``, because
        what matters is the answer Celery arrives at -- routes, the default
        queue and any per-task option together -- not the dict this project
        happens to write.
        """
        return celery_app.amqp.router.route({}, name).get('queue').name

    def test_email_is_routed_to_the_mail_queue(self):
        """**The one route in the project, and the reason the second worker
        exists.** Without it every email queues behind the nightly purges.
        """
        self.assertEqual(MAIL_QUEUE, self.route_for(DELIVER_EMAIL))

    def test_the_route_key_matches_a_registered_task(self):
        """A route keyed on a name no task uses does not raise -- it silently
        leaves the task on the default queue. So the string in the routes dict
        has to be the string the task registered under, and this is what pins
        the two together."""
        self.assertIn(DELIVER_EMAIL, settings.CELERY_TASK_ROUTES)
        self.assertIn(DELIVER_EMAIL, celery_app.tasks)

    def test_every_scheduled_job_is_routed_to_the_scheduled_queue(self):
        """Including by default. None of the three has a route of its own; they
        rely on ``CELERY_TASK_DEFAULT_QUEUE``, and this is what says so."""
        for task in ScheduledTask:
            with self.subTest(task=task.value):
                self.assertEqual(SCHEDULED_QUEUE, self.route_for(task.value))

    def test_the_default_queue_is_the_scheduled_one(self):
        """**The direction of the safe failure.** An unrouted task added later
        lands with the nightly work, where it is slow, rather than on the mail
        queue, where it would sit in front of somebody's sign-in code.
        """
        self.assertEqual(SCHEDULED_QUEUE, settings.CELERY_TASK_DEFAULT_QUEUE)

    def test_the_beat_schedule_holds_only_scheduled_queue_tasks(self):
        """Beat publishes on a timer; the send task is published by a request.
        A send task appearing in the schedule would mean an email going out on a
        crontab to whoever the row happened to name."""
        scheduled = {
            entry['task'] for entry in settings.CELERY_BEAT_SCHEDULE.values()
        }

        self.assertNotIn(DELIVER_EMAIL, scheduled)
        self.assertEqual(set(ScheduledTask.values), scheduled)


class SendTaskSettingsTests(SimpleTestCase):
    """The per-task overrides on ``deliver_email``, which are not decoration.

    Each one differs from a global default that is correct for the nightly jobs
    and wrong for an email, and the consequence of losing any of them is
    invisible in a diff.
    """

    @property
    def task(self):
        return celery_app.tasks[DELIVER_EMAIL]

    def test_it_acknowledges_on_receipt_rather_than_after_the_work(self):
        """**The most consequential line in the task, and the easiest to lose to
        a tidy-up.**

        ``CELERY_TASK_ACKS_LATE`` is ``True`` globally and justified there by
        every scheduled job being idempotent. Sending an email is not: with
        late acknowledgement, a worker killed mid-hand-over has its message
        redelivered, and the member gets a second sign-in code or a second
        suspension notice. A lost send leaves a row saying ``queued``; a
        duplicate leaves two rows that both look correct.
        """
        self.assertTrue(settings.CELERY_TASK_ACKS_LATE)
        self.assertFalse(self.task.acks_late)

    def test_it_is_bounded_in_seconds_rather_than_in_minutes(self):
        """The global limits were sized for a delete pass over a whole table. A
        hand-over is one SMTP conversation against a ten-second socket timeout,
        and holding the worker slot for twenty minutes over one message would
        stall every send behind it."""
        self.assertLessEqual(self.task.soft_time_limit, 60)
        self.assertLessEqual(self.task.time_limit, 90)
        self.assertLess(self.task.time_limit, settings.CELERY_TASK_TIME_LIMIT)

    def test_the_retry_policy_is_configured_rather_than_hard_coded(self):
        """So a deployment can flatten it and the test runner can switch it off
        -- which it does, for the reason ``f2c/test_runner.py`` gives."""
        self.assertIsInstance(settings.EMAIL_SEND_MAX_RETRIES, int)
        self.assertGreater(settings.EMAIL_SEND_BACKOFF_SECONDS, 0)
        self.assertGreaterEqual(
            settings.EMAIL_SEND_BACKOFF_CEILING_SECONDS,
            settings.EMAIL_SEND_BACKOFF_SECONDS,
        )

    def test_the_whole_retry_window_fits_inside_the_broker_visibility_timeout(self):
        """Otherwise Redis decides a message being retried was never handled and
        redelivers it to a second worker -- which for a non-idempotent task is
        the duplicate send ``acks_late=False`` was set to prevent, arriving by
        another route."""
        base = settings.EMAIL_SEND_BACKOFF_SECONDS
        ceiling = settings.EMAIL_SEND_BACKOFF_CEILING_SECONDS
        window = sum(
            min(base * (2 ** attempt), ceiling)
            for attempt in range(settings.EMAIL_SEND_MAX_RETRIES)
        )

        visibility = settings.CELERY_BROKER_TRANSPORT_OPTIONS[
            'visibility_timeout'
        ]
        self.assertLess(window, visibility)

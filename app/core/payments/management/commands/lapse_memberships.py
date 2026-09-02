"""Withdraw access from memberships that have stopped paying, by hand.

This is the half of the payment lifecycle Payfast does not tell us about. A
cancelled mandate and a card that stopped working both end the same way -- the
paid-up date passes and no money arrives -- and neither sends a notification
saying "this member should now be switched off". So it is computed rather than
driven by an event, and it has to be *run*.

**What runs it is no longer nothing.** This docstring used to say "a daily cron
or an Azure App Service WebJob is the intended home", and ``design/todo.md``
carried a timer-triggered Azure Function App calling a protected endpoint on the
API. Neither exists and neither will: the home is ``app/core/payments/tasks.py``
on Celery beat, inside this application, with the schedule in
``CELERY_BEAT_SCHEDULE`` and a record of every run in
``scheduling.ScheduledRun``. See ``f2c/queue.py`` for why that beat the two
external schedulers.

**This command is now the same job by hand**, which is what it is for: a run
brought forward, a run repeated after a failure, and the ``--dry-run`` that
answers "who would this switch off?" before anybody switches them off. It calls
the same service the task calls, so the two cannot disagree about who is
overdue.

A real run is recorded in ``ScheduledRun`` exactly as the nightly one is, and
deliberately: the table answers "when was this member's access withdrawn, and
by which run", and that question does not care whether a person or a timer
started it. What the table cannot currently say is *which* of the two it was --
noted here rather than fixed, because the column that would carry it is only
worth adding when somebody asks the question.

Nothing here erases anything, and nothing here signs anybody out of the
platform. The membership lapses; the account is untouched; a payment reverses
it.
"""
from django.core.management.base import BaseCommand

from app.core.payments import services
from app.core.scheduling.models import ScheduledTask
from app.core.scheduling.runs import record


class Command(BaseCommand):
    help = 'Suspend members whose subscription is no longer paid up.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would lapse and change nothing.',
        )

    def handle(self, *args, **options):
        from app.core.payments.gateway import billing_date
        from app.core.payments.models import Subscription

        today = billing_date()

        if options['dry_run']:
            overdue = (
                Subscription.objects.overdue(today)
                .select_related('user')
                .order_by('paid_until')
            )
            for subscription in overdue:
                self.stdout.write(
                    f'{subscription.user_id} paid until {subscription.paid_until}'
                )
            self.stdout.write(
                self.style.WARNING(
                    f'{overdue.count()} membership(s) would lapse as at {today}. '
                    'Nothing changed.'
                )
            )
            # No `ScheduledRun` row. A dry run changed nothing, and a table of
            # runs that includes runs that did not happen is a table that has to
            # be filtered before it can be read.
            return

        with record(ScheduledTask.LAPSE_MEMBERSHIPS) as run:
            run.affected = services.lapse_overdue(today=today)

        self.stdout.write(
            self.style.SUCCESS(f'{run.affected} membership(s) lapsed as at {today}.')
        )

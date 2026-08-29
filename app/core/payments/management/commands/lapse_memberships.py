"""Withdraw access from memberships that have stopped paying.

This is the half of the payment lifecycle Payfast does not tell us about. A
cancelled mandate and a card that stopped working both end the same way -- the
paid-up date passes and no money arrives -- and neither sends a notification
saying "this member should now be switched off".

So it is computed rather than driven by an event, and it has to be *run*. Until
something schedules it, an unpaid membership keeps its access indefinitely: see
``design/features/payments.md``, risk table. A daily cron or an Azure App
Service WebJob is the intended home.

Nothing here erases anything. ``deactivate`` blocks sign-in and cuts live
sessions, and a payment reverses it.
"""
from django.core.management.base import BaseCommand

from app.core.payments import services


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
            return

        lapsed = services.lapse_overdue(today=today)
        self.stdout.write(
            self.style.SUCCESS(f'{lapsed} membership(s) lapsed as at {today}.')
        )

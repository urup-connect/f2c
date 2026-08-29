"""Stand in for a Payfast notification, in development only.

Payfast delivers notifications server-to-server, so it has to be able to reach
``notify_url``. It cannot reach ``localhost``, which means the one step that
actually activates a membership is the one step that never happens on a
developer's machine -- the same shape of problem as the console email backend,
and this is the same kind of answer.

It is not a shortcut past the verification. The payload is signed with the
configured passphrase and goes through ``services.apply_notification`` exactly
as a real one does, so a signature bug shows up here rather than in production.
Two checks are stood down and both are about the network rather than the
payload: the source address is asserted to be this machine, and the callback to
Payfast asking "did you send this?" is skipped, because it did not.

Refuses to run with ``DEBUG`` off. A command that can activate a membership from
a shell is a command that has no business existing in production, where the
honest route is *Activate selected accounts* in the member admin -- which
records an account change and claims no payment.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.core.payments import gateway, services
from app.core.payments.models import Subscription

#: The address the fake notification claims to come from. Asserted rather than
#: resolved -- there is no Payfast host at the other end of this.
LOCAL_SOURCE = '127.0.0.1'


class Command(BaseCommand):
    help = 'Simulate a Payfast notification against a subscription (DEBUG only).'

    def add_arguments(self, parser):
        target = parser.add_mutually_exclusive_group(required=True)
        target.add_argument('--email', help='Member whose subscription to pay.')
        target.add_argument('--subscription', help='Subscription id (UUID).')
        parser.add_argument(
            '--status',
            default='COMPLETE',
            choices=sorted(services.PAYMENT_STATUSES),
            help='What Payfast is pretending happened. Default COMPLETE.',
        )
        parser.add_argument(
            '--payment-id',
            help=(
                'The pf_payment_id to use. Defaults to one derived from the '
                'subscription and status, so running the command twice '
                'exercises the duplicate path.'
            ),
        )
        parser.add_argument(
            '--amount',
            help='Override amount_gross, to exercise the mismatch refusal.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'This command only runs with DJANGO_DEBUG=True. In a deployed '
                'environment a membership is activated by a real Payfast '
                'notification, or by "Activate selected accounts" in the '
                'member admin.'
            )

        subscription = self._find(options)
        config = services.config()
        status = options['status']

        amount = Decimal(options['amount']) if options['amount'] else subscription.amount
        payment_id = options['payment_id'] or f'{subscription.pk.hex[:12]}-{status.lower()}'

        # Ordered exactly as Payfast orders a notification, because the
        # signature is computed over the order the fields arrive in. Building
        # this from a dict would test nothing about that.
        pairs = [
            ('m_payment_id', str(subscription.pk)),
            ('pf_payment_id', payment_id),
            ('payment_status', status),
            ('item_name', config.item_name),
            ('amount_gross', f'{amount:.2f}'),
            ('amount_fee', f'{-(amount * Decimal("0.035")).quantize(Decimal("0.01")):.2f}'),
            ('amount_net', f'{(amount * Decimal("0.965")).quantize(Decimal("0.01")):.2f}'),
            ('merchant_id', config.merchant_id),
            ('token', f'sandbox-token-{subscription.pk.hex[:8]}'),
        ]
        pairs.append(
            ('signature', gateway.notification_signature(pairs, config.passphrase))
        )

        applied = services.apply_notification(
            pairs,
            source_ip=LOCAL_SOURCE,
            # Both stood down, and both are about the network rather than the
            # payload. See the module docstring.
            addresses={LOCAL_SOURCE},
            confirm=False,
        )

        subscription.refresh_from_db()
        user = subscription.user
        user.refresh_from_db()

        if applied.duplicate:
            self.stdout.write(
                self.style.WARNING(
                    f'Already recorded: payment {payment_id} was applied before. '
                    'Pass --payment-id to simulate a different one.'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Subscription {subscription.pk} is now {subscription.status}, '
                f'paid until {subscription.paid_until}. '
                f'Account {user.email} is {user.status}.'
            )
        )

    def _find(self, options):
        if options['subscription']:
            subscription = Subscription.objects.filter(
                pk=options['subscription']
            ).first()
            if subscription is None:
                raise CommandError(f'No subscription {options["subscription"]}.')
            return subscription

        subscription = (
            Subscription.objects.filter(user__email=options['email'].strip().lower())
            .order_by('-created_at')
            .first()
        )
        if subscription is None:
            raise CommandError(
                f'No subscription for {options["email"]}. Register the member '
                'first: a subscription is opened in the same transaction.'
            )
        return subscription

"""What a member has agreed to pay, and what they have actually paid.

Two models, and the split between them is the same one ``documents`` makes
between a document and its revisions: ``Subscription`` is the standing
arrangement -- the price, the cycle, the Payfast mandate behind it, and how far
the membership is paid up -- and ``Payment`` is one movement of money against it.

Three decisions are worth recording here.

**The subscription's primary key is what Payfast is told.** It travels as
``m_payment_id`` and comes back on every notification, which is how a
notification is matched to a member. A UUIDv7 is safe to hand over: it names a
row and says nothing about who holds it, which is the property that lets the
checkout carry no personal data at all (see ``gateway.checkout``).

**The checkout link has a token of its own, and it is not the primary key.** The
key goes to Payfast; the token goes in a URL the member follows. Keeping them
separate means the thing in the address bar is not the thing in Payfast's
dashboard, and it can be expired and re-minted without touching the mandate.

**No notification is stored verbatim.** A Payfast notification carries the name,
email address and mobile number the member typed on Payfast's page, and keeping
the raw body would quietly re-import personal data this application went to some
trouble not to send. Only the amounts, the status and the two identifiers are
copied off it. The cost is that a dispute cannot be re-litigated from our own
audit trail -- Payfast's dashboard is the record for that -- and that is the
trade this project makes everywhere else too.
"""
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .gateway import CYCLE_DAYS, FREQUENCIES

#: Bytes of entropy behind a checkout token. 32 bytes is 43 URL-safe
#: characters: this is a bearer credential that appears in an emailed link, so
#: it is sized to be unguessable rather than to be typed.
CHECKOUT_TOKEN_BYTES = 32


def new_checkout_token():
    return secrets.token_urlsafe(CHECKOUT_TOKEN_BYTES)


class SubscriptionStatus(models.TextChoices):
    """Where a membership subscription sits.

    ``PENDING`` is one that has been opened and never paid -- where every
    registration starts. ``ACTIVE`` is one Payfast has taken at least one
    payment against. ``CANCELLED`` is one the member or the club stopped, and
    ``LAPSED`` is one that stopped paying without anyone saying so.

    Cancelled and lapsed are kept apart because they are different facts about
    the member and they justify different treatment: someone who cancelled made
    a decision, and someone whose card expired did not. Collapsing them would
    lose the only signal that distinguishes a member worth contacting from one
    who has already left.
    """

    PENDING = 'pending', 'Awaiting first payment'
    ACTIVE = 'active', 'Active'
    CANCELLED = 'cancelled', 'Cancelled'
    LAPSED = 'lapsed', 'Lapsed (unpaid)'


#: The two statuses that mean "this is the arrangement in force". At most one
#: per member, enforced by a partial unique index below.
LIVE_STATUSES = (SubscriptionStatus.PENDING, SubscriptionStatus.ACTIVE)


class SubscriptionQuerySet(models.QuerySet):

    def live(self):
        """The subscription in force, if there is one. At most one per member."""
        return self.filter(status__in=LIVE_STATUSES)

    def awaiting_payment(self):
        return self.filter(status=SubscriptionStatus.PENDING)

    def overdue(self, today):
        """Active subscriptions whose paid-up period has run out.

        ``paid_until`` null is excluded deliberately: an active subscription
        always has one (a check constraint says so), so a null here would be a
        row written by something that bypassed this app, and lapsing a
        membership is not the way to report that.
        """
        return self.filter(
            status=SubscriptionStatus.ACTIVE,
            paid_until__isnull=False,
            paid_until__lt=today,
        )


class Subscription(models.Model):
    """One member's standing arrangement to pay for their membership.

    The price and the cycle are copied onto the row at the moment it is opened
    rather than read from settings when they are needed. A member who joined at
    R150 a month is on R150 a month; changing the configured price must change
    what *new* members are asked for and nothing about what existing ones
    agreed to. Reading the setting later would silently rewrite every past
    arrangement -- and would make a payment that no longer matches the
    configured amount look like fraud (see ``services.apply_notification``).
    """

    # Handed to Payfast as m_payment_id and returned on every notification. See
    # the module docstring on why it is safe to hand over.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    # CASCADE, unlike most relations to User in this project. A subscription is
    # meaningless without the member it belongs to and holds no history the
    # collective needs -- Payment does, which is why that one is PROTECT.
    # Erasure does not delete the account, so this is reached only by a real
    # deletion, which the admin does not offer.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
    )

    status = models.CharField(
        max_length=16,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.PENDING,
        db_index=True,
    )

    # What was agreed, at the moment it was agreed. See the class docstring.
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    frequency = models.PositiveSmallIntegerField(
        choices=[
            (code, name.title())
            for name, code in sorted(FREQUENCIES.items(), key=lambda item: item[1])
        ],
        help_text='How often Payfast bills this subscription.',
    )
    cycles = models.PositiveSmallIntegerField(
        default=0, help_text='Billing cycles to take, or 0 for until cancelled.'
    )

    # The bearer credential in the checkout URL. Unique so a collision is a
    # database error rather than one member paying for another's membership.
    checkout_token = models.CharField(
        max_length=64, unique=True, default=new_checkout_token, editable=False
    )
    checkout_expires_at = models.DateTimeField()

    # Payfast's own handle on the mandate, returned with the first payment. It
    # is what a cancellation or an amendment would be addressed to, and it is
    # blank until Payfast has actually taken money.
    gateway_token = models.CharField(max_length=64, blank=True, db_index=True)

    # How far the membership is paid up. The one field that decides whether an
    # account keeps its access, and the only input to `services.lapse_overdue`.
    paid_until = models.DateField(null=True, blank=True)

    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    cancelled_at = models.DateTimeField(null=True, blank=True, editable=False)
    lapsed_at = models.DateTimeField(null=True, blank=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        constraints = (
            # At most one arrangement in force per member. Without this, a
            # retried registration or a repaired row could leave two live
            # mandates against one account and Payfast billing twice.
            models.UniqueConstraint(
                fields=('user',),
                condition=models.Q(status__in=[s.value for s in LIVE_STATUSES]),
                name='one_live_subscription_per_member',
            ),
            # An active subscription is one Payfast has taken money against, so
            # it has a token and a paid-up date. Stated in SQL because the
            # lapsing query trusts `paid_until` and a null there would silently
            # exempt an account from ever lapsing.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=SubscriptionStatus.ACTIVE)
                    | models.Q(gateway_token__gt='', paid_until__isnull=False)
                ),
                name='active_subscription_is_paid_up',
            ),
        )

    def __str__(self):
        return f'{self.user_id} {self.get_status_display()} R{self.amount}'

    @property
    def cycle_days(self):
        """How long one paid cycle covers. See ``gateway.CYCLE_DAYS``."""
        return CYCLE_DAYS[self.frequency]

    def checkout_is_usable(self, now=None):
        """Whether the checkout link still resolves.

        Two conditions, and the second is the one worth naming: a subscription
        that is no longer awaiting payment has no checkout, whatever its expiry
        says. Otherwise a link found in an inbox would send a paid-up member
        back to Payfast to start a second mandate.
        """
        now = now or timezone.now()
        return (
            self.status == SubscriptionStatus.PENDING
            and self.checkout_expires_at > now
        )

    def extend_checkout(self, ttl_seconds, now=None):
        """Push the checkout expiry out, without changing the token.

        The token is deliberately kept: the member may be holding the link in an
        email, and re-minting it on every send would invalidate the one they
        already have.
        """
        now = now or timezone.now()
        self.checkout_expires_at = now + timedelta(seconds=ttl_seconds)
        return self


class PaymentStatus(models.TextChoices):
    """What Payfast said happened, mapped from its ``payment_status``.

    Payfast's vocabulary, not ours, so a value it adds later arrives as a
    recognisable gap rather than being coerced into the nearest match.
    """

    COMPLETE = 'complete', 'Complete'
    FAILED = 'failed', 'Failed'
    CANCELLED = 'cancelled', 'Cancelled'


class Payment(models.Model):
    """One movement of money against a subscription, as Payfast reported it.

    One row per Payfast payment id, which is what makes the notification
    endpoint safe to call twice: Payfast retries a notification it did not get a
    2xx for, and a duplicate delivery collides with the unique index rather than
    activating a membership a second time or extending it twice.

    ``covers_until`` is written here as well as on the subscription, and the
    repetition is on purpose. The subscription says where the membership stands
    now; this says what *this payment* bought, which is the question a dispute
    asks and the one a later correction to the subscription would erase.
    """

    subscription = models.ForeignKey(
        Subscription, on_delete=models.PROTECT, related_name='payments'
    )

    # Payfast's pf_payment_id. Unique, and that uniqueness is the idempotency
    # of the whole notification endpoint.
    gateway_payment_id = models.CharField(max_length=64, unique=True)

    status = models.CharField(max_length=16, choices=PaymentStatus.choices)

    # As reported, not as computed. `amount_fee` is negative in Payfast's own
    # numbers and is stored as sent, because a sign flipped on the way in is a
    # reconciliation that never balances and nobody can explain.
    amount_gross = models.DecimalField(max_digits=10, decimal_places=2)
    amount_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    amount_net = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # What this payment bought. Null for anything that did not complete.
    covers_until = models.DateField(null=True, blank=True)

    # Stamped by the database when the notification was accepted. Payfast sends
    # no timestamp of its own, and two clocks for one fact eventually disagree.
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-received_at',)
        indexes = (models.Index(fields=('subscription', '-received_at')),)

    def __str__(self):
        return f'{self.gateway_payment_id} {self.status} R{self.amount_gross}'

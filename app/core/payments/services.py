"""What a payment does to a membership.

Every rule about money lives here. ``gateway`` knows the Payfast protocol and
nothing about members; ``models`` holds the two rows; ``api`` translates
exceptions into status codes. This module is the only place that decides that a
payment activates an account, and it is the only place that writes to one.

Four rules run through it.

**A notification is the only thing that activates a membership.** Not the
member's return from Payfast -- that is a browser redirect, which the member
controls and can replay, bookmark or forge. The ``return_url`` says "thank you"
and reads nothing. The server-to-server notification is the transaction.

**The agreement is on the row, not in the settings.** ``apply_notification``
checks the amount Payfast reports against ``subscription.amount``, which was
copied onto the row when the member agreed to it. Checking it against the
configured price instead would mean that raising the fee turned every existing
member's next renewal into an amount mismatch.

**Applying a notification is idempotent.** Payfast retries anything it did not
get a 2xx for, and the retry carries the same ``pf_payment_id``. A unique index
on that column, plus ``get_or_create``, is what makes a second delivery a no-op
rather than a second cycle of membership granted free.

**A cancellation does not switch anybody off.** It ends the mandate, and the
membership then runs out on the date it was already paid up to --
``lapse_overdue`` is what eventually withdraws access. Cutting access on the
cancellation notification would take back time the member has paid for, which is
both wrong and, under the Consumer Protection Act, not ours to take.
"""
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from app.core.accounts.models import User
from app.core.storefronts.mail import brand_for, send_storefront_email
from app.core.storefronts.models import Storefront
from app.club.membership.models import MembershipStatus

from . import gateway
from .gateway import NotificationRejected
from .models import (
    LIVE_STATUSES,
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)

#: How Payfast's ``payment_status`` maps onto ours. A value not in here is
#: refused rather than guessed at -- see ``apply_notification``.
PAYMENT_STATUSES = {
    'COMPLETE': PaymentStatus.COMPLETE,
    'FAILED': PaymentStatus.FAILED,
    'CANCELLED': PaymentStatus.CANCELLED,
}

#: The membership statuses a payment may lift a member out of. **Only the two
#: that are about money.** ``PENDING_PAYMENT`` is where registration leaves one
#: and ``LAPSED`` is where ``lapse_overdue`` puts one whose subscription stopped
#: paying; paying again undoes both, which is the whole point of them.
#:
#: ``PENDING`` is deliberately absent: that is a membership awaiting
#: *verification* by the club, and money does not settle that question.
#: ``SHARING`` is absent because a placeholder pays for nothing -- C6.
#:
#: **``SUSPENDED`` was here and should not have been.** This tuple's own comment
#: used to justify it by calling ``SUSPENDED`` the club's landing state for a
#: subscription that stopped paying. Nothing in the codebase does that.
#: ``lapse_overdue`` writes ``LAPSED`` and refuses to touch ``SUSPENDED`` --
#: there is a test named for it, *does not overwrite a suspension staff
#: applied* -- and the only writer of ``SUSPENDED`` is
#: ``membership.administration.suspend_member``, a conduct action that mentions
#: money nowhere. So the effect was that **a member suspended for conduct could
#: pay the fee and be restored to Active automatically**, going around
#: ``reinstate_member``, which exists so that lifting a block is a deliberate
#: act by an administrator. Only that function lifts a suspension now.
#:
#: A recurring debit from a suspended member is therefore recorded, warned
#: about and not activated -- see ``_activate`` below. That leaves money held
#: against an account with no access, which is a refund question and belongs to
#: **C11**, not here.
#:
#: **These are membership statuses now, not account statuses.** Before the split
#: a payment activated the account, which is why an unpaid registrant could not
#: sign in. The account is an identity and stays Active throughout; what a
#: payment moves is the membership. C27.
ACTIVATABLE_STATUSES = (
    MembershipStatus.PENDING_PAYMENT,
    MembershipStatus.LAPSED,
)


def config():
    """The Payfast settings, read once at startup. See ``gateway.payfast_config``."""
    return settings.PAYFAST


class CheckoutUnavailable(Exception):
    """The checkout token names nothing a member can pay right now.

    One exception for four situations -- unknown token, expired token, a
    subscription already paid, a subscription cancelled -- because the answer to
    all four is the same screen, and distinguishing them would turn the endpoint
    into a way to probe whether a token was ever real.
    """


class NotificationUnconfirmed(Exception):
    """Payfast could not be asked whether it sent this.

    Separate from :class:`~app.core.payments.gateway.NotificationRejected` because it
    is the one failure worth retrying: nothing is known to be wrong with the
    notification, we simply could not reach Payfast to confirm it. The endpoint
    answers it with a 503 so Payfast delivers again.
    """


@dataclass(frozen=True)
class Applied:
    """What a notification did.

    ``duplicate`` is a success: it means this payment had already been recorded,
    which is exactly what a Payfast retry looks like. The caller answers it with
    the same 200 as a first delivery, because anything else asks Payfast to keep
    trying.
    """

    subscription: Subscription
    payment: Payment | None
    duplicate: bool = False


def open_subscription(user, *, now=None):
    """Open a subscription for ``user`` at ``PENDING``, with a fresh checkout.

    Called from inside the registration transaction, so a member and their
    arrangement to pay are one write: a member with no subscription would sit at
    Pending payment with no way to leave it, and a subscription with no member
    would be a mandate against nobody.

    The price and cycle are copied off the configuration here, once. See
    ``Subscription`` on why they are not read back later.

    :raises IntegrityError: the member already has a live subscription. Left to
        propagate rather than caught: two live mandates against one account is a
        bug in the caller, and the partial unique index is the only thing that
        can rule it out under concurrency.
    """
    now = now or timezone.now()
    plan = config()
    return Subscription.objects.create(
        user=user,
        status=SubscriptionStatus.PENDING,
        amount=plan.amount,
        frequency=plan.frequency,
        cycles=plan.cycles,
        checkout_expires_at=now + timedelta(seconds=plan.checkout_ttl_seconds),
    )


def checkout_for(subscription, *, today=None):
    """The signed Payfast field set for ``subscription``.

    Built fresh on every read rather than stored. A checkout signature is
    computed over the merchant key and the passphrase, so a stored one is a
    stored secret-derived value that would also have to be invalidated whenever
    either changed -- and it is three lines of MD5 to recompute.
    """
    return gateway.checkout(config(), m_payment_id=str(subscription.pk), today=today)


def find_checkout(token, *, now=None):
    """The subscription a checkout token names, if it is still payable.

    :raises CheckoutUnavailable: for an unknown token, an expired one, or a
        subscription that is no longer awaiting payment. One answer for all
        three, deliberately -- see the exception.
    """
    now = now or timezone.now()
    subscription = Subscription.objects.filter(checkout_token=token).first()
    if subscription is None or not subscription.checkout_is_usable(now):
        raise CheckoutUnavailable(
            'This payment link is no longer valid. Ask the club for a new one.'
        )
    return subscription


def _covers_until(subscription, today):
    """The date a completed payment pays the membership up to.

    Measured from whichever is later -- today, or where the membership is
    already paid up to -- so a renewal that arrives early extends the period
    rather than resetting it, and one that arrives after a gap does not
    retrospectively cover the gap.
    """
    start = today
    if subscription.paid_until and subscription.paid_until > today:
        start = subscription.paid_until
    return start + timedelta(days=subscription.cycle_days)


def _activate_membership(user):
    """Open the club to a paid-up member.

    **This used to activate the account.** It now activates the membership, and
    the account is left alone: signing in is a question about an identity and
    using the club is a question about a membership. The visible consequence is
    that an unpaid registrant reaches the payment screen instead of the sign-in
    refusal. C27.

    Four outcomes, and keeping them apart is what makes the log usable.

    A membership at ``PENDING_PAYMENT``, ``SUSPENDED`` or ``LAPSED`` is
    activated. One already ``ACTIVE`` is left alone **quietly** -- that is every
    renewal, which is the majority of notifications this application will ever
    see, and warning about it would bury the one case that matters under a
    monthly flood.

    **No membership at all** is warned about rather than refused. It should not
    happen -- a subscription is created against a member -- and if it does, the
    money arrived for something nobody can be given.

    Anything else is recorded and warned about rather than refused. A payment
    against a membership awaiting verification is a thing that actually
    happened and must still be written down; refusing the notification would
    only make Payfast retry it forever and would lose the money's trail. The
    payment row is the record, and this is how a human finds out.
    """
    membership = getattr(user, 'club_membership', None)

    if membership is None:
        logger.warning(
            'payments: payment recorded against account %s, which holds no '
            'club membership; nothing activated. A human should look at this.',
            user.pk,
        )
        return False

    if membership.status == MembershipStatus.ACTIVE:
        return False

    if membership.status in ACTIVATABLE_STATUSES:
        membership.status = MembershipStatus.ACTIVE
        membership.activated_at = membership.activated_at or timezone.now()
        membership.save(
            update_fields=['status', 'activated_at', 'updated_at']
        )
        return True

    logger.warning(
        'payments: payment recorded against membership %s at status %s; not '
        'activated. A human should look at this.',
        membership.pk,
        membership.status,
    )
    return False


def _record(subscription, posted, status, today):
    """Write the ``Payment`` row for a notification, or report a duplicate.

    ``get_or_create`` on the unique gateway payment id is what makes the
    endpoint idempotent, and the ``IntegrityError`` branch is what makes it
    idempotent under *concurrency* -- Payfast can deliver twice at once, and two
    workers can both find nothing before either writes.
    """
    defaults = {
        'subscription': subscription,
        'status': status,
        'amount_gross': posted.get('amount_gross') or '0.00',
        'amount_fee': posted.get('amount_fee') or None,
        'amount_net': posted.get('amount_net') or None,
        'covers_until': (
            _covers_until(subscription, today)
            if status == PaymentStatus.COMPLETE
            else None
        ),
    }
    try:
        with transaction.atomic():
            payment, created = Payment.objects.get_or_create(
                gateway_payment_id=posted['pf_payment_id'], defaults=defaults
            )
    except IntegrityError:
        return Payment.objects.get(gateway_payment_id=posted['pf_payment_id']), False
    return payment, created


@transaction.atomic
def apply_notification(
    pairs, *, source_ip, addresses=None, opener=None, now=None, confirm=True
):
    """Verify a Payfast notification and apply what it says.

    ``pairs`` is the posted body as an *ordered* sequence of key/value pairs.
    Order matters and cannot be recovered from a dict -- see ``gateway``.

    The four checks run in order of cost, and the network one runs last so a
    forged notification never causes an outbound call. ``confirm=False`` skips
    only that last check and exists for the development command; no request path
    passes it.

    :raises NotificationRejected: the notification is not from Payfast, names no
        subscription, or reports an amount that is not what was agreed. Final --
        there is nothing to retry.
    :raises NotificationUnconfirmed: Payfast could not be reached to confirm it.
        Worth a retry, and the endpoint asks for one.
    :returns: an :class:`Applied`.
    """
    now = now or timezone.now()
    plan = config()

    posted = gateway.verify_notification(
        pairs, plan, source_ip=source_ip, addresses=addresses
    )

    raw_status = (posted.get('payment_status') or '').strip().upper()
    if raw_status not in PAYMENT_STATUSES:
        # Refused rather than mapped to the nearest thing. Payfast adding a
        # status we then guess at is how an account gets activated by an event
        # that did not mean that.
        raise NotificationRejected(f'unknown payment_status {raw_status!r}')
    status = PAYMENT_STATUSES[raw_status]

    # Locked for the rest of the transaction: two deliveries of the same
    # notification, or a renewal arriving while a cancellation is being applied,
    # must not both read the same `paid_until` and both extend it.
    subscription = (
        Subscription.objects.select_for_update()
        .filter(pk=_subscription_id(posted))
        .select_related('user')
        .first()
    )
    if subscription is None:
        raise NotificationRejected('m_payment_id names no subscription')

    if confirm:
        confirmed = gateway.confirm_with_payfast(pairs, plan, opener=opener)
        if confirmed is None:
            raise NotificationUnconfirmed(
                'Payfast could not be reached to confirm this notification.'
            )
        if not confirmed:
            raise NotificationRejected('Payfast did not confirm sending this')

    if status == PaymentStatus.CANCELLED:
        return _apply_cancellation(subscription, posted, now)

    if status == PaymentStatus.FAILED:
        return _apply_failure(subscription, posted)

    return _apply_completion(subscription, posted, now)


def _subscription_id(posted):
    """The subscription a notification names, or ``None`` if it names nothing.

    ``m_payment_id`` is a UUID this application generated, but it arrives from
    outside and an unparseable one is a refusal rather than a crash.
    """
    import uuid

    try:
        return uuid.UUID(str(posted.get('m_payment_id', '')).strip())
    except (ValueError, AttributeError, TypeError):
        return None


def _apply_completion(subscription, posted, now):
    """Money arrived: record it, extend the paid-up period, let them sign in."""
    if not gateway.amount_matches(posted.get('amount_gross'), subscription.amount):
        # Checked against the row, not the setting. See the module docstring.
        raise NotificationRejected(
            'amount_gross does not match the agreed subscription amount'
        )

    today = gateway.billing_date()
    payment, created = _record(subscription, posted, PaymentStatus.COMPLETE, today)
    if not created:
        # A Payfast retry. Nothing to do, and saying so is what stops the caller
        # extending the membership a second time.
        return Applied(subscription=subscription, payment=payment, duplicate=True)

    subscription.status = SubscriptionStatus.ACTIVE
    subscription.paid_until = payment.covers_until
    subscription.gateway_token = (posted.get('token') or '').strip()
    if subscription.activated_at is None:
        subscription.activated_at = now
    # Once paid, the checkout is spent: a link still in an inbox must not start
    # a second mandate. `checkout_is_usable` refuses on status alone, and this
    # makes the same fact true of the expiry.
    subscription.checkout_expires_at = now
    subscription.save(
        update_fields=[
            'status',
            'paid_until',
            'gateway_token',
            'activated_at',
            'checkout_expires_at',
            'updated_at',
        ]
    )

    _activate_membership(subscription.user)
    return Applied(subscription=subscription, payment=payment)


def _apply_cancellation(subscription, posted, now):
    """The mandate ended. The membership runs to what it is paid up to.

    No ``Payment`` row: a cancellation moves no money, and Payfast does not
    always send a payment id with one. The subscription is the record.
    """
    if subscription.status != SubscriptionStatus.CANCELLED:
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = now
        subscription.save(update_fields=['status', 'cancelled_at', 'updated_at'])

    return Applied(subscription=subscription, payment=None)


def _apply_failure(subscription, posted):
    """A charge did not go through. Recorded, and nothing else.

    Payfast retries a failed recurring charge on its own schedule, so switching
    the account off on the first failure would cut a member off over an expired
    card that is about to be replaced. ``lapse_overdue`` is what eventually
    acts, and it acts on the paid-up date rather than on a failure count.

    A failure with no payment id is logged and dropped: there is nothing to key
    a row on, and inventing one would break the idempotency the unique index
    provides.
    """
    if not (posted.get('pf_payment_id') or '').strip():
        logger.warning(
            'payments: failed charge on subscription %s with no pf_payment_id; '
            'not recorded.',
            subscription.pk,
        )
        return Applied(subscription=subscription, payment=None)

    payment, created = _record(
        subscription, posted, PaymentStatus.FAILED, gateway.billing_date()
    )
    return Applied(
        subscription=subscription, payment=payment, duplicate=not created
    )


def lapse_overdue(*, today=None):
    """Withdraw access from members whose subscription stopped paying.

    This is the half of the lifecycle Payfast cannot tell us about. A cancelled
    mandate and a failed card both end the same way -- the paid-up date passes
    and no money arrives -- and neither sends a notification saying "this member
    should now be switched off". So it is computed from ``paid_until`` rather
    than driven by an event.

    ``deactivate`` rather than anything harsher: it blocks sign-in and cuts live
    sessions, erases nothing, and paying again reverses it. Nothing here touches
    an account that is not currently Active, so a suspension applied by staff
    for some other reason is not quietly overwritten with this one.

    :returns: how many memberships lapsed.
    """
    today = today or gateway.billing_date()
    lapsed = 0

    for subscription in (
        Subscription.objects.overdue(today)
        .select_related('user', 'user__club_membership')
        .iterator()
    ):
        with transaction.atomic():
            subscription.status = SubscriptionStatus.LAPSED
            subscription.lapsed_at = timezone.now()
            subscription.save(update_fields=['status', 'lapsed_at', 'updated_at'])

            # The membership lapses; the account is untouched. Before the split
            # this called `user.deactivate()` and signed the member out of the
            # platform entirely. That is now wrong twice over: it would lock a
            # produce-market customer out of the market because their club
            # subscription stopped paying, and it would deny the member the one
            # screen that fixes it. They stay signed in and every club
            # destination sends them to the payment screen. C27.
            membership = getattr(subscription.user, 'club_membership', None)
            if membership is not None and membership.status == MembershipStatus.ACTIVE:
                membership.status = MembershipStatus.LAPSED
                membership.save(update_fields=['status', 'updated_at'])
            lapsed += 1

    return lapsed


def _send_checkout_link(email, name, url, amount):
    """Blocking send. Called through a thread by :func:`email_outstanding_checkout`.

    Always the club's server, named outright rather than resolved from a request.
    The membership subscription is the club's alone -- the produce market has no
    membership to bill -- so the host this happens to have been triggered from
    says nothing about which storefront the money is for.
    """
    brand = brand_for(Storefront.CLUB)
    body = render_to_string(
        'emails/payment_link.txt',
        {'name': name, 'url': url, 'amount': f'{amount:.2f}', 'brand': brand},
    )
    send_storefront_email(
        storefront=Storefront.CLUB,
        subject=f'Complete your {brand} membership payment',
        body=body,
        to=[email],
    )


def email_outstanding_checkout(user, *, now=None):
    """Email ``user`` their payment link, if they have one outstanding.

    The fallback path for a registration that could not be redirected -- a
    duplicate submission, which is answered without disclosing that it was one.
    The link only ever reaches the mailbox, so the neutral confirmation screen
    stays neutral: whoever submitted the form learns nothing, and the member
    whose address it is gets a way to finish paying.

    The expiry is pushed out rather than the token re-minted, so a link the
    member is already holding keeps working.

    :returns: ``True`` if an email was sent.
    """
    now = now or timezone.now()
    subscription = (
        Subscription.objects.awaiting_payment().filter(user=user).first()
    )
    if subscription is None:
        # Nothing outstanding: already paid, cancelled, or never opened. Sending
        # anything here would be telling a mailbox about a payment that is not
        # owed.
        return False

    plan = config()
    subscription.extend_checkout(plan.checkout_ttl_seconds, now)
    subscription.save(update_fields=['checkout_expires_at', 'updated_at'])

    email = user.email
    name = user.get_short_name() or 'there'
    url = f'{plan.checkout_url}/{subscription.checkout_token}'
    amount = subscription.amount

    # On commit, not now. This is called from inside the registration
    # transaction, and a link emailed against an expiry that then rolled back is
    # a link that does not work -- worse than no email, because the member has
    # been told to use it.
    transaction.on_commit(
        lambda: _send_checkout_link(email, name, url, amount)
    )
    return True


def outstanding_for_email(email):
    """The live account for ``email``, for the duplicate-registration fallback.

    Matched on the address alone and on live accounts only. Deliberately *not*
    on the identity number or the mobile: a registration that duplicates one of
    those while naming a different address must not send mail about somebody
    else's membership to the address that was typed.
    """
    return User.objects.filter(email=email, deleted_at__isnull=True).first()


def live_subscription(user):
    """The arrangement in force for ``user``, or ``None``. At most one exists."""
    return (
        Subscription.objects.filter(user=user, status__in=LIVE_STATUSES)
        .order_by('-created_at')
        .first()
    )

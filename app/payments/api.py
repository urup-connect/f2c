"""The two endpoints payment needs: one the member reads, one Payfast posts to.

``GET /api/payments/checkout/{token}`` hands back the signed Payfast fields for a
subscription awaiting payment. Unauthenticated, because the whole point of
``Pending payment`` is that the member cannot sign in yet.

``POST /api/payments/payfast/notify`` is the transaction. It is the only thing
that activates a membership -- not the member's return from Payfast, which is a
browser redirect and therefore theirs to replay or forge.

Nothing here decides anything. Every rule is in ``services`` and ``gateway``, so
each endpoint is a translation of exceptions into status codes, and the status
codes are chosen for **what Payfast does with them**:

* **200** -- applied, or already applied. Stops the retries. A duplicate answers
  200 because asking Payfast to redeliver something already recorded gains
  nothing.
* **400** -- rejected, finally. The notification did not prove it came from
  Payfast, named no subscription, or reported an amount nobody agreed to. No
  redelivery will fix any of those.
* **503** -- we could not reach Payfast to confirm it. Nothing is known to be
  wrong; a retry is exactly what should happen.

The refusal body never says which check failed. That reason goes to the log,
where the attacker cannot read which one to fix next.
"""
import logging
from urllib.parse import parse_qsl

from ninja import Router

from . import gateway, services
from .schemas import CheckoutOut, CheckoutUnavailableOut, NotificationOut
from .throttles import CheckoutThrottle

logger = logging.getLogger(__name__)

router = Router(tags=['payments'])


@router.get(
    '/checkout/{token}',
    response={200: CheckoutOut, 404: CheckoutUnavailableOut},
    auth=None,
    throttle=[CheckoutThrottle()],
)
def checkout(request, token: str):
    """The signed Payfast fields for a subscription awaiting payment.

    * **200** -- POST ``fields`` to ``url``, unchanged. The signature covers
      exactly that set, so reordering, re-casing or dropping one makes Payfast
      refuse the checkout.
    * **404** -- the token names nothing payable: unknown, expired, or a
      subscription that is already paid or cancelled. One answer for all of
      them, on purpose -- see ``CheckoutUnavailableOut``.
    * **429** -- the per-IP limit from ``CheckoutThrottle``.

    A GET, and it writes nothing: re-reading it is how a member who abandoned
    the Payfast page gets back. What makes that safe is that the response is the
    same every time and names nobody.
    """
    try:
        subscription = services.find_checkout(token)
    except services.CheckoutUnavailable as unavailable:
        return 404, {'detail': str(unavailable)}

    return 200, services.checkout_for(subscription)


@router.post(
    '/payfast/notify',
    response={200: NotificationOut, 400: NotificationOut, 503: NotificationOut},
    auth=None,
)
def payfast_notify(request):
    """Apply a Payfast notification. The only thing that activates a membership.

    The body is read with ``parse_qsl`` off the raw request rather than through
    ``request.POST``, and that is not fussiness: Payfast signs its notification
    over the fields **in the order they were sent**, and a ``QueryDict`` has
    already collapsed duplicates and is not guaranteed to preserve that order.
    Verifying a re-serialised body is how a signature check passes in
    development and fails in production.

    Unauthenticated and CSRF-free by necessity -- Payfast has no session and no
    token to present. What stands in for both is the four-check verification in
    ``gateway`` and ``services``: source address, merchant, signature, and a
    call back to Payfast asking whether it sent this.

    Not throttled. See ``throttles`` for why.
    """
    pairs = parse_qsl(
        request.body.decode('utf-8', 'replace'), keep_blank_values=True
    )
    source_ip = gateway.notification_source_ip(
        request.META, behind_proxy=services.config().behind_proxy
    )

    try:
        applied = services.apply_notification(pairs, source_ip=source_ip)
    except gateway.NotificationRejected as rejected:
        # Logged with the reason, answered without it. The address is logged
        # because a rejected notification is either an attempt or a
        # misconfiguration, and both need to be traceable to a source.
        logger.warning(
            'payments: notification from %s rejected: %s', source_ip, rejected.reason
        )
        return 400, {'detail': 'This notification was not accepted.'}
    except services.NotificationUnconfirmed as unconfirmed:
        logger.error('payments: notification from %s: %s', source_ip, unconfirmed)
        return 503, {'detail': 'Could not confirm this notification. Retry.'}

    if applied.duplicate:
        # Already recorded. A 200 stops Payfast redelivering something that has
        # been dealt with; anything else asks it to try forever.
        logger.info(
            'payments: duplicate notification for payment %s on subscription %s',
            applied.payment.gateway_payment_id if applied.payment else '-',
            applied.subscription.pk,
        )
        return 200, {'detail': 'Already recorded.'}

    logger.info(
        'payments: subscription %s now %s',
        applied.subscription.pk,
        applied.subscription.status,
    )
    return 200, {'detail': 'Recorded.'}

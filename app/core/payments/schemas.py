"""The checkout contract, and the two answers the notification endpoint gives.

Written out by hand rather than generated from the model, for the same reason
``membership.schemas`` is: a model change must not be able to alter the contract
the frontend depends on.

One decision dominates this file. **The checkout payload contains nothing about
the member.** No name, no address, no mobile number, no account id -- and not
even the amount as a separate field, only inside the signed Payfast fields it is
about to POST. It is reached with a bearer token in a URL, and a URL is shared,
logged and cached; a payload that named the member would make that token a way to
read personal data rather than a way to pay. Payfast asks for the buyer's details
on its own page, which is where the card is typed anyway.

The consequence to know about: ``fields`` is opaque to the frontend. It renders
every pair as a hidden input and POSTs them to ``url``, and it must not reorder,
re-case or omit any of them -- the signature is computed over exactly that set.
"""
from ninja import Schema


class CheckoutOut(Schema):
    """Where to send the member, and what to send with them.

    ``url`` is Payfast's payment engine -- sandbox or live, decided by
    configuration rather than by the caller. ``fields`` is the signed field set,
    including ``signature`` itself.

    A dict rather than a typed object on purpose. Payfast adds fields, and a
    schema that named each one would have to be edited in lockstep with the
    gateway module to let a new one through; here, whatever ``gateway.checkout``
    signs is what the browser posts.
    """

    url: str
    fields: dict[str, str]


class CheckoutUnavailableOut(Schema):
    """A checkout token that names nothing payable.

    One shape for an unknown token, an expired one and an already-paid
    subscription alike. There is deliberately no code to tell them apart: the
    remedy is the same, and distinguishing them would turn the endpoint into a
    way to probe whether a token was ever real.
    """

    detail: str


class NotificationOut(Schema):
    """What Payfast is told. It reads none of it, and that is the point.

    Payfast cares about the status code only -- a 2xx stops the retries. The
    body exists for whoever is reading the exchange in a log or a test, and it
    carries no member, no amount and no account status, because a notification
    endpoint's response is the one part of this flow an attacker gets to see.
    """

    detail: str

"""The rate limit on reading a checkout, and why the notification endpoint has
none.

``GET /api/payments/checkout/{token}`` is unauthenticated -- there is no session
until a membership is paid for -- so a per-IP limit is what bounds guessing at
tokens. It is not the control that matters: 32 bytes of entropy is, and the
limit exists so that an attempt to brute-force one shows up as throttling rather
than as load.

**``POST /api/payments/payfast/notify`` is deliberately not throttled.** Two
reasons. It already refuses every caller that is not one of Payfast's four
notification hosts, which is a tighter bound than any rate could be. And a rate
limit there would drop *real* notifications on the one day it matters -- the
first of the month, when every monthly subscription renews at once and Payfast
delivers them in a burst from a handful of addresses. A dropped notification is a
member who paid and cannot sign in.
"""
from ninja.throttling import AnonRateThrottle


class CheckoutThrottle(AnonRateThrottle):
    scope = 'checkout'

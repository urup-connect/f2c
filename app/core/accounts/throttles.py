"""Per-account rate limits for the profile endpoints.

``UserRateThrottle`` rather than the ``AnonRateThrottle`` the sign-in endpoints
use, and the difference is the point: everything in ``authn.throttles`` guards an
endpoint with no session, so IP is the only key available -- and IP is a key a
determined caller rotates. These endpoints require a session, so the limit can be
keyed on the account, which is the thing actually being protected.

The rates live in ``NINJA_DEFAULT_THROTTLE_RATES``, read by scope name.
"""
from ninja.throttling import AnonRateThrottle, UserRateThrottle


class AvatarUploadThrottle(UserRateThrottle):
    """Bounds the one expensive thing a member can ask for.

    Every upload decodes and re-encodes an image of up to 8MB in a worker
    process. Without this, one account can occupy the pool.
    """

    scope = 'avatar_upload'


class ProfileWriteThrottle(UserRateThrottle):
    scope = 'profile_write'


class CustomerRegisterThrottle(AnonRateThrottle):
    """The limit on ``POST /api/customers/register``.

    The exception to this module's own rule, and the reason is in the first
    paragraph above: an account does not exist yet, so there is no account to
    key on and IP is all there is. It is the same position
    ``membership.throttles.RegisterThrottle`` is in, and the same control doing
    the same job -- **it stands in for the CSRF check an unauthenticated,
    server-to-server endpoint cannot have.** The call arrives from a Next.js
    server action with no session cookie and no token to check; a token this
    application issued to itself would protect nothing.

    What it bounds is bulk creation of accounts and, since a registration emails
    a sign-in code, bulk mail to addresses somebody typed. A scope of its own
    rather than sharing ``register`` with the club: one storefront is a club
    somebody joins once and the other is a shop, and a shared bucket would mean
    tuning the store's limit changes the club's.
    """

    scope = 'customer_register'

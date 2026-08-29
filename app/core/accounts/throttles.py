"""Per-account rate limits for the profile endpoints.

``UserRateThrottle`` rather than the ``AnonRateThrottle`` the sign-in endpoints
use, and the difference is the point: everything in ``authn.throttles`` guards an
endpoint with no session, so IP is the only key available -- and IP is a key a
determined caller rotates. These endpoints require a session, so the limit can be
keyed on the account, which is the thing actually being protected.

The rates live in ``NINJA_DEFAULT_THROTTLE_RATES``, read by scope name.
"""
from ninja.throttling import UserRateThrottle


class AvatarUploadThrottle(UserRateThrottle):
    """Bounds the one expensive thing a member can ask for.

    Every upload decodes and re-encodes an image of up to 8MB in a worker
    process. Without this, one account can occupy the pool.
    """

    scope = 'avatar_upload'


class ProfileWriteThrottle(UserRateThrottle):
    scope = 'profile_write'

"""Per-IP rate limits for the unauthenticated authentication endpoints.

django-ninja's ``AnonRateThrottle`` reads its rate from the scope name in
``NINJA_DEFAULT_THROTTLE_RATES``. Each endpoint gets its own scope so a burst
of failed code entries cannot exhaust the budget for sending new ones.

These are a blunt instrument on their own -- they key on IP, which a determined
attacker rotates. The per-code attempt counter on ``EmailOtp`` is what actually
bounds guessing against a single account.
"""
from ninja.throttling import AnonRateThrottle


class AuthStartThrottle(AnonRateThrottle):
    scope = 'auth_start'


class OtpStartThrottle(AnonRateThrottle):
    """Bounds outbound email. Without it the endpoint is a mailbomb relay."""

    scope = 'otp_start'


class OtpVerifyThrottle(AnonRateThrottle):
    scope = 'otp_verify'


class PasskeyVerifyThrottle(AnonRateThrottle):
    scope = 'passkey_verify'

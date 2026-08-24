"""One-time passcodes emailed to a member as the fallback for passkeys.

This is the only route into a new account -- a user with no passkey yet has to
sign in some other way before they can enrol one -- so it is treated as a
first-class credential, not a back door. Three things keep a six-digit code
honest: it is hashed at rest, it dies after ``OTP_TTL_SECONDS``, and it is
burned after ``OTP_MAX_ATTEMPTS`` wrong guesses.

Django 6.1 has no async email API and password hashing is deliberately slow, so
both run in a worker thread rather than blocking the event loop.
"""
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOtp

_hash = sync_to_async(make_password, thread_sensitive=False)
_check = sync_to_async(check_password, thread_sensitive=False)


def _send_code(email, name, code):
    """Blocking send. Called through a thread by :func:`issue`."""
    body = render_to_string(
        'emails/login_code.txt',
        {
            'name': name,
            'code': code,
            'minutes': max(1, settings.OTP_TTL_SECONDS // 60),
        },
    )
    EmailMessage(
        subject='Your Cultivators Collective sign-in code',
        body=body,
        to=[email],
    ).send()


_send = sync_to_async(_send_code, thread_sensitive=False)


async def issue(user, purpose=EmailOtp.Purpose.LOGIN):
    """Invalidate any outstanding code for the user, then email a fresh one.

    Superseding the previous code means only ever one live code per user, so
    requesting a new one cannot widen the guessing surface.
    """
    now = timezone.now()
    await EmailOtp.objects.filter(
        user=user, purpose=purpose, consumed_at__isnull=True
    ).aupdate(consumed_at=now)

    code = EmailOtp.generate_code()
    await EmailOtp.objects.acreate(
        user=user,
        purpose=purpose,
        code_hash=await _hash(code),
        expires_at=EmailOtp.default_expiry(),
    )

    name = user.get_short_name() or user.get_username()
    await _send(user.email, name, code)


async def verify(user, code, purpose=EmailOtp.Purpose.LOGIN):
    """Check a submitted code, consuming it on success.

    Returns ``True`` only for the current, unexpired, unused code. Every
    attempt -- right or wrong -- increments the counter, so the code is spent
    after ``OTP_MAX_ATTEMPTS`` regardless of how the guesses are spread out.
    """
    otp = await EmailOtp.objects.filter(user=user, purpose=purpose).usable().afirst()
    if otp is None:
        return False

    otp.attempts += 1
    if not await _check(code, otp.code_hash):
        await otp.asave(update_fields=['attempts'])
        return False

    otp.consumed_at = timezone.now()
    await otp.asave(update_fields=['attempts', 'consumed_at'])
    return True

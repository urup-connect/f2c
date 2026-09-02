"""One-time passcodes emailed to a member as the fallback for passkeys.

This is the only route into a new account -- a user with no passkey yet has to
sign in some other way before they can enrol one -- so it is treated as a
first-class credential, not a back door. Three things keep a six-digit code
honest: it is hashed at rest, it dies after ``OTP_TTL_SECONDS``, and it is
burned after ``OTP_MAX_ATTEMPTS`` wrong guesses.

Password hashing is deliberately slow and does not run on the event loop; it
goes to a worker thread from here. **The mail server is no longer on this path
at all** -- ``storefronts.mail`` records the message and a Celery worker hands
it over, so what used to be a ten-second SMTP timeout inside a sign-in request
is now one ``INSERT`` and a publish to Redis. That mattered more here than
anywhere else on the platform: this is the only route into an account that has
no passkey yet, so a mail provider having a bad afternoon was an authentication
outage.

**And it closed a small leak on the way.** A refused hand-over used to raise out
of ``issue`` and out of ``otp/start`` as a 500, while an address with no account
got a clean 200 -- so the failure of a mail server was, briefly, a way to ask
whether an address belonged to a member. Both answers are now 200, which is what
that endpoint always meant to say.

Every code sent is recorded, in ``storefronts.EmailDispatch``. A code that
cannot be delivered is the one authentication failure a member cannot diagnose
and cannot work around, so "was it sent, and did the server take it?" has to be
answerable without a mail provider's console -- and it is the only place that
answers it now, since the request no longer waits to find out.
"""
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.template.loader import render_to_string
from django.utils import timezone

from app.core.storefronts.mail import (
    EmailDispatch,
    asend_storefront_email,
    brand_for,
)

from .models import EmailOtp

_hash = sync_to_async(make_password, thread_sensitive=False)
_check = sync_to_async(check_password, thread_sensitive=False)


async def _send(user, name, code, storefront):
    """Render the code and send it. Awaited by :func:`issue`.

    The storefront decides the server, the sender and the name on the message --
    all three together, in ``storefronts.mail``. A code that arrives from the
    store's provider signed with the club's name is indistinguishable from a
    phishing attempt, which is the one thing a member must be able to tell about
    a one-time code.

    **This awaits a record, not a send.** ``asend_storefront_email`` writes the
    ``EmailDispatch`` row and publishes one task; a Celery worker holds the SMTP
    conversation. So this returns as soon as the code is durably recorded, and
    it does **not** report whether a mail server took the message -- ``mail``
    sets out why that trade is the right way round on this path in particular.
    Rendering stays here because a cached template is a string interpolation,
    not I/O.

    The code reaches the worker through the ``EmailDispatch`` row rather than
    through the task payload, which is deliberate: a task argument sits in Redis
    in cleartext, and hashing the code at rest in ``EmailOtp`` would count for
    very little if a plaintext copy were queued alongside it.

    ``trigger`` is ``MEMBER`` with nobody named, and both halves of that are the
    truth rather than a shortcut. Somebody asked for this code -- it is not a
    send the platform decided on -- and whoever asked was by definition not
    signed in, so the platform has the address they typed and no proof of who
    typed it. Naming the recipient as the trigger would record a claim the
    endpoint deliberately never verifies.
    """
    brand = brand_for(storefront)
    body = render_to_string(
        'emails/login_code.txt',
        {
            'name': name,
            'code': code,
            'brand': brand,
            'minutes': max(1, settings.OTP_TTL_SECONDS // 60),
        },
    )
    await asend_storefront_email(
        storefront=storefront,
        kind=EmailDispatch.Kind.LOGIN_CODE,
        recipient=user,
        subject=f'Your {brand} sign-in code',
        body=body,
        trigger=EmailDispatch.Trigger.MEMBER,
    )


async def issue(user, purpose=EmailOtp.Purpose.LOGIN, *, storefront=None):
    """Invalidate any outstanding code for the user, then email a fresh one.

    Superseding the previous code means only ever one live code per user, so
    requesting a new one cannot widen the guessing surface.

    **Returns before the email leaves.** The send is queued -- see ``_send`` --
    so a caller that gets no exception knows the code exists and is recorded,
    not that it has been accepted by a mail server. ``EmailDispatch`` is where
    the second question is answered.

    ``storefront`` is which shopfront the member is signing in to, and it comes
    from the host the request arrived on -- not from what the member belongs to.
    A code has to be sendable to an address with no account at all, so there is
    nothing else to ask, and a member of both storefronts signing in at the store
    should be answered by the store. Omitted, it falls back to
    ``DEFAULT_STOREFRONT``, which is what a shell or a test gets.
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
    await _send(user, name, code, storefront)


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

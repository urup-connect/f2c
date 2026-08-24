"""Session-cookie authentication endpoints.

The frontend never handles a token. Django issues an HttpOnly ``sessionid``
cookie on login; every subsequent request carries it. Unsafe methods must also
carry the CSRF token, which the frontend gets from ``GET /api/auth/csrf``.

Endpoints that run before a session exists set ``auth=None``, which also skips
django-ninja's built-in CSRF check, so they call ``check_csrf`` themselves.
Login is a state-changing request and must not be forgeable.

Members sign in with a passkey, falling back to a code emailed to them when
they have not enrolled one or ask for a code instead. The password endpoint
below is kept for staff, who also need it for Django admin.

Every route in here reaches an account through ``User.objects.active_by_email``
or through ``is_active``, so only an account with status Active can ever get a
session -- Pending, Suspended and erased accounts are all refused identically,
and the refusal never says which.

This module owns every write to the credential tables. The two services it
calls -- ``authn.otp`` and ``authn.webauthn`` -- deliberately do not persist
anything themselves, so there is one place to look for what touches them.
"""
from django.contrib.auth import aauthenticate, alogin, alogout, get_user_model
from django.middleware.csrf import get_token
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError
from ninja.utils import check_csrf
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)

from app.accounts.schemas import UserOut
from app.common.schemas import MessageOut

from . import otp as otp_service
from . import webauthn as wa
from .models import PasskeyCredential, PasskeyUserHandle
from .schemas import (
    EmailIn,
    LoginIn,
    LoginStartOut,
    OtpVerifyIn,
    PasskeyLoginIn,
    PasskeyOptionsOut,
    PasskeyOut,
    PasskeyRegisterIn,
)
from .throttles import (
    AuthStartThrottle,
    OtpStartThrottle,
    OtpVerifyThrottle,
    PasskeyVerifyThrottle,
)

router = Router(tags=['auth'])

User = get_user_model()

# Passkey and OTP sign-ins never call authenticate(), so Django cannot infer
# which backend authorised them. It has to be named explicitly.
MODEL_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def _require_csrf(request):
    """Reject the request unless it carries a valid CSRF token."""
    if check_csrf(request) is not None:
        raise HttpError(403, 'CSRF verification failed. Fetch /api/auth/csrf first.')


async def _find_user(email):
    """Resolve an email address to the one active account, or ``None``.

    Unambiguous by construction: ``User.email`` is unique and stored
    lower-cased, and only an account with status Active is returned. An erased
    account has no address at all and so can never match.
    """
    if not (email or '').strip():
        return None
    return await User.objects.active_by_email(email).afirst()


@router.get('/csrf', response=MessageOut, auth=None)
async def csrf(request):
    """Set the ``csrftoken`` cookie so the frontend can make unsafe requests.

    ``get_token`` flags the cookie for update and ``CsrfViewMiddleware`` writes
    it on the way out.
    """
    get_token(request)
    return {'detail': 'CSRF cookie set.'}


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------

@router.post(
    '/login/start',
    response=LoginStartOut,
    auth=None,
    throttle=[AuthStartThrottle()],
)
async def login_start(request, payload: EmailIn):
    """Decide which credential to ask this address for, and prepare it.

    An address with at least one passkey gets a WebAuthn challenge. Everyone
    else -- including addresses with no account at all -- gets the same
    ``otp`` response, so the endpoint reveals nothing about who is a member.

    It does reveal which addresses have a passkey, because the credential IDs
    have to reach the browser for the authenticator to match against. That is
    inherent to an identifier-first passkey flow; closing it means moving to a
    usernameless flow over discoverable credentials.
    """
    _require_csrf(request)
    user = await _find_user(payload.email)

    credentials = []
    if user is not None:
        credentials = [credential async for credential in user.passkeys.all()]

    if credentials:
        options, challenge = wa.authentication_options(allow=credentials)
        # The user is pinned to the challenge, so a credential belonging to a
        # different account cannot be presented against it.
        #
        # As text, not as the UUID itself: the session is serialised to JSON,
        # which has no UUID type and raises rather than coercing one.
        await wa.store_challenge(
            request.session, wa.LOGIN_CHALLENGE_KEY, challenge, user_id=str(user.pk)
        )
        return {'method': 'passkey', 'options': options}

    if user is not None:
        await otp_service.issue(user)
    return {'method': 'otp'}


@router.post(
    '/login/passkey',
    response=UserOut,
    auth=None,
    throttle=[PasskeyVerifyThrottle()],
)
async def login_passkey(request, payload: PasskeyLoginIn):
    """Verify a ``navigator.credentials.get()`` response and open a session."""
    _require_csrf(request)

    stored = await wa.take_challenge(request.session, wa.LOGIN_CHALLENGE_KEY)
    if stored is None:
        raise HttpError(400, 'This sign-in attempt has expired. Please start again.')

    credential = (
        await PasskeyCredential.objects.select_related('user')
        .filter(credential_id=payload.credential.get('id') or '')
        .afirst()
    )
    # Both checks give the same vague answer: which passkeys exist, and which
    # account they belong to, are not the client's business.
    #
    # Compared as text, matching how login_start stored it. A UUID and its own
    # string form are never equal, so comparing the two would refuse every
    # passkey that is in fact the right one.
    if credential is None or str(credential.user_id) != stored.get('user_id'):
        raise HttpError(401, 'That passkey was not recognised.')

    try:
        verified = wa.verify_authentication(
            credential=payload.credential,
            challenge=wa.decode(stored['challenge']),
            public_key=wa.decode(credential.public_key),
            sign_count=credential.sign_count,
        )
    except InvalidAuthenticationResponse:
        raise HttpError(401, 'That passkey could not be verified.')

    credential.sign_count = verified.new_sign_count
    credential.backed_up = verified.credential_backed_up
    credential.last_used_at = timezone.now()
    await credential.asave(update_fields=['sign_count', 'backed_up', 'last_used_at'])

    user = credential.user
    # Checked here as well as in login_start: a challenge issued moments before
    # a suspension must not still open a session.
    if not user.is_active:
        raise HttpError(403, 'This account is not active.')

    await alogin(request, user, backend=MODEL_BACKEND)
    return user


@router.post(
    '/otp/start',
    response=MessageOut,
    auth=None,
    throttle=[OtpStartThrottle()],
)
async def otp_start(request, payload: EmailIn):
    """Email a fresh sign-in code. Also the 'send it again' endpoint.

    Always reports success. An unknown address simply gets no email.
    """
    _require_csrf(request)
    user = await _find_user(payload.email)
    if user is not None:
        await otp_service.issue(user)
    return {'detail': 'If that address belongs to a member, a code is on its way.'}


@router.post(
    '/otp/verify',
    response=UserOut,
    auth=None,
    throttle=[OtpVerifyThrottle()],
)
async def otp_verify(request, payload: OtpVerifyIn):
    """Exchange a valid emailed code for a session."""
    _require_csrf(request)
    user = await _find_user(payload.email)
    if user is None or not await otp_service.verify(user, payload.code.strip()):
        raise HttpError(401, 'That code is not valid. Request a new one.')

    await alogin(request, user, backend=MODEL_BACKEND)
    return user


@router.post('/login', response=UserOut, auth=None)
async def login(request, payload: LoginIn):
    """Username and password sign-in, retained for staff.

    Members are expected to use a passkey or an emailed code. This endpoint
    stays because staff still need a password for Django admin, and the
    frontend no longer offers it.
    """
    _require_csrf(request)
    # ModelBackend takes the USERNAME_FIELD value under the keyword `username`
    # whatever that field is actually called; here it is the email address.
    user = await aauthenticate(
        request, username=payload.email, password=payload.password
    )
    if user is None:
        # Deliberately vague: do not reveal whether the address exists.
        # aauthenticate() already refuses a non-Active account, and returns the
        # same None for that as for a wrong password.
        raise HttpError(401, 'Invalid credentials.')
    # Rotates the session key, so a pre-login session cannot be fixated.
    await alogin(request, user)
    return user


@router.post('/logout', response=MessageOut, auth=None)
async def logout(request):
    _require_csrf(request)
    await alogout(request)
    return {'detail': 'Logged out.'}


@router.get('/me', response=UserOut)
async def me(request):
    """The signed-in user. Returns 401 when there is no valid session."""
    return await request.auser()


# ---------------------------------------------------------------------------
# Passkey enrolment and management (session required)
# ---------------------------------------------------------------------------

@router.post('/passkeys/options', response=PasskeyOptionsOut)
async def passkey_register_options(request):
    """Options for ``navigator.credentials.create()``.

    Authenticated on purpose: enrolling a passkey is only possible once the
    member has proved who they are some other way, which for a new account
    means an emailed code.
    """
    user = await request.auser()
    handle, _ = await PasskeyUserHandle.objects.aget_or_create(user=user)
    existing = [credential async for credential in user.passkeys.all()]

    options, challenge = wa.registration_options(
        user_handle=handle.handle.bytes,
        user_name=user.email,
        user_display_name=user.display_name,
        exclude=existing,
    )
    await wa.store_challenge(request.session, wa.REGISTER_CHALLENGE_KEY, challenge)
    return {'options': options}


@router.post('/passkeys', response=PasskeyOut)
async def passkey_register(request, payload: PasskeyRegisterIn):
    """Verify a ``create()`` response and store the new credential."""
    user = await request.auser()

    stored = await wa.take_challenge(request.session, wa.REGISTER_CHALLENGE_KEY)
    if stored is None:
        raise HttpError(400, 'This enrolment has expired. Please try again.')

    try:
        verified = wa.verify_registration(
            credential=payload.credential,
            challenge=wa.decode(stored['challenge']),
        )
    except InvalidRegistrationResponse:
        raise HttpError(400, 'That passkey could not be verified.')

    credential_id = wa.encode(verified.credential_id)
    if await PasskeyCredential.objects.filter(credential_id=credential_id).aexists():
        raise HttpError(409, 'That passkey is already registered.')

    return await PasskeyCredential.objects.acreate(
        user=user,
        credential_id=credential_id,
        public_key=wa.encode(verified.credential_public_key),
        sign_count=verified.sign_count,
        transports=payload.credential.get('response', {}).get('transports') or [],
        aaguid=verified.aaguid or '',
        backed_up=verified.credential_backed_up,
        device_type=verified.credential_device_type.value,
        name=(payload.name or '').strip()[:64] or 'Passkey',
    )


@router.get('/passkeys', response=list[PasskeyOut])
async def passkey_list(request):
    user = await request.auser()
    return [credential async for credential in user.passkeys.all()]


@router.delete('/passkeys/{passkey_id}', response=MessageOut)
async def passkey_delete(request, passkey_id: int):
    """Remove a passkey. The member can always get back in with a code."""
    user = await request.auser()
    deleted, _ = await PasskeyCredential.objects.filter(
        pk=passkey_id, user=user
    ).adelete()
    if not deleted:
        raise HttpError(404, 'No such passkey.')
    return {'detail': 'Passkey removed.'}

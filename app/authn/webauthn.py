"""WebAuthn ceremony helpers, wrapping py_webauthn for this project.

A ceremony is two round trips: the server issues a challenge, the browser has
the authenticator sign it, and the server verifies the signature against that
same challenge. The challenge is held in the Django session between the halves,
which is why it works before the user is signed in -- ``SessionMiddleware``
gives every visitor a session, authenticated or not.

Nothing here touches the database; ``authn.api`` owns persistence.
"""
import json
import time

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from webauthn import (
    base64url_to_bytes,
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

# Session keys. Separate keys for the two ceremonies so a registration
# challenge can never be replayed against the login endpoint.
LOGIN_CHALLENGE_KEY = 'webauthn_login_challenge'
REGISTER_CHALLENGE_KEY = 'webauthn_register_challenge'


def rp_id():
    value = settings.WEBAUTHN_RP_ID
    if not value:
        raise ImproperlyConfigured(
            'DJANGO_WEBAUTHN_RP_ID is not set. It must be the registrable '
            'domain the frontend is served from, e.g. cultivatorscollective.co.za.'
        )
    return value


def origins():
    value = settings.WEBAUTHN_ORIGINS
    if not value:
        raise ImproperlyConfigured(
            'DJANGO_WEBAUTHN_ORIGINS is not set. It must list the full frontend '
            'origins, scheme and port included, e.g. https://app.example.co.za.'
        )
    return value


def _descriptors(credentials):
    """Turn stored credentials into the descriptors the browser expects."""
    return [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
        for c in credentials
    ]


async def store_challenge(session, key, challenge, **extra):
    """Park a challenge in the session with an expiry and any ceremony state."""
    await session.aset(
        key,
        {
            'challenge': bytes_to_base64url(challenge),
            'expires': time.time() + settings.WEBAUTHN_CHALLENGE_TTL_SECONDS,
            **extra,
        },
    )


async def take_challenge(session, key):
    """Pop a stored challenge, returning ``None`` if absent or expired.

    Single use by construction: the value is removed whether or not the
    verification that follows succeeds, so a challenge cannot be replayed.
    """
    stored = await session.apop(key, None)
    if not stored or stored.get('expires', 0) < time.time():
        return None
    return stored


def registration_options(*, user_handle, user_name, user_display_name, exclude):
    """Options for ``navigator.credentials.create()``.

    ``resident_key=preferred`` asks for a discoverable credential so the
    passkey can later identify the user on its own; ``user_verification`` is
    also preferred rather than required, because insisting on it locks out
    authenticators that cannot do biometrics or a PIN.
    """
    options = generate_registration_options(
        rp_id=rp_id(),
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user_handle,
        user_name=user_name,
        user_display_name=user_display_name,
        exclude_credentials=_descriptors(exclude),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return json.loads(options_to_json(options)), options.challenge


def authentication_options(*, allow):
    """Options for ``navigator.credentials.get()``."""
    options = generate_authentication_options(
        rp_id=rp_id(),
        allow_credentials=_descriptors(allow),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return json.loads(options_to_json(options)), options.challenge


def verify_registration(*, credential, challenge):
    """Verify a ``create()`` response. Raises on anything unexpected."""
    return verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp_id(),
        expected_origin=origins(),
    )


def verify_authentication(*, credential, challenge, public_key, sign_count):
    """Verify a ``get()`` response, including the replay-counter check."""
    return verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=rp_id(),
        expected_origin=origins(),
        credential_public_key=public_key,
        credential_current_sign_count=sign_count,
    )


def encode(value):
    """bytes -> base64url text, the form everything is stored and sent in."""
    return bytes_to_base64url(value)


def decode(value):
    """base64url text -> bytes."""
    return base64url_to_bytes(value)

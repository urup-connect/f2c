"""Request and response shapes for the sign-in endpoints.

These are the contract between Django and the Next.js frontend. Keep them
explicit rather than auto-generated from models, so a model change cannot
silently alter the payload the frontend depends on.

WebAuthn options and credentials cross the wire as opaque dicts. They are
defined by the W3C serialisation that the browser and py_webauthn both already
speak, and re-declaring that structure here would only add a second place for
it to drift.

The member returned on a successful sign-in is ``accounts.schemas.UserOut``.
It is not redeclared here: this app authenticates a member, it does not define
one.
"""
from datetime import datetime
from typing import Any, Literal

from ninja import Schema


class LoginIn(Schema):
    """Staff sign-in. Members use a passkey or an emailed code instead."""

    email: str
    password: str


class EmailIn(Schema):
    email: str


class LoginStartOut(Schema):
    """Which credential the frontend should ask for next.

    ``passkey`` carries the ``navigator.credentials.get()`` options.
    ``otp`` means a code has been emailed, and nothing else is returned --
    including for addresses with no account, so the response cannot be used to
    discover who is a member.
    """

    method: Literal['passkey', 'otp']
    options: dict[str, Any] | None = None


class PasskeyLoginIn(Schema):
    email: str
    credential: dict[str, Any]


class OtpVerifyIn(Schema):
    email: str
    code: str


# --------------------------------------------------------------------------
# Passkey management (authenticated)
# --------------------------------------------------------------------------

class PasskeyOptionsOut(Schema):
    options: dict[str, Any]


class PasskeyRegisterIn(Schema):
    credential: dict[str, Any]
    name: str = ''


class PasskeyOut(Schema):
    id: int
    name: str
    backed_up: bool
    device_type: str
    created_at: datetime
    last_used_at: datetime | None

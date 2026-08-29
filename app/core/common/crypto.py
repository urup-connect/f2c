"""Application-level encryption for the few fields that must be readable again.

Most secrets in this project are hashed and never recovered -- OTP codes, staff
passwords. An identity-document number is different: it has to be produced in
full when a member's identity is checked, so it must be encrypted rather than
hashed.

Two separate secrets do two separate jobs:

``FIELD_ENCRYPTION_KEY``
    AES-256-GCM, with a fresh random nonce per record. That makes the
    ciphertext non-deterministic, which is the point -- two members with the
    same ID number produce different ciphertext, so the column leaks nothing
    to anyone reading a database dump.

``BLIND_INDEX_PEPPER``
    Non-deterministic ciphertext also cannot be indexed or searched, which
    would leave no way to enforce "one account per ID number". The blind index
    fills that gap: a keyed HMAC of the normalised value, unique-indexed, which
    supports equality lookups and nothing else. It is keyed rather than a plain
    hash because the space of valid South African ID numbers is small enough to
    enumerate against an unkeyed digest.

Both are deliberately separate from ``DJANGO_SECRET_KEY``: that key is rotated
on a different schedule (and after any suspected leak), and rotating it must
not render every stored ID number unreadable.
"""
import base64
import hashlib
import hmac
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# AES-GCM's standard nonce length. Anything else costs an extra derivation
# step inside the cipher for no benefit.
NONCE_BYTES = 12

# Prefixed to every ciphertext so a future change of algorithm can be told
# apart from this one without a migration guessing game.
VERSION = b'\x01'


class DecryptionError(Exception):
    """The stored value could not be decrypted or failed its integrity check.

    Raised for a wrong key, a truncated column, or a tampered row. Never
    swallowed: a silent fallback to empty string would quietly hide the fact
    that data is unrecoverable.
    """


def _decode_key(raw, name, length):
    """Decode a base64 secret from settings and check its length."""
    if not raw:
        raise ImproperlyConfigured(
            f'{name} is not set. Generate one with:\n'
            '    python -c "import base64, secrets; '
            'print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"'
        )
    try:
        key = base64.urlsafe_b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(f'{name} is not valid base64.') from exc
    if len(key) != length:
        raise ImproperlyConfigured(
            f'{name} must decode to {length} bytes, got {len(key)}.'
        )
    return key


def _cipher():
    key = _decode_key(
        getattr(settings, 'FIELD_ENCRYPTION_KEY', ''), 'FIELD_ENCRYPTION_KEY', 32
    )
    return AESGCM(key)


def _pepper():
    return _decode_key(
        getattr(settings, 'BLIND_INDEX_PEPPER', ''), 'BLIND_INDEX_PEPPER', 32
    )


def encrypt(plaintext, context):
    """Encrypt ``plaintext``, binding the result to ``context``.

    ``context`` is authenticated but not encrypted, and should name the field
    the value belongs in (``'accounts.User.id_number'``). GCM verifies it on the way
    back out, so a ciphertext copied into a different column -- or a different
    row's -- fails to decrypt instead of silently decoding.

    Returns base64url text: version, nonce, then ciphertext-with-tag.
    """
    if plaintext is None or plaintext == '':
        return ''
    nonce = secrets.token_bytes(NONCE_BYTES)
    sealed = _cipher().encrypt(
        nonce, str(plaintext).encode(), context.encode()
    )
    return base64.urlsafe_b64encode(VERSION + nonce + sealed).decode()


def decrypt(token, context):
    """Reverse :func:`encrypt`. Raises :class:`DecryptionError` on any failure."""
    if not token:
        return ''
    try:
        blob = base64.urlsafe_b64decode(token)
    except (ValueError, TypeError) as exc:
        raise DecryptionError('Stored value is not valid base64.') from exc

    if len(blob) < len(VERSION) + NONCE_BYTES + 16:
        raise DecryptionError('Stored value is too short to be a ciphertext.')
    if blob[: len(VERSION)] != VERSION:
        raise DecryptionError(
            f'Unsupported ciphertext version {blob[:len(VERSION)]!r}.'
        )

    nonce = blob[len(VERSION) : len(VERSION) + NONCE_BYTES]
    sealed = blob[len(VERSION) + NONCE_BYTES :]
    try:
        return _cipher().decrypt(nonce, sealed, context.encode()).decode()
    except InvalidTag as exc:
        raise DecryptionError(
            'Ciphertext failed its integrity check: wrong key, wrong field, '
            'or a modified row.'
        ) from exc


def blind_index(value, context):
    """A keyed, deterministic digest of ``value`` for equality lookups.

    Case- and whitespace-insensitive, so ``Craig@Example.com `` and
    ``craig@example.com`` index identically. ``context`` is mixed in for the
    same reason as in :func:`encrypt`: an email digest and an ID-number digest
    of the same string must not collide.
    """
    if value is None or value == '':
        return ''
    normalised = str(value).strip().casefold().encode()
    return hmac.new(
        _pepper(), context.encode() + b'\x00' + normalised, hashlib.sha256
    ).hexdigest()

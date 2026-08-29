"""The state behind passkey and email-OTP authentication.

These models are deliberately narrow: no request metadata, no IP addresses,
nothing that would turn a credential table into a tracking log. Rate limiting
lives in the cache instead (see ``authn.throttles``), which keeps personal data
out of the database under POPIA's minimality principle.

Every model here points at ``AUTH_USER_MODEL`` and cascades on delete, and each
declares a reverse relation -- ``passkeys``, ``email_otps``, ``passkey_handle``.
Those names are the interface ``accounts.models.User.soft_delete`` uses to
revoke a member's credentials without importing this app.
"""
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class PasskeyCredential(models.Model):
    """One WebAuthn credential belonging to one user.

    ``credential_id`` and ``public_key`` are stored base64url-encoded rather
    than as ``BinaryField``s: they are looked up and compared as opaque
    identifiers, and text columns index identically on SQLite and PostgreSQL.
    """

    class DeviceType(models.TextChoices):
        SINGLE = 'single_device', 'Single device'
        MULTI = 'multi_device', 'Multi device'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='passkeys',
    )
    # base64url, as the browser reports it. Unique across all users: a
    # credential belongs to exactly one account.
    credential_id = models.CharField(max_length=512, unique=True)
    # base64url-encoded COSE public key returned by the authenticator.
    public_key = models.TextField()
    # Replay defence. Many authenticators always report 0, which the WebAuthn
    # spec permits; the library only enforces monotonicity when it is non-zero.
    sign_count = models.PositiveBigIntegerField(default=0)
    transports = models.JSONField(default=list, blank=True)
    aaguid = models.CharField(max_length=36, blank=True)
    # True for a synced passkey (iCloud Keychain, Google Password Manager).
    # Surfaced to the user so they can tell a synced key from a hardware one.
    backed_up = models.BooleanField(default=False)
    device_type = models.CharField(
        max_length=16, choices=DeviceType.choices, default=DeviceType.SINGLE
    )
    # User-supplied label, e.g. "Work laptop". Never trusted for anything.
    name = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name = 'passkey'

    def __str__(self):
        return f'{self.name or "Passkey"} ({self.user})'


class EmailOtpQuerySet(models.QuerySet):
    def usable(self):
        """Codes that are still live: unconsumed, unexpired, attempts left."""
        return self.filter(
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
            attempts__lt=settings.OTP_MAX_ATTEMPTS,
        )


class EmailOtp(models.Model):
    """A single-use numeric code emailed to a user as the passkey fallback.

    Only ever created for a user that exists. Unknown addresses get the same
    API response with no row and no email, so the endpoint cannot be used to
    enumerate accounts.
    """

    class Purpose(models.TextChoices):
        LOGIN = 'login', 'Login'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_otps',
    )
    purpose = models.CharField(
        max_length=16, choices=Purpose.choices, default=Purpose.LOGIN
    )
    # Hashed with Django's configured password hasher. A six-digit code is
    # only 10^6 possibilities, so a fast hash would be reversible from a DB
    # dump before the code even expired.
    code_hash = models.CharField(max_length=256)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    objects = EmailOtpQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['user', 'purpose', 'consumed_at']),
        ]
        verbose_name = 'email OTP'
        verbose_name_plural = 'email OTPs'

    def __str__(self):
        return f'{self.get_purpose_display()} code for {self.user}'

    @staticmethod
    def generate_code():
        """A zero-padded numeric code of ``OTP_CODE_LENGTH`` digits."""
        length = settings.OTP_CODE_LENGTH
        return f'{secrets.randbelow(10 ** length):0{length}d}'

    @staticmethod
    def default_expiry():
        return timezone.now() + timedelta(seconds=settings.OTP_TTL_SECONDS)

    @property
    def is_usable(self):
        return (
            self.consumed_at is None
            and self.attempts < settings.OTP_MAX_ATTEMPTS
            and self.expires_at > timezone.now()
        )


class PasskeyUserHandle(models.Model):
    """The opaque ``user.id`` presented to authenticators for a given user.

    WebAuthn stores this value inside the credential and, for discoverable
    credentials, syncs it to the user's password manager. The spec is explicit
    that it must not contain personal information, which rules out the email
    address. The account's own UUID primary key is not used either: it appears
    in URLs and API payloads, and a handle that leaks out of a password manager
    should not be a key to anything else.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='passkey_handle',
    )
    handle = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    def __str__(self):
        return f'Passkey handle for {self.user}'

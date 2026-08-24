"""The member record and the manager that creates one.

``User`` is this project's ``AUTH_USER_MODEL``: one model for members and staff
alike, distinguished by ``is_staff``. The alternative -- Django's default user
for admin plus a separate member model for the frontend -- would mean a second
authentication stack and two identities for anyone who is both.

Two fields on ``User`` are duplicated on purpose, and both are explained where
they are declared: ``is_active`` mirrors ``status`` because Django's auth stack
filters on it in SQL, and ``email_hash`` outlives ``email`` so a returning
member can be recognised after erasure. Neither is written by hand.

``soft_delete`` is the POPIA erasure route and the reason this app is not purely
declarative: erasing a member has to revoke their credentials, which belong to
``authn``. It reaches them through the reverse relations that app declares
rather than importing it, so the dependency stays one-directional.
"""
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.contrib.sessions.models import Session
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone

from app.common import crypto
from app.common.validators import (
    nickname_key,
    normalise_id_number,
    normalise_sa_mobile_number,
    sa_id_birth_date,
    validate_sa_id_number,
    validate_sa_mobile_number,
)


class UserStatus(models.TextChoices):
    """Where an account sits in its lifecycle.

    Exactly one value grants access. ``PENDING`` is a member who has registered
    but has not been verified, ``PENDING_PAYMENT`` is one whose details are on
    file and whose membership has not been paid for, ``SUSPENDED`` is a block
    that can be lifted, and ``INACTIVE`` is where an account lands after
    :meth:`User.soft_delete`. Keeping them distinct matters: "not yet
    approved", "not yet paid", "in trouble" and "erased on request" are
    different situations that a single boolean cannot tell apart.

    ``PENDING_PAYMENT`` is where sign-up leaves a new member. It is a status
    value rather than a row in a membership table on purpose, for now: the one
    question the whole application asks of it is *may this person sign in*, and
    that question is already answered here, in SQL, by the check constraint on
    ``User``. A ``Membership`` model with a subscription period and a gateway
    reference arrives with the payment gateway; until there is a payment to
    record, a second table would hold one fact that this field already holds.
    """

    PENDING = 'pending', 'Pending verification'
    PENDING_PAYMENT = 'pending_payment', 'Pending payment'
    ACTIVE = 'active', 'Active'
    SUSPENDED = 'suspended', 'Suspended'
    INACTIVE = 'inactive', 'Inactive'


class UserManager(BaseUserManager):
    """Creates accounts keyed on email, since there is no username field."""

    use_in_migrations = True

    def _create(self, email, password, **extra):
        email = (email or '').strip()
        if not email:
            raise ValueError('An email address is required.')
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            # Members sign in with a passkey or an emailed code and never hold
            # a password. An unusable one is not an empty one: it cannot match
            # any input, so it cannot be guessed.
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email=None, password=None, **extra):
        extra.setdefault('status', UserStatus.PENDING)
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create(email, password, **extra)

    def create_superuser(self, email=None, password=None, **extra):
        extra['is_staff'] = True
        extra['is_superuser'] = True
        extra.setdefault('status', UserStatus.ACTIVE)
        return self._create(email, password, **extra)

    def active(self):
        return self.filter(status=UserStatus.ACTIVE)

    def active_by_email(self, email):
        """The one live account for an address, as a queryset.

        ``email`` is unique and always stored lower-cased, so this matches at
        most one row -- unlike Django's default user model, where a duplicated
        address is ambiguous and whoever registered second could intercept the
        first member's sign-in codes.
        """
        return self.active().filter(email=(email or '').strip().lower())

    def by_id_number(self, value):
        """Accounts holding this identity-document number.

        Matched through the blind index; the ciphertext itself is not
        searchable by design. See ``common.crypto``.
        """
        digits = normalise_id_number(value)
        if not digits:
            return self.none()
        return self.filter(
            id_number_hash=crypto.blind_index(digits, User.ID_NUMBER_CONTEXT)
        )

    def by_mobile(self, value):
        """Accounts holding this mobile number, however it was written.

        The value is normalised before the lookup, so ``082 123 4567`` and
        ``+27821234567`` find the same row -- the same normalisation
        ``User.save`` applies on the way in, which is what stops a queryset and
        the unique constraint from disagreeing about who holds a handset.

        A number the rule refuses matches nothing rather than raising. Callers
        here are asking *who holds this*, and a malformed number is held by
        nobody; refusing it is the validator's job, at the point of write.
        """
        normalised = normalise_sa_mobile_number(value)
        if not normalised:
            return self.none()
        return self.filter(mobile=normalised)

    def by_nickname(self, value):
        """Accounts wearing this nickname, compared case-insensitively.

        Uniqueness is decided on the lower-cased form, so ``Grower`` and
        ``grower`` cannot both exist while the capitalisation the member chose
        is what other members see. Matched the same way the unique constraint
        on the model indexes it, so a queryset and the database cannot
        disagree.
        """
        key = nickname_key(value)
        if not key:
            return self.none()
        return self.annotate(_nickname_key=Lower('nickname')).filter(_nickname_key=key)

    def nickname_is_taken(self, value, *, exclude_pk=None):
        """Whether this nickname belongs to somebody already.

        Erased accounts are not excluded, and that is deliberate: erasure
        blanks the nickname (see :meth:`User.soft_delete`), so an erased row
        holds none to collide with, and a *suspended* member's nickname must
        stay theirs while the suspension lasts.
        """
        candidates = self.by_nickname(value)
        if exclude_pk is not None:
            candidates = candidates.exclude(pk=exclude_pk)
        return candidates.exists()

    def has_been_seen(self, email):
        """Whether this address ever held an account, erased ones included.

        Answers "is this person coming back?" without an erased row having to
        keep their address. See ``User.email_hash``.
        """
        email = (email or '').strip().lower()
        if not email:
            return False
        return self.filter(
            email_hash=crypto.blind_index(email, User.EMAIL_CONTEXT)
        ).exists()


class User(AbstractBaseUser, PermissionsMixin):
    """A member of the collective, and the Django account behind them."""

    # Namespaces for the encryption and blind-index helpers. They bind a stored
    # value to the column it belongs in, so ciphertext copied into a different
    # field fails to decrypt rather than silently decoding. Never change these
    # without re-encrypting the column.
    ID_NUMBER_CONTEXT = 'accounts.User.id_number'
    EMAIL_CONTEXT = 'accounts.User.email'

    # UUIDv7, not v4: it is time-ordered, so inserts land at the end of the
    # primary-key index instead of scattering random writes across it. Free on
    # SQLite, and it matters once this moves to PostgreSQL.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    # The sign-in identifier. Nullable only so soft delete can clear it; a live
    # account always has one. Unique, and lower-cased by save().
    email = models.EmailField(unique=True, null=True, blank=True)
    # Keyed digest of the address, written alongside `email` and deliberately
    # not cleared by soft delete. It answers "has this person been here
    # before?" once the address itself is gone -- which the collective needs in
    # order to recognise a returning member, and which POPIA's minimality
    # principle prefers to keeping the address on an erased record. Not unique:
    # an erased member is allowed to register again.
    email_hash = models.CharField(
        max_length=64, blank=True, db_index=True, editable=False
    )

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    # What the frontend shows. Members of a collective know each other by this
    # far more often than by a legal name. Unique case-insensitively -- see the
    # constraint in Meta, and `UserManager.by_nickname` for why that is the
    # comparison rather than a plain unique=True.
    nickname = models.CharField(max_length=60, blank=True)

    # Always `+27` followed by nine digits: `validate_sa_mobile_number` is the
    # only way in, and it normalises before it accepts. That normalisation is
    # what makes the constraint below mean anything -- `082 123 4567` and
    # `+27821234567` are one handset, and a unique index over the raw text a
    # member typed would let both through.
    #
    # One handset, one member, by decision of the club. It is a contact detail
    # rather than a credential -- members sign in with an emailed code or a
    # passkey, never with this -- so uniqueness is not a security control here.
    # It is the club's rule about who may hold a membership, enforced in the
    # same place as the address and the identity number. The cost is explicit
    # and accepted: a member who has no phone of their own cannot give a
    # partner's or a parent's. See `Meta.constraints` and
    # `UserManager.by_mobile`.
    mobile = models.CharField(
        max_length=16,
        blank=True,
        validators=[validate_sa_mobile_number],
        help_text='Stored as +27 and nine digits, whatever form it was given in.',
    )

    date_of_birth = models.DateField(null=True, blank=True)
    # When someone confirmed the date of birth against a document. Null means
    # unverified, and no amount of a member typing their own birthday changes
    # that. Set by capture_sa_id_number(), or by hand for a foreign document.
    date_of_birth_verified_at = models.DateTimeField(null=True, blank=True)

    # AES-256-GCM ciphertext. Read and written through the `id_number`
    # property; never touch this column directly.
    id_number_encrypted = models.TextField(blank=True, editable=False)
    # Keyed digest of the same value. The ciphertext uses a fresh nonce per row
    # and so cannot be indexed or compared; this is what enforces one account
    # per identity document.
    id_number_hash = models.CharField(
        max_length=64, unique=True, null=True, blank=True, editable=False
    )

    status = models.CharField(
        max_length=16,
        choices=UserStatus.choices,
        default=UserStatus.PENDING,
        db_index=True,
    )
    # A denormalised copy of `status == ACTIVE`, and the reason for the check
    # constraint below. Django's auth stack does not merely read `is_active`,
    # it filters on it in SQL -- admin login, ModelBackend and password reset
    # all do -- so a Python property would satisfy the reads and break every
    # queryset. `status` is the source of truth; save() derives this from it
    # and nothing else may write it.
    is_active = models.BooleanField(default=False, editable=False)
    is_staff = models.BooleanField(
        default=False,
        help_text='Grants access to the Django admin site.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Distinguishes an account that was erased from one merely deactivated.
    # `status` alone cannot: both end up INACTIVE.
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    # Everything else is optional at creation, so `createsuperuser` asks only
    # for an address and a password.
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ('-created_at',)
        constraints = [
            # Belt and braces on the denormalisation above. Any write that
            # changes `status` without letting save() recompute `is_active` --
            # a queryset .update(), a data migration, raw SQL -- fails loudly
            # here rather than silently locking a member out, or letting a
            # suspended one back in.
            models.CheckConstraint(
                condition=(
                    models.Q(status=UserStatus.ACTIVE, is_active=True)
                    | (~models.Q(status=UserStatus.ACTIVE) & models.Q(is_active=False))
                ),
                name='user_is_active_matches_status',
                violation_error_message=(
                    'is_active is derived from status and cannot be set directly.'
                ),
            ),
            # One nickname, one member -- compared case-insensitively, because
            # `Grower` and `grower` read as the same person to everyone but the
            # database, and a nickname that reads as an existing member's is
            # impersonation. Indexed on Lower() rather than on a second
            # denormalised column: a stored key would be one more thing that
            # can drift from the value it is derived from, and `is_active`
            # above is the only denormalisation this model can justify.
            #
            # Blank nicknames are excluded rather than colliding. Staff have
            # none, and erasure blanks the field (see soft_delete), so without
            # the condition the second erased member would be refused by the
            # database.
            models.UniqueConstraint(
                Lower('nickname'),
                condition=~models.Q(nickname=''),
                name='user_nickname_unique_ci',
                violation_error_message='That nickname is already taken.',
            ),
            # One handset, one member. No Lower() and no expression: save()
            # normalises the column to `+27` and nine digits before it is
            # written, so the stored text is already the only form there is.
            #
            # Blank numbers are excluded, for the same reason as the nickname
            # above: staff have none, and erasure blanks the field, so without
            # the condition the second erased member would be refused by the
            # database.
            #
            # This is the third of the three identity keys, alongside `email`
            # (unique on the column) and `id_number_hash` (unique on the blind
            # index). All three are enforced here rather than only in the
            # registration service, because a queryset .update(), a data
            # migration or a member of staff in the admin does not go through
            # it.
            models.UniqueConstraint(
                fields=['mobile'],
                condition=~models.Q(mobile=''),
                name='user_mobile_unique',
                violation_error_message=(
                    'Another account already holds that mobile number.'
                ),
            ),
        ]

    def __str__(self):
        return self.email or self.nickname or f'Erased member {self.pk}'

    # ------------------------------------------------------------------
    # Names
    # ------------------------------------------------------------------

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        return self.nickname or self.first_name

    @property
    def display_name(self):
        """What to put in front of a human. Never blank, never a raw UUID."""
        return self.nickname or self.get_full_name() or self.email or 'Member'

    # ------------------------------------------------------------------
    # Identity document
    # ------------------------------------------------------------------

    @property
    def id_number(self):
        """The plaintext document number, or ``''`` when none is held.

        Raises ``crypto.DecryptionError`` if the column cannot be decrypted --
        wrong key, or a modified row. That is deliberate: returning a blank
        string would quietly present unrecoverable data as absent.
        """
        return crypto.decrypt(self.id_number_encrypted, self.ID_NUMBER_CONTEXT)

    @id_number.setter
    def id_number(self, value):
        """Encrypt and index in one step, so the two cannot drift apart.

        Accepts any document number. Use :meth:`capture_sa_id_number` when it
        is a South African ID and should be checked.
        """
        digits = normalise_id_number(value)
        if not digits:
            self.id_number_encrypted = ''
            self.id_number_hash = None
            return
        self.id_number_encrypted = crypto.encrypt(digits, self.ID_NUMBER_CONTEXT)
        self.id_number_hash = crypto.blind_index(digits, self.ID_NUMBER_CONTEXT)

    @property
    def has_id_number(self):
        """True when a number is on file, without decrypting it."""
        return bool(self.id_number_encrypted)

    def capture_sa_id_number(self, value, verified_at=None):
        """Validate an RSA ID number, store it, and read the birth date off it.

        Taking the date of birth from the document rather than having it typed
        in again means the two cannot disagree. Does not save; the caller
        decides when. Raises ``ValidationError`` on a malformed number.
        """
        digits = validate_sa_id_number(value)
        self.id_number = digits
        self.date_of_birth = sa_id_birth_date(digits)
        self.date_of_birth_verified_at = verified_at or timezone.now()
        return digits

    # ------------------------------------------------------------------
    # Persistence and lifecycle
    # ------------------------------------------------------------------

    def save(self, *args, update_fields=None, **kwargs):
        # Derive is_active from status on every write, so the two cannot drift
        # and the check constraint above never fires in normal use.
        self.is_active = self.status == UserStatus.ACTIVE

        if self.email:
            # Lower-cased whole, not just the domain as normalize_email() does.
            # Case-sensitive local parts are legal and universally ignored by
            # real mail providers; honouring them here would let someone
            # register Member@example.com alongside member@example.com and
            # receive the other's sign-in codes.
            self.email = self.email.strip().lower()
            self.email_hash = crypto.blind_index(self.email, self.EMAIL_CONTEXT)
        # No else: a null email leaves the digest standing. That is the entire
        # point of email_hash -- see its declaration.

        if self.mobile:
            # One stored form, whatever form it arrived in -- the same reason
            # the address above is lower-cased. Raises rather than storing a
            # value the rule does not accept: the admin's field validator has
            # already refused it politely, so anything reaching here came from
            # code, and code should hear about it.
            self.mobile = validate_sa_mobile_number(self.mobile)

        if update_fields is not None:
            update_fields = set(update_fields) | {'is_active'}
            if 'email' in update_fields:
                update_fields.add('email_hash')

        super().save(*args, update_fields=update_fields, **kwargs)

    @transaction.atomic
    def soft_delete(self):
        """Erase the personal data on this account but keep the row.

        The row survives because other records point at it -- who grew what,
        who paid what -- and cascading those away would destroy the
        collective's own operating history. What goes is everything that
        identifies the person: name, nickname, email address, mobile number,
        ID number.
        ``email_hash`` is the one deliberate survivor, and its declaration says
        why.

        Credentials go too. A passkey or a live session against an erased
        account is both a way back in and personal data in its own right, so
        neither is left behind.

        Reversible only in the sense that the row can be reactivated; the
        erased fields are gone.
        """
        if self._state.adding:
            raise ValueError('Cannot soft-delete an unsaved user.')

        self.first_name = ''
        self.last_name = ''
        self.nickname = ''
        self.email = None
        self.mobile = ''
        self.id_number_encrypted = ''
        self.id_number_hash = None
        self.status = UserStatus.INACTIVE
        self.deleted_at = timezone.now()
        self.set_unusable_password()
        # A full save, not update_fields: `updated_at` is auto_now, and Django
        # skips auto_now columns that a partial save does not name.
        self.save()

        # Reached through the reverse relations ``authn`` declares, not by
        # importing its models: ``authn`` depends on this app, and an import
        # back the other way would make the two apps mutually dependent.
        # Django's reverse one-to-one accessor raises a subclass of
        # AttributeError when the row is absent, which is what makes getattr's
        # default work here.
        self.passkeys.all().delete()
        self.email_otps.all().delete()
        handle = getattr(self, 'passkey_handle', None)
        if handle is not None:
            handle.delete()
        self.flush_sessions()
        return self

    def flush_sessions(self):
        """End every live session this user holds. Returns how many were cut.

        Changing `status` does not touch the session store, so without this an
        already signed-in browser keeps working until its cookie expires.
        Sessions carry no user column, so they have to be decoded to be
        matched.
        """
        user_id = str(self.pk)
        keys = [
            session.session_key
            for session in Session.objects.filter(expire_date__gte=timezone.now())
            if session.get_decoded().get('_auth_user_id') == user_id
        ]
        if not keys:
            return 0
        Session.objects.filter(session_key__in=keys).delete()
        return len(keys)

    def deactivate(self, status=UserStatus.SUSPENDED):
        """Block sign-in without erasing anything: the reversible half."""
        self.status = status
        self.save(update_fields=['status', 'updated_at'])
        self.flush_sessions()
        return self

    def activate(self):
        """Let this account sign in again. Refuses to resurrect an erased one."""
        if self.deleted_at is not None:
            raise ValueError(
                'This account was erased and cannot be reactivated; its personal '
                'data is gone. Create a new account instead.'
            )
        self.status = UserStatus.ACTIVE
        self.save(update_fields=['status', 'updated_at'])
        return self

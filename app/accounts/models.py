"""The member record and the manager that creates one.

``User`` is this project's ``AUTH_USER_MODEL``: one model for members and staff
alike, distinguished by ``is_staff``. The alternative -- Django's default user
for admin plus a separate member model for the frontend -- would mean a second
authentication stack and two identities for anyone who is both.

Two fields on ``User`` are duplicated on purpose, and both are explained where
they are declared: ``is_active`` mirrors ``status`` because Django's auth stack
filters on it in SQL, and ``email_hash`` outlives ``email`` so a returning
member can be recognised after erasure. Neither is written by hand.

``role`` says what the account *is* -- admin, cultivator or member -- where
``status`` says whether it may sign in. Exactly one role per account, enforced
by a check constraint, and ``save`` mirrors it into a Django group of the same
name. The role itself and the catalogue of what each one may do live in
``accounts.roles``, which is also where the reasoning behind a column rather
than a group membership is set out.

``soft_delete`` is the POPIA erasure route and the reason this app is not purely
declarative: erasing a member has to revoke their credentials, which belong to
``authn``. It reaches them through the reverse relations that app declares
rather than importing it, so the dependency stays one-directional.
"""
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import Group, PermissionsMixin
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

from .roles import ROLE_GROUP_NAMES, UserRole

# Re-exported so that ``from app.accounts.models import UserRole`` reads the
# same way as ``UserStatus`` beside it. ``accounts.roles`` is the canonical
# home: the role and the catalogue of what each one may do belong together, and
# a status has no such catalogue.
__all__ = ['User', 'UserManager', 'UserRole', 'UserStatus']


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
        extra.setdefault('role', UserRole.MEMBER)
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create(email, password, **extra)

    def create_superuser(self, email=None, password=None, **extra):
        extra['is_staff'] = True
        extra['is_superuser'] = True
        extra.setdefault('status', UserStatus.ACTIVE)
        # A default, not a derivation. `role` and `is_staff` are independent by
        # decision -- see `UserRole` -- so nothing here forces one from the
        # other, and `create_superuser(role=...)` overrides this. But the
        # account that bootstraps a deployment is the club's administrator, and
        # leaving it at the column default would have the admin list describe
        # the founder as an ordinary member.
        extra.setdefault('role', UserRole.ADMIN)
        return self._create(email, password, **extra)

    def active(self):
        return self.filter(status=UserStatus.ACTIVE)

    def with_role(self, role):
        """Accounts holding this role, whatever their status.

        Deliberately not filtered to active accounts: "who are our
        cultivators" and "who can sign in today" are different questions, and a
        suspended cultivator is still a cultivator. Chain
        ``.filter(status=UserStatus.ACTIVE)`` when the second is what is meant.
        """
        return self.filter(role=role)

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
    # What the account is, where `status` is whether it may sign in. Exactly one
    # value, held by every account including staff, and checked in SQL by the
    # constraint in Meta.
    #
    # The default is Member because that is where a completed registration
    # leaves everybody, and because it is the safest value to land on: it grants
    # nothing over anybody else's records. A role is granted by hand from there.
    # `save()` mirrors it into a Django group -- see `sync_role_group` -- and
    # `accounts.roles` holds the catalogue of what each role may do.
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.MEMBER,
        db_index=True,
        help_text=(
            'What this account is. Separate from staff status, which opens the '
            'Django admin and is granted independently.'
        ),
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
            # One role per account, and it has to be one this application
            # recognises. `choices` is a form-level rule that a queryset
            # `.update()`, a data migration or raw SQL walks straight past, and
            # the failure mode without this is quiet: `permissions_for` returns
            # an empty set for a role it does not know, so an account would
            # simply stop being able to do anything, with nothing to explain
            # why. Adding a role means a migration, which is the right cost --
            # roles are a schema-level fact about the club, not runtime data.
            models.CheckConstraint(
                condition=models.Q(role__in=UserRole.values),
                name='user_role_is_known',
                violation_error_message=(
                    'That is not a role this platform recognises.'
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
    # Role
    # ------------------------------------------------------------------

    #: The role as it stands in the database, so ``save`` can tell whether it
    #: changed and skip the group write when it did not. ``None`` on an unsaved
    #: instance, which is what makes the first save always sync.
    _role_in_db = None

    @classmethod
    def from_db(cls, db, field_names, values, *args, **kwargs):
        """Remember the stored role, so ``save`` can spot a change.

        Guarded on ``field_names`` because a ``.only()`` or ``.defer()``
        queryset need not have loaded the column, and reading it here would
        turn every deferred fetch into a second query.

        ``*args, **kwargs`` are passed straight through and deliberately not
        named: Django adds arguments to this hook between releases -- 6.1 passes
        ``fetch_mode`` -- and a signature that lists them breaks every queryset
        on upgrade. Nothing here needs them.
        """
        instance = super().from_db(db, field_names, values, *args, **kwargs)
        if 'role' in field_names:
            instance._role_in_db = instance.role
        return instance

    @property
    def is_club_admin(self):
        """Holds the Admin role. Says nothing about Django admin access.

        ``is_staff`` is the flag that opens ``/admin/``, and the two are
        independent by decision -- see ``roles.UserRole``. Named
        ``is_club_admin`` rather than ``is_admin`` precisely so that the two
        cannot be misread for each other at a call site.
        """
        return self.role == UserRole.ADMIN

    @property
    def is_cultivator(self):
        return self.role == UserRole.CULTIVATOR

    @property
    def is_member(self):
        return self.role == UserRole.MEMBER

    def set_role(self, role):
        """Move this account to another role, and sync its group.

        The reason to use this rather than assigning ``role`` and saving: it
        refuses a value the platform does not recognise here, with a
        ``ValueError`` naming the field, instead of leaving the database check
        constraint to refuse it as an ``IntegrityError`` naming an index.

        Live sessions are left alone, unlike ``deactivate``. A session carries
        no cached permissions -- every request resolves the role afresh through
        ``accounts.backends`` -- so a role change takes effect on the next
        request without signing anybody out. What can lag is a page already
        rendered in a member's browser, which is a refresh rather than a
        privilege.
        """
        if role not in UserRole.values:
            raise ValueError(f'{role!r} is not a role this platform recognises.')
        self.role = role
        self.save(update_fields=['role', 'updated_at'])
        return self

    def sync_role_group(self):
        """Put this account in the Django group matching its role, and no other.

        Only the three role groups are touched. Any other group a member of
        staff has put the account in is left standing, because those are
        somebody's deliberate act and this is bookkeeping.

        Nothing reads the group to decide a platform action --
        ``accounts.roles`` explains why it exists at all -- so a group that has
        drifted grants nothing. ``get_or_create`` rather than ``get`` for the
        same reason: a missing group is a row somebody deleted, not a reason to
        fail a save.
        """
        wanted = ROLE_GROUP_NAMES[self.role]
        group, _ = Group.objects.get_or_create(name=wanted)
        stale = Group.objects.filter(
            name__in=set(ROLE_GROUP_NAMES.values()) - {wanted}
        )
        self.groups.remove(*stale)
        self.groups.add(group)
        return group

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

        # Whether this write is one the role column travels in. A partial save
        # that does not name `role` cannot change it, so mirroring the group
        # afterwards would sync to a value that was never stored.
        role_written = update_fields is None or 'role' in update_fields

        super().save(*args, update_fields=update_fields, **kwargs)

        # After the row exists, because the group is a many-to-many and an
        # unsaved instance has no primary key to join on. Only when the value
        # actually moved: this is two or three extra queries, and every ordinary
        # save -- a status change, a login timestamp -- would otherwise pay them
        # to write the group it already has.
        if role_written and self._role_in_db != self.role:
            self.sync_role_group()
            self._role_in_db = self.role

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

        ``role`` deliberately stays, and so does the group mirroring it. A role
        is a fact about the collective's own structure rather than about the
        person -- that this cultivator grew what the batch records say it grew
        -- and it confers nothing here: ``roles.permissions_for`` refuses an
        inactive account before it ever looks at the role, and this method
        leaves the account Inactive.

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

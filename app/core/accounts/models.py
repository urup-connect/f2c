"""The member record and the manager that creates one.

``User`` is this project's ``AUTH_USER_MODEL``: one model for members and staff
alike, distinguished by ``is_staff``. The alternative -- Django's default user
for admin plus a separate member model for the frontend -- would mean a second
authentication stack and two identities for anyone who is both.

Two fields on ``User`` are duplicated on purpose, and both are explained where
they are declared: ``is_active`` mirrors ``status`` because Django's auth stack
filters on it in SQL, and ``email_hash`` outlives ``email`` so a returning
member can be recognised after erasure. Neither is written by hand.

``status`` says whether this identity may sign in, and **nothing else**. What
somebody *is* -- a club member, a producer's appointed staff, a storefront
administrator -- lives in the relationship rather than on the account, because
one person is routinely several of them at once. See ``membership.models``,
``cultivators.models.ProducerMembership`` and ``storefronts.models``, and C27
and C28 in ``design/conflict.md``.

There is no ``role`` column, and there is no group mirroring one. C28 retired
both: one person may administer a storefront, hold a membership and be appointed
to two producers at once, and a column could say only one of those. What an
account may do is resolved from those relationships in ``accounts.roles``.

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
from django.utils import timezone

from app.core.common import crypto
from app.core.common.validators import (
    mask_id_number,
    normalise_id_number,
    normalise_sa_mobile_number,
    sa_id_birth_date,
    validate_sa_id_number,
    validate_sa_mobile_number,
)
from .storage import avatar_storage, avatar_upload_to

__all__ = [
    'IdentityNumberDisclosure',
    'User',
    'UserManager',
    'UserStatus',
]


class UserStatus(models.TextChoices):
    """Whether this identity may sign in. Four values, and one grants access.

    **This used to say more than it does now.** ``PENDING`` and
    ``PENDING_PAYMENT`` described a club membership rather than an account, and
    the previous version of this docstring argued that a membership table would
    hold one fact this field already held. That was true while the club was the
    whole platform. It stopped being true with the produce market: ``is_active``
    is derived from this column under a check constraint, and
    ``PENDING_PAYMENT`` is not ``ACTIVE``, so somebody buying carrots could not
    sign in at all. Both values moved to ``membership.MembershipStatus``. C27,
    and ``design/verticals.md`` section 5.

    A consequence worth stating plainly, because it changes behaviour rather
    than only shape: **an unpaid club registrant can now sign in.** They land on
    a screen asking them to pay instead of being refused at the door. The club
    gate moved from the account to the membership, which is where the market
    needed it to be.

    ``NON_AUTHENTICATING`` is the one value that is not a stage in a lifecycle.
    It is where an identity sits that holds records and never signs in -- today
    only the sharing member, which **C6** has now decided is a placeholder
    rather than a person. It stays named for the fact rather than for the club
    concept: "this row authenticates nobody" is what the auth stack needs to
    know, and it will still be true of whatever the swap zone makes of the
    placeholder.

    ``INACTIVE`` remains where an account lands after :meth:`User.soft_delete`.
    Erasure is a fact about a person, so it stays on the person.
    """

    ACTIVE = 'active', 'Active'
    SUSPENDED = 'suspended', 'Suspended'
    INACTIVE = 'inactive', 'Inactive'
    NON_AUTHENTICATING = 'non_authenticating', 'Holds records, never signs in'


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
        # Active, where this used to default to PENDING. An account is now an
        # identity and nothing more: there is nothing to verify before somebody
        # may hold one, and the address is proved by the emailed code they sign
        # in with. Whether they may *use* the club is `ClubMembership.status`.
        extra.setdefault('status', UserStatus.ACTIVE)
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create(email, password, **extra)

    def create_superuser(self, email=None, password=None, **extra):
        extra['is_staff'] = True
        extra['is_superuser'] = True
        extra.setdefault('status', UserStatus.ACTIVE)
        # No role, and nothing else. `is_staff` **is** the platform operator's
        # tier -- C29 -- so an account that bootstraps a deployment is complete
        # as it stands. It used to be given the club administrator role as well,
        # on the reasoning that the founder should not appear in the admin list
        # as an ordinary member. There is no list of roles to appear in now, and
        # administering the club is a `StorefrontStaff` row granted
        # deliberately rather than a side effect of `createsuperuser`.
        return self._create(email, password, **extra)

    def active(self):
        return self.filter(status=UserStatus.ACTIVE)

    def with_platform_roles(self):
        """Accounts with every relationship ``permissions_for`` reads loaded.

        **Required wherever the permission set is serialised or a list is
        rendered.** ``accounts.roles.permissions_for`` reads the club
        membership, the storefront appointments and the producer appointments;
        unloaded, that is three queries per account, and inside the async views
        in ``authn.api`` it is not slow but fatal --
        ``SynchronousOnlyOperation``.

        ``select_related`` for the one-to-one and ``prefetch_related`` for the
        two reverse foreign keys, which is two extra queries for any number of
        accounts rather than two per account.
        """
        return self.select_related('club_membership').prefetch_related(
            'storefront_appointments', 'producer_appointments'
        )

    def with_club_membership(self):
        """Accounts with their club membership already loaded.

        **Required, not an optimisation, anywhere the result is serialised by
        ``UserOut`` or rendered in a list.** Two things read the membership off
        an account -- ``club_nickname`` and the membership status on the session
        payload -- and both go through the reverse one-to-one, which issues a
        query the first time it is touched. In a list that is one query per row;
        inside the async views in ``authn.api`` it is worse than slow, because a
        synchronous ORM call there raises ``SynchronousOnlyOperation``.

        The failure is at least loud. That is deliberate: the alternative was a
        resolver that quietly returns nothing when the relation is not loaded,
        which would put "this member has no nickname" on a screen instead of an
        error somebody fixes.

        No import of ``membership`` here, and none is needed -- Django resolves
        the reverse accessor by name at query time, so this app keeps its
        one-directional dependency.
        """
        return self.select_related('club_membership')

    def producers(self):
        """Accounts appointed to at least one producer, whatever their status.

        The replacement for `with_role(UserRole.CULTIVATOR)`. `distinct()`
        because the join multiplies a row by its appointments, and somebody
        appointed to two farms is one account.

        Deliberately not filtered to active accounts: "who are our cultivators"
        and "who can sign in today" are different questions, and a suspended
        cultivator is still a cultivator. Chain
        `.filter(status=UserStatus.ACTIVE)` when the second is what is meant.
        """
        return self.filter(producer_appointments__isnull=False).distinct()

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

    # There is no `nickname` here any more. It is what the *club* shows, not a
    # property of a person -- a produce customer has a name and needs no
    # pseudonym -- so it moved to `membership.ClubMembership` with the
    # uniqueness key and both constraints that policed it. C27.

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

    # The same trick as `nickname_key`, for the same reason, and read that one
    # first. This is a plain mirror rather than a normalisation: `save` has
    # already put `mobile` in its one canonical form, so the only work left is
    # turning a blank into a null so that the accounts holding no number -- staff,
    # and every erased member -- do not collide with each other under an
    # unconditional unique index.
    mobile_key = models.CharField(
        max_length=16, null=True, blank=True, editable=False
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
        max_length=24,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
        db_index=True,
        help_text=(
            'Whether this identity may sign in. What somebody may *do* is the '
            'membership, not this.'
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

    # The four sharing-member columns are gone from here too -- the cultivator
    # who registered them and the three recording the POPIA attestation. What
    # they describe is a club arrangement rather than anything about the person,
    # so they moved to `membership.ClubMembership` unchanged. **C6 is still open
    # on what a sharing member is**, and nothing was redesigned in passing.

    # The member's own photograph, kept on the private avatars store rather
    # than the container the CDN fronts -- see `accounts.storage`. Always a
    # 512-pixel square JPEG, because `accounts.avatars` decodes and re-encodes
    # every upload rather than storing what arrived; nothing else may write
    # here. Blank is the normal state and is not a gap to be filled: a member
    # who wants no photograph of themselves on file is entitled to none.
    avatar = models.FileField(
        blank=True,
        storage=avatar_storage,
        upload_to=avatar_upload_to,
        help_text='Set through the profile endpoint, which crops and re-encodes.',
    )
    # When the avatar last changed. It is what lets the address the frontend
    # requests carry a version, so a replaced photograph is fetched again
    # instead of the browser showing the cached previous one -- `avatar` itself
    # cannot say, because every avatar is written to the same path. Null for an
    # account that has never had one.
    avatar_updated_at = models.DateTimeField(null=True, blank=True, editable=False)

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
            # One handset, one member. No case folding needed: save() normalises
            # the column to `+27` and nine digits before it is written, so the
            # stored text is already the only form there is, and `mobile_key` is
            # a plain mirror of it with a blank turned into a null.
            #
            # Blank numbers do not collide, for the same reason as the nickname
            # above: staff have none, and erasure blanks the field.
            #
            # This is the third of the three identity keys, alongside `email`
            # (unique on the column) and `id_number_hash` (unique on the blind
            # index). All three are enforced here rather than only in the
            # registration service, because a queryset .update(), a data
            # migration or a member of staff in the admin does not go through
            # it.
            #
            # Over `mobile_key` rather than `mobile`, and unconditional, for the
            # same reason as the nickname above: the condition that excluded
            # blanks is what MySQL cannot build, so the exclusion moved into the
            # column as a null.
            models.UniqueConstraint(
                fields=['mobile_key'],
                name='user_mobile_key_unique',
                violation_error_message=(
                    'Another account already holds that mobile number.'
                ),
            ),
            # `mobile_key` is a denormalised column, and section 3.1's argument
            # about `is_active` applies to it word for word: a column derived by
            # `save` is a column a queryset `.update()`, a data migration or raw
            # SQL can leave behind. So it is tied to its source in SQL, and this
            # is the backstop rather than the rule.
            #
            # The explicit null test beside the equality is load-bearing, not
            # belt and braces. A `CHECK` fails only when its condition is
            # *false*, and a SQL comparison against null is *unknown*, which
            # passes -- so without it a row with a number and no key would
            # satisfy this constraint by being unanswerable.
            models.CheckConstraint(
                condition=(
                    models.Q(mobile='', mobile_key__isnull=True)
                    | models.Q(
                        mobile_key__isnull=False, mobile_key=models.F('mobile')
                    )
                ),
                name='user_mobile_key_matches_mobile',
                violation_error_message=(
                    'mobile_key is derived from mobile and cannot be set '
                    'directly.'
                ),
            ),
        ]

    def __str__(self):
        return self.email or f'Erased member {self.pk}'

    # ------------------------------------------------------------------
    # Names
    # ------------------------------------------------------------------

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    def get_short_name(self):
        """A name for an email greeting. **Account fields only.**

        Deliberately *not* the club nickname, and this is the second bug of its
        kind in Block 0.5. Both callers -- the emailed sign-in code and the
        payment link -- greet a person by name, and both run where reaching into
        another table is wrong for two separate reasons:

        * ``authn.otp.issue`` is called from an ``async def`` view, where a lazy
          relation is not slow but fatal;
        * a produce-market customer has no club membership at all, so a greeting
          that depended on one would have nothing to say to them.

        ``display_name`` is the one that prefers the nickname, and its callers
        are club surfaces that select the relation. See ``club_nickname``.
        """
        return self.first_name

    @property
    def club_nickname(self):
        """This account's club nickname, or ``''`` when there is no membership.

        The nickname moved to ``membership.ClubMembership`` with the split, and
        this reads it back for the callers that legitimately want *the club's*
        name for somebody. A produce customer has no membership and no nickname,
        and gets a blank rather than an error.

        **This is a query per call unless the caller has selected the relation.**
        Anything rendering a list -- the admin, the member register, the swap
        zone -- must ``select_related('club_membership')`` or it pays one query
        per row. The reverse one-to-one raises a subclass of ``AttributeError``
        when the row is absent, which is what makes ``getattr``'s default work.
        """
        membership = getattr(self, 'club_membership', None)
        return membership.nickname if membership is not None else ''

    @property
    def display_name(self):
        """What to put in front of a human. Never blank, never a raw UUID.

        Still prefers the club nickname, because that is what members know each
        other by and what the compliance rules on pseudonymity assume -- see
        ``club_nickname`` above on the query it costs.
        """
        return (
            self.club_nickname or self.get_full_name() or self.email or 'Member'
        )

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

    @property
    def id_number_masked(self):
        """All but the last four digits, or ``''`` when none is on file.

        Decrypts, so it is a property rather than a column and it is not free.
        Raises ``crypto.DecryptionError`` for a row that will not decrypt --
        surfaced rather than swallowed, because that is a key or integrity
        problem somebody has to look at, and each caller has its own idea of
        what to show while they do.
        """
        if not self.has_id_number:
            return ''
        return mask_id_number(self.id_number)

    @property
    def has_avatar(self):
        """True when a photograph is on file.

        ``FileField`` is falsey when the column is blank, which is what this
        reads. It does not ask storage whether the blob is really there: that
        would be a network call per render against the Azure backend, and a
        column pointing at a missing blob is a broken deployment rather than a
        state a screen should try to describe.
        """
        return bool(self.avatar)

    def clear_avatar(self):
        """Delete the stored photograph and forget it. Does not save.

        Deletes the blob as well as blanking the column, because the whole
        reason avatars overwrite one path is that the club has no reason to hold
        a photograph a member has taken down. ``delete(save=False)`` is what
        does both; the caller saves.

        Tolerant of a blob that is already gone. Storage failing to delete
        something that does not exist must not stop the column being cleared --
        otherwise a half-migrated environment leaves a member unable to remove
        their own photograph.
        """
        if not self.avatar:
            self.avatar_updated_at = None
            return self

        try:
            self.avatar.delete(save=False)
        except FileNotFoundError:
            self.avatar = ''

        self.avatar_updated_at = None
        return self

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
    # Relationships
    # ------------------------------------------------------------------
    # What used to be four `is_*` properties over a role column. They read the
    # relationships instead -- C28 -- and each is one query unless the caller
    # loaded them. `UserManager.with_platform_roles()` is how.

    @property
    def is_sharing_member(self):
        """A placeholder holding flowering stock in the swap zone. C6.

        Not a person: no name, no identity number, no consent. It cannot sign
        in, which is `UserStatus.NON_AUTHENTICATING` on this row, and what it
        holds is the club's business, which is the membership row.
        """
        membership = getattr(self, 'club_membership', None)
        return membership is not None and membership.is_sharing_member

    @property
    def is_producer(self):
        """Whether this account is appointed to any producer at all.

        **One query.** For a single account in a synchronous view; use
        `User.objects.producers()` for a list, and `with_platform_roles()`
        before serialising.
        """
        return self.producer_appointments.exists()

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

        # The uniqueness key, derived after its source has been normalised
        # above and never written by hand. `or None` is doing the load-bearing
        # work: a null is what lets the accounts holding no number coexist under
        # an unconditional unique index. See the field declaration, and
        # `design/backend.md` section 8.2.
        self.mobile_key = self.mobile or None

        if update_fields is not None:
            update_fields = set(update_fields) | {'is_active'}
            if 'email' in update_fields:
                update_fields.add('email_hash')
            # A partial save that changes a member's number must not leave the
            # key it is compared on behind -- that would be a row whose stored
            # number and whose uniqueness key disagree, which is exactly the
            # drift the `is_active` treatment above exists to prevent.
            if 'mobile' in update_fields:
                update_fields.add('mobile_key')

        super().save(*args, update_fields=update_fields, **kwargs)

    @transaction.atomic
    def soft_delete(self):
        """Erase the personal data on this account but keep the row.

        The row survives because other records point at it -- who grew what,
        who paid what -- and cascading those away would destroy the
        collective's own operating history. What goes is everything that
        identifies the person: name, email address, mobile number, ID number,
        their photograph -- the last of which is deleted from storage rather
        than merely unlinked, since a blob nobody points at is still a picture
        of somebody's face -- and the club nickname, which now lives one table
        away and is cleared through it.
        ``email_hash`` is the one deliberate survivor, and its declaration says
        why.

        Credentials go too. A passkey or a live session against an erased
        account is both a way back in and personal data in its own right, so
        neither is left behind.

        The relationships deliberately stay -- the club membership, the
        storefront appointments, the producer appointments. They are facts about
        the collective's own structure rather than about the person: that this
        cultivator grew what the batch records say it grew. They confer nothing
        on an erased account either, because ``roles.permissions_for`` refuses
        an inactive one before it looks at any of them, and this method leaves
        the account Inactive.

        A sharing member has nothing here to erase. **C6** decided it is a
        placeholder rather than a person, so it holds no name, no address and
        no identity number, and the consent attestation that used to make
        holding those lawful is gone from the schema. ``registered_by`` on the
        membership stays: it names the *cultivator* whose stock the placeholder
        holds, which is that cultivator's act rather than anybody's personal
        data.

        Reversible only in the sense that the row can be reactivated; the
        erased fields are gone.
        """
        if self._state.adding:
            raise ValueError('Cannot soft-delete an unsaved user.')

        self.first_name = ''
        self.last_name = ''
        self.email = None
        self.mobile = ''
        self.id_number_encrypted = ''
        self.id_number_hash = None
        # The blob goes, not just the column. A photograph of a face is
        # personal data in the plainest sense, and an erasure that left the
        # image sitting in storage with only the pointer removed would be an
        # erasure the club could not honestly claim to have made.
        self.clear_avatar()
        self.status = UserStatus.INACTIVE
        self.deleted_at = timezone.now()
        self.set_unusable_password()
        # A full save, not update_fields: `updated_at` is auto_now, and Django
        # skips auto_now columns that a partial save does not name.
        self.save()

        # The club nickname, which is personal data and lives one table away
        # now. Reached through the reverse accessor rather than by importing
        # `membership.models`, for the same reason the credential clean-up below
        # does not import `authn`: both apps depend on this one, and an import
        # back would make them mutually dependent.
        membership = getattr(self, 'club_membership', None)
        if membership is not None:
            membership.nickname = ''
            membership.save(update_fields=['nickname', 'updated_at'])

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
        if self.status == UserStatus.NON_AUTHENTICATING:
            # This identity holds records and authenticates nobody -- today only
            # a sharing member, pending **C6**. Refused here rather than left to
            # the database so that a bulk action in the admin says something
            # useful instead of failing the whole transaction on an index name.
            raise ValueError(
                'This identity holds records and never signs in, so there is '
                'nothing to activate. A sharing member joining as a member '
                'needs a membership of their own, not a status change.'
            )
        self.status = UserStatus.ACTIVE
        self.save(update_fields=['status', 'updated_at'])
        return self


class IdentityNumberDisclosure(models.Model):
    """One occasion on which a member of staff read a member's ID number.

    ``design/backend.md`` section 10 makes the identity number **write-only** in
    the Django admin: staff may set it and confirm which one is on file from the
    masked last four digits, and the plaintext is never rendered. The reasoning
    is that putting the number on a page puts it in the browser cache, the proxy
    logs and anyone's shoulder view, for no operational gain.

    The administrator's Next.js register keeps that default and adds one
    exception, and this row is the price of the exception. Reading the number in
    full is a deliberate act that names a reason and leaves a record: the
    endpoint writes one of these *before* it decrypts anything, so a read that
    happened is a read that is recorded even if the response never reaches the
    caller. There is no endpoint that returns the number without writing one.

    **Nothing here is editable, and there is no delete.** A row staff can type
    into is not evidence of anything -- the same argument
    ``documents.DocumentConsent`` makes about a consent ledger.

    Two deletion rules, and they differ on purpose:

    * ``member`` cascades. Erasure is ``User.soft_delete``, which keeps the row,
      so this is reached only by a real deletion -- superusers only -- and a
      disclosure against an account that no longer exists names nobody. The same
      reading ``payments.Subscription.user`` and ``documents.DocumentConsent.user``
      take.
    * ``read_by`` is ``SET_NULL``. Deleting the *auditor's* account must not
      erase the fact that a disclosure happened, only who made it. The same
      reading ``documents.DocumentVersion.published_by`` takes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    member = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='identity_disclosures',
        editable=False,
    )
    read_by = models.ForeignKey(
        'User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='identity_numbers_read',
        editable=False,
    )

    # Required, and required with content: a disclosure with no stated reason is
    # a disclosure nobody can review afterwards, which is the whole purpose of
    # the row. `blank=False` makes `full_clean` say so, and the service checks it
    # before the write because the endpoint is the only caller that can supply
    # one.
    reason = models.CharField(
        max_length=200,
        help_text='Why the number had to be read. Recorded, and never blank.',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            # The one query this table answers: what has been read against this
            # member, most recent first. It is what the member's own screen shows
            # and what a POPIA request would be answered from.
            models.Index(
                fields=('member', '-created_at'),
                name='idnum_disclosure_member_idx',
            ),
        ]
        verbose_name = 'identity number disclosure'
        verbose_name_plural = 'identity number disclosures'

    def __str__(self):
        return f'Identity number of {self.member_id} read by {self.read_by_id}'

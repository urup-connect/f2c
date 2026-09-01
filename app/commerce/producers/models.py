"""The cultivator's public face.

The third model ``todo.md`` Block 1 asks for, beside the strain and the finished
product type: "Cultivator profile: public description, image, pseudonym". It is
its own app rather than a fourth class in ``strains`` because it is not a strain,
and because Block 2 grows it into the cultivator organisation -- the farm as a
record, with its primary cultivator, its appointed staff, its collection address
and its bank details. Those arrive here.

**There is no pseudonym field, and that is the decision worth defending.**

``member-roles.md`` conceals members behind a nickname, and
``plant-id-numbers.md`` puts a "cultivator pseudonym" on the certificate of
ownership -- so the club clearly needs a public name for a grower. What it does
not need is a *second namespace* for one. ``backend.md`` section 4.6 already
settled the same question for sharing members and gave the reason in one line:
"two people wearing one name in the swap zone is impersonation, not a
collision". A ``pseudonym`` column here would be exactly that second namespace,
free to hold a value identical to another member's nickname, and no single
constraint can span the two.

So the pseudonym *is* ``User.nickname``. It is already unique
case-insensitively across every account, it is already what
``accounts.User.display_name`` returns, and it is already the only member
identifier the API is allowed to expose. A cultivator wanting a trading name
sets it as their nickname.

One consequence, recorded because it is not obvious: nickname uniqueness is
enforced by a **partial** unique index (blanks excluded, because staff have none
and erasure blanks the field), and MySQL cannot express one. Django omits it
silently on a backend that does not support it, so on MySQL nothing stops two
accounts sharing a nickname. That is a pre-existing hole in ``accounts``, not one
this app opens, but this app is the first thing to depend on the guarantee.

**MySQL.** The same four considerations as ``strains.models``, and one more:
this table's uniqueness is a one-to-one on a foreign key, which is an
unconditional unique index and portable.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from app.core.common import crypto
from app.core.storefronts.models import Storefront


def profile_image_upload_to(instance, filename):
    """``cultivators/<profile id>/image<ext>``.

    One path per profile, overwritten in place -- the same reasoning as
    ``strains.models.listing_image_upload_to``, which also records the open
    question about which storage a public catalogue image belongs in.
    """
    extension = (filename.rsplit('.', 1)[-1] or 'jpg').lower()[:8]
    return f'cultivators/{instance.pk}/image.{extension}'


class ProducerQuerySet(models.QuerySet):
    def published(self):
        """Producers a member may see."""
        return self.filter(is_published=True)

    def selling_into(self, storefront):
        """Producers that sell into one storefront. See ``ProducerStorefront``."""
        return self.filter(storefronts__storefront=storefront).distinct()


class Producer(models.Model):
    """The farm as a record: who it trades as, where stock is collected, who is paid.

    **This was ``CultivatorProfile``, and the change is more than a rename.**
    That model was a profile hanging off one user account by a one-to-one, and
    its own comments said twice that it pointed at a user and should point at a
    farm. It does now: the organisation is the record, the people are
    ``ProducerMembership`` rows against it, and the primary is the appointment
    that says so.

    It is deliberately **not** cannabis-specific. A farmer supplying the produce
    market is the same record with a different storefront -- see
    ``ProducerStorefront`` -- which is why it lives on the commerce side rather
    than in the club vertical. ``design/verticals.md`` section 6.

    A producer is optional in the sense that people are appointed before the
    organisation is described: appointments can exist against a bare row, and
    stock can exist before the description does. What cannot happen is a member
    reaching an unpublished one.
    """

    # Namespace for the encryption helper, binding a stored value to the column
    # it belongs in: ciphertext copied into a different field fails to decrypt
    # rather than silently decoding. Never change it without re-encrypting.
    BANK_ACCOUNT_CONTEXT = 'cultivators.Producer.bank_account_number'

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # **The name the organisation trades under**, and the reason the one-to-one
    # to a user is gone. `pseudonym` used to return the owner's nickname, with a
    # comment saying that if the club ever decided a farm needed a trading name
    # distinct from its owner's, there should be one place to change. This is
    # that place, and the decision made itself: a farm with three appointed
    # staff has no single owner whose nickname to borrow.
    trading_name = models.CharField(
        max_length=80,
        help_text='What members see. The farm trades under this, not under an '
                  'owner’s nickname.',
    )
    # Lower-cased trading name, and the column the uniqueness rule is actually
    # decided on. The fifth derived column in this project, after
    # `nickname_key`, `mobile_key`, `live_for_user` and `primary_for_producer`,
    # and it exists for the same reason all four do: the natural spelling is
    # `UniqueConstraint(Lower('trading_name'))`, which is an expression index,
    # and MySQL builds none while Django omits what the backend will not build
    # without saying so. `design/backend.md` section 8.2 and
    # `design/migrations.md` section 2.
    #
    # Not nullable, unlike the others: every producer has a trading name, so
    # there is no blank case to keep out of the index.
    trading_name_key = models.CharField(max_length=80, editable=False)

    public_description = models.TextField(
        blank=True,
        help_text='Your description of your farm, shown to members. '
                  'Compliance-governed copy: no claim about what cannabis does.',
    )
    image = models.ImageField(
        upload_to=profile_image_upload_to,
        blank=True,
        help_text='One photograph, shown beside your name.',
    )

    # A profile is drafted before it is shown. Unpublished is the default so
    # that creating the row is never itself the act of publishing -- the same
    # argument `documents` makes for publication being an action rather than a
    # save.
    is_published = models.BooleanField(
        default=False,
        help_text='Members see this profile only once it is published.',
    )

    # ------------------------------------------------------------------
    # Collection, and settlement
    # ------------------------------------------------------------------
    # Both are Block 2's, from the drawio cultivator story: "My Farm -- users,
    # collection address, sharing members, bank details".
    #
    # **What settlement actually needs is unspecified -- C10.** These are the
    # fields the story names and no more; whether the platform collects and
    # remits or introduces and invoices is undecided, and the answer may want a
    # tax number, a mandate reference or nothing at all. Guessing at those now
    # would be inventing a commercial model in a schema.

    collection_address = models.TextField(
        blank=True,
        help_text='Where a courier collects from. Members never see this.',
    )

    bank_account_name = models.CharField(max_length=120, blank=True)
    bank_name = models.CharField(max_length=80, blank=True)
    bank_branch_code = models.CharField(max_length=16, blank=True)
    # Encrypted at rest, through the same helper the identity number uses. It is
    # not blind-indexed, and the difference is the point: an identity number is
    # searched -- "is this person already on file" -- and an account number is
    # only ever read back to the person it belongs to or to whoever runs the
    # payout. Adding an index nothing queries would be a second place for the
    # ciphertext to leak from.
    bank_account_number_encrypted = models.TextField(blank=True, editable=False)

    objects = ProducerQuerySet.as_manager()

    class Meta:
        ordering = ('trading_name',)
        verbose_name = 'producer'
        constraints = [
            # One trading name, compared case-insensitively. Two farms reading
            # as the same name to everybody but the database is the same
            # impersonation problem the nickname rule exists for, and a member
            # choosing which carrot to buy by producer rating has to be able to
            # tell them apart.
            models.UniqueConstraint(
                fields=['trading_name_key'],
                name='producer_trading_name_key_unique',
                violation_error_message='A producer already trades under that name.',
            ),
            # The backstop tying the derived column to its source, in the same
            # migration as the index over it. `save` keeps them true; this stops
            # a write that went around it. No null test is needed here, unlike
            # the nickname's: the column is not nullable.
            models.CheckConstraint(
                condition=models.Q(trading_name_key=Lower('trading_name')),
                name='producer_trading_name_key_matches_name',
                violation_error_message=(
                    'trading_name_key is derived from trading_name and cannot '
                    'be set directly.'
                ),
            ),
        ]

    def __str__(self):
        return self.trading_name

    @property
    def pseudonym(self):
        """The producer's public name.

        Every caller that wants a grower's pseudonym -- the strain comparison
        screen, the certificate of ownership, the plant's derived pseudonym
        field -- reads this rather than reaching for a person's nickname.

        It used to return the owner's ``display_name``, with a note that one
        place to change would be wanted if a farm ever needed a name of its own.
        This is that change, and it costs nothing at the call sites.
        """
        return self.trading_name

    @property
    def primary(self):
        """The appointment that owns this producer, or ``None``.

        A query unless the caller prefetched ``appointments``. There is at most
        one -- ``producer_membership_one_primary`` says so in SQL -- and there
        can be none: a producer created in the admin before anybody is appointed
        to it is a legitimate intermediate state, and returning ``None`` beats
        raising at a call site that only wanted a name to display.
        """
        for appointment in self.appointments.all():
            if appointment.is_primary:
                return appointment
        return None

    @property
    def bank_account_number(self):
        """The plaintext account number, or ``''`` when none is held.

        Raises ``crypto.DecryptionError`` if the column will not decrypt --
        wrong key, or a modified row -- rather than returning a blank, which
        would present unrecoverable data as absent. The same treatment as
        ``User.id_number``.
        """
        return crypto.decrypt(
            self.bank_account_number_encrypted, self.BANK_ACCOUNT_CONTEXT
        )

    @bank_account_number.setter
    def bank_account_number(self, value):
        digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
        self.bank_account_number_encrypted = (
            crypto.encrypt(digits, self.BANK_ACCOUNT_CONTEXT) if digits else ''
        )

    def save(self, *args, update_fields=None, **kwargs):
        # Trimmed for one stored form, and it is also what makes
        # `trading_name_key` exactly `LOWER(trading_name)` -- without it
        # ` Kloof ` would be stored with a key of `kloof` and the check
        # constraint would refuse the model's own write.
        self.trading_name = (self.trading_name or '').strip()
        self.trading_name_key = self.trading_name.lower()

        if update_fields is not None and 'trading_name' in set(update_fields):
            update_fields = set(update_fields) | {'trading_name_key'}

        super().save(*args, update_fields=update_fields, **kwargs)


class ProducerStorefront(models.Model):
    """Which storefronts a producer sells into.

    A table rather than two booleans, and rather than a column on ``Producer``,
    because a producer sells into *some* of them: one farm may supply the club
    with cannabis and the market with vegetables, and another only one of the
    two. A pair of booleans says the same thing today and says nothing useful
    the day a third storefront exists.

    **Not to be confused with a product category.** Which storefront a producer
    sells into is this; which produce they sell within the market -- vegetables,
    honey, biltong -- is the market catalogue's, and belongs to that vertical.
    The two were briefly one idea under the name ``ProducerCategory``, and
    keeping them apart is the reason this is not called that.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    producer = models.ForeignKey(
        'producers.Producer',
        on_delete=models.CASCADE,
        related_name='storefronts',
    )
    storefront = models.CharField(
        max_length=16,
        choices=Storefront.choices,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('producer', 'storefront')
        verbose_name = 'producer storefront'
        constraints = [
            models.UniqueConstraint(
                fields=('producer', 'storefront'),
                name='producer_storefront_once_each',
                violation_error_message=(
                    'This producer already sells into that storefront.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(storefront__in=Storefront.values),
                name='producer_storefront_is_known',
                violation_error_message=(
                    'That is not a storefront this platform serves.'
                ),
            ),
        ]

    def __str__(self):
        return f'{self.producer} — {self.get_storefront_display()}'


class ProducerRole(models.TextChoices):
    """What an appointed person may do for a producer.

    ``PRIMARY`` is the account the organisation belongs to: the owner of the
    farm. Only the primary appoints staff, registers sharing members and
    controls the farm's public identity, per ``member-roles`` and C13.
    ``FULL`` manages stock, listings and pricing; ``LIMITED`` manages stock
    only. The distinction is the brief's -- "appointed staff with full or
    limited rights" -- and it is a column here rather than a permission because
    it is a fact about one appointment, not about the person.

    **These three are the whole of "as permitted by the primary" -- C13.** The
    farm's structure says staff act *as permitted by* the owner, and the
    permission being granted is this column: appointing somebody ``FULL`` is
    what permits them to move stock into a sharing member's hands, and
    ``LIMITED`` is what withholds it. There is no per-appointment grant beside
    the tier, deliberately: a second permission system next to
    ``accounts.roles`` would need every screen to ask both, and no requirement
    yet distinguishes a staff member who may allocate from one who may price.
    """

    PRIMARY = 'primary', 'Primary'
    FULL = 'full', 'Appointed staff, full rights'
    LIMITED = 'limited', 'Appointed staff, limited rights'


class ProducerMembership(models.Model):
    """One person's appointment to one producer organisation.

    This is Block 2's "appointed staff with full or limited rights", built as
    the general thing rather than the cannabis-specific one: a farmer supplying
    the produce market gets the same table. C28, and ``design/verticals.md``
    section 6.

    **It is what makes the object-level rules expressible.** ``RoleBackend``
    refuses object-level questions today because "their own listings" had
    nothing to point at -- C13 and ``roles-and-permissions.md`` risk 9. With a
    row per person per producer, "their own" is a join rather than a special
    case.

    The producer is still ``CultivatorProfile`` while the generalisation to
    ``Producer`` is the next section of Block 0.5. Nothing here is
    cannabis-specific and the rename carries it unchanged.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    producer = models.ForeignKey(
        Producer,
        on_delete=models.CASCADE,
        related_name='appointments',
    )
    # CASCADE for the same reason as `ClubMembership.user`: an appointment
    # without the person is not a record of anything, and erasure keeps the
    # `User` row rather than deleting it.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='producer_appointments',
    )
    role = models.CharField(
        max_length=16,
        choices=ProducerRole.choices,
        default=ProducerRole.LIMITED,
        db_index=True,
    )

    appointed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('producer', 'role', 'appointed_at')
        verbose_name = 'producer appointment'
        constraints = [
            # One appointment per person per producer. Somebody promoted from
            # limited to full holds one appointment that changed, not two.
            models.UniqueConstraint(
                fields=('producer', 'user'),
                name='producer_membership_once_per_producer',
                violation_error_message=(
                    'This person is already appointed to that producer.'
                ),
            ),
            # `choices` is a form-level rule, and an unrecognised value here
            # would leave somebody appointed with no rights at all and nothing
            # to explain why.
            models.CheckConstraint(
                condition=models.Q(role__in=ProducerRole.values),
                name='producer_membership_role_is_known',
                violation_error_message=(
                    'That is not a producer role this platform recognises.'
                ),
            ),
            # **One primary per producer**, and the club's rule that only the
            # primary appoints staff is meaningless without it. A partial unique
            # index is the natural spelling and MySQL builds none -- see
            # `design/backend.md` section 8.2 -- so the rule hangs off a derived
            # column that is null for everybody who is not the primary.
            models.UniqueConstraint(
                fields=('primary_for_producer',),
                name='producer_membership_one_primary',
                violation_error_message=(
                    'That producer already has a primary cultivator.'
                ),
            ),
            # The backstop tying the derived column to what it is derived from,
            # in the same migration as the index over it. The explicit null test
            # is load-bearing: a CHECK passes on `unknown`, so without it a
            # primary row with a null slot would satisfy this by being
            # unanswerable.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        role=ProducerRole.PRIMARY,
                        primary_for_producer__isnull=False,
                    )
                    | (
                        ~models.Q(role=ProducerRole.PRIMARY)
                        & models.Q(primary_for_producer__isnull=True)
                    )
                ),
                name='producer_membership_primary_slot_matches_role',
                violation_error_message=(
                    'primary_for_producer is derived from role and cannot be '
                    'set directly.'
                ),
            ),
        ]

    # A copy of `producer_id` while this appointment is the primary one, and
    # null otherwise. The fourth derived column in this project, after
    # `nickname_key`, `mobile_key` and `live_for_user`, and it exists for the
    # same reason all three do: nulls are distinct under a unique index on every
    # backend here, so an unconditional index over this expresses "at most one
    # primary per producer" without the partial condition MySQL will not build.
    primary_for_producer = models.UUIDField(null=True, blank=True, editable=False)

    @property
    def is_primary(self):
        """The account the organisation belongs to. Only the primary appoints
        staff and creates sharing-member placeholders -- ``member-roles``."""
        return self.role == ProducerRole.PRIMARY

    @property
    def has_full_rights(self):
        """Whether this appointment carries the commercial decisions.

        Pricing, listings and allocation to sharing members, as against moving
        stock. **Not the public profile** -- that went to the primary with C13,
        because the identity members see is the farm owner's. The primary holds
        everything here as well: being the primary is more than full rights, not
        an alternative to them.

        Asked of the appointment by ``accounts.roles.permissions_for`` rather
        than compared against a value there, so that module needs no import from
        here.
        """
        return self.role in (ProducerRole.PRIMARY, ProducerRole.FULL)

    def __str__(self):
        return f'{self.user} — {self.get_role_display()} at {self.producer}'

    def save(self, *args, update_fields=None, **kwargs):
        self.primary_for_producer = (
            self.producer_id if self.role == ProducerRole.PRIMARY else None
        )
        if update_fields is not None:
            fields = set(update_fields)
            if 'role' in fields or 'producer' in fields:
                fields.add('primary_for_producer')
            update_fields = fields
        super().save(*args, update_fields=update_fields, **kwargs)

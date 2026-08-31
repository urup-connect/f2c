"""The plant. Block 3, and the spine of the whole product.

Everything the club actually sells is a row in this table: a member buys a
serialised plant with a grow service attached, owns it while a cultivator grows
it, may swap it before harvest, and takes delivery of a finished product when it
is harvested. `design/plan.md` Block 3 lists what it has to carry;
`twp-tasks/cultivator-stock-upload.md` and `twp-tasks/plant-id-numbers.md` are
the briefs.

Four decisions here are worth reading before the code.

**A plant points at a listing, not at a cultivator and a strain.**
``strains.CultivatorStrainListing`` *is* the (cultivator, strain) pair -- it
carries a unique constraint saying so -- and pointing at it rather than at both
halves means the two can never disagree about who is growing what. It also
resolves C18 for free: the platform defines the finished product type catalogue,
the listing selects a subset, and this inherits from its listing through a
property with no per-plant override. That is the recommendation in
``conflict.md`` exactly.

**The serial is short, sequential and readable, and it is not the primary key.**
The primary key is a UUIDv7 like everything else in this project. But
``plant-id-numbers.md`` puts the serial on a certificate of ownership handed to
a member, and gives the administrator "trace serials and batches" -- a UUID is
neither readable on paper nor typeable into a search box under pressure. So
there are two identifiers doing two jobs, which is the same split
``payments.Subscription`` makes between its key and its checkout token.

**Ownership is a column and a history, and the history is the record.**
``owner`` answers "who holds this now" for every browse and inventory query;
``PlantOwnership`` is the append-only tenure log that a certificate of ownership
is evidence from. The duplication is deliberate and its risk is named in
``transfer_to``.

**The history starts at capture, not at the first sale -- C13.** *Each plant must
always have a verifiable owner*, and the farm is an owner: a cultivation tenure
held by the ``Producer`` is opened by ``save`` when the row is created, and the
first transfer closes it. So the trail runs farm → buyer → whoever it was swapped
to, with no gap at the front and nothing to reconstruct from a listing. ``owner``
stays null while the farm holds it -- the column answers *which member*, and
``available()`` stays a one-column filter -- so ``holder`` is what a screen
asking "who has this" should read.

**The leaf rating is stored, not computed on read.** It is a pure function of
the grow price, so a property would be the obvious choice -- but Block 10 has to
*match* plants of equal swap value, and a Python property cannot appear in a
``WHERE`` clause. So it is derived on write, like every other denormalised
column in this project. Section 8.2 of ``design/backend.md`` sets out what that
costs and what is owed in return.

**What is deliberately not here.** No price history and no promotion: that is
Block 4, and both are properties of a price *change over time* rather than of a
plant. No cart, order or allocation: Block 5. No swap: Block 10 -- ungated
since C7, though the four-plant holding check that block depends on *is* here,
because ``transfer_to`` is the only place ownership is written. And **no status
for a plant that died** -- C9 is open, nobody has decided whether a crop failure
means substitution, refund or credit, and inventing a status for it here would
pre-empt that decision in the schema.
"""
import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Count, F
from django.utils import timezone

#: Prefix on every platform-allocated serial. Short, and not a word: it appears
#: on a certificate of ownership beside the cultivator's own plant ID, and the
#: two need to be told apart at a glance.
SERIAL_PREFIX = 'CC'

#: Digits the sequence is padded to. Eight is a hundred million plants, which is
#: not a number this club will reach -- the point of padding is that serials sort
#: lexicographically in the same order they were issued, so an admin list and a
#: spreadsheet export agree.
SERIAL_DIGITS = 8

#: The name of the counter row serials are drawn from. A constant because
#: `allocate_serials` and the migration that seeds the row both need it.
PLANT_SERIAL_SEQUENCE = 'plant'

#: `swap-zone.md`: "grow price divided by 1000 and rounded to nearest 0 or .5".
LEAF_RATING_DIVISOR = Decimal('1000')
LEAF_RATING_STEP = Decimal('0.5')

#: What a plant rates when the formula would round it away to nothing. Anything
#: under R250 divides to less than half a step, and a rating of 0.0 has no swap
#: value to be equivalent to -- in an equivalent-value trade it matches nothing,
#: or matches everything for free, depending on how Block 10 reads it. A price
#: that low is not expected in practice; the floor is here so that the
#: unexpected case is a plant that is merely unswappable rather than one that
#: breaks equivalence.
#:
#: 0.1 deliberately is **not** a multiple of `LEAF_RATING_STEP`. A rating below
#: swap value is then recognisable as one wherever it is read, and a R50 plant is
#: not promoted to the same 0.5 as a R250 one.
LEAF_RATING_FLOOR = Decimal('0.1')

#: The least rating that may enter the swap zone: one whole step. Enforced by
#: `PlantQuerySet.swappable` and `Plant.assert_swappable`, and not in SQL -- for
#: the same reason the rating itself carries no check constraint tying it to the
#: grow price.
SWAP_MINIMUM_LEAF_RATING = LEAF_RATING_STEP


def leaf_rating_for(grow_price):
    """Swap value, from grow price. ``swap-zone.md``, and C4.

    ``grow_price / 1000`` rounded to the nearest 0.5. The brief's five worked
    examples: R500 gives 0.5, R850 gives 1, R1,100 gives 1, R1,650 gives 1.5,
    R1,900 gives 2. All five are asserted in ``tests/test_models.py``.

    **The tie-break is a decision, not a derivation.** R1,250 gives exactly 1.25,
    equidistant between 1.0 and 1.5, and every example in the brief avoids the
    midpoint. ``todo.md`` chose round half up: it is the conventional reading and
    it favours the member offering the plant, which is the right way for a
    rounding rule in a barter system to lean.

    Computed in ``Decimal`` throughout, and that matters more than it looks. In
    binary floating point ``1.25`` is representable but ``0.85`` is not, and
    ``round()`` uses banker's rounding -- so a float implementation would put
    R1,250 at 1.0 rather than 1.5 and disagree with the brief on the one case the
    brief does not cover.

    **A price under R250 floors at 0.1 rather than rounding to zero.** The
    formula alone gives 0.0 there, and a plant with no swap value at all is not
    one the swap zone can price. :data:`LEAF_RATING_FLOOR` carries the reasoning;
    :data:`SWAP_MINIMUM_LEAF_RATING` is the threshold that keeps such a plant out
    of a swap, and :meth:`Plant.assert_swappable` is where a caller meets it.

    **This is not a reputation score.** C4 records that ``plan.md`` and
    ``todo.md`` once described the leaf rating as a rating system for
    cultivators, which is the reviews feature (five stars, Block 7) wearing this
    one's name. Nothing about a leaf rating changes when a review is left.
    """
    if grow_price is None:
        return None

    steps = (
        Decimal(grow_price) / LEAF_RATING_DIVISOR / LEAF_RATING_STEP
    ).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    rating = (steps * LEAF_RATING_STEP).quantize(Decimal('0.1'))
    # `max` rather than a branch: both sides are `Decimal` and quantized to one
    # place, so there is no float comparison hiding in here.
    return max(rating, LEAF_RATING_FLOOR)


class SerialCounter(models.Model):
    """The sequence platform serials are drawn from.

    A table rather than an ``AutoField`` because the primary key is already a
    UUID and a model may hold only one automatic column. A table rather than
    ``Max(serial) + 1`` because that is a race: two cultivators uploading at the
    same moment read the same maximum and one insert fails on the unique index,
    which during a five-hundred-row Excel upload is a failure halfway through.

    ``allocate_serials`` explains how it is read without a lock the development
    database cannot take.
    """

    name = models.CharField(primary_key=True, max_length=32)
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        verbose_name = 'serial counter'

    def __str__(self):
        return f'{self.name} → {self.next_value}'


def format_serial(number):
    """``CC-00000001``. The number as a member sees it on a certificate."""
    return f'{SERIAL_PREFIX}-{number:0{SERIAL_DIGITS}d}'


def allocate_serials(count, *, sequence=PLANT_SERIAL_SEQUENCE):
    """Reserve ``count`` consecutive serials and return them, in order.

    One call per upload rather than one per row: a batch of five hundred plants
    takes the counter once, which is both faster and the only way the serials in
    one crop come out contiguous.

    **Why an ``UPDATE`` and then a read, rather than ``select_for_update``.** The
    obvious spelling is to lock the counter row, read it, and write it back. But
    SQLite has no ``SELECT ... FOR UPDATE`` and Django raises
    ``NotSupportedError`` rather than quietly ignoring it, so that spelling
    cannot run on the database this project develops and tests against.

    An atomic ``UPDATE ... SET next_value = next_value + n`` needs no such
    feature and is race-free on both. The update takes a row lock held until
    commit, so a second transaction attempting the same thing blocks rather than
    reading a stale value; and the read that follows is inside the same
    transaction, so it sees the transaction's own write whatever the isolation
    level. On SQLite the whole database is serialised for writes anyway.
    """
    if count < 1:
        raise ValueError('A serial allocation must be for at least one plant.')

    with transaction.atomic():
        updated = SerialCounter.objects.filter(name=sequence).update(
            next_value=F('next_value') + count
        )
        if not updated:
            # The migration seeds the row. Reaching here means a database
            # somebody has emptied by hand, and creating the row silently would
            # restart the sequence at 1 and reissue serials that are already on
            # certificates.
            raise SerialCounter.DoesNotExist(
                f'The {sequence!r} serial counter row is missing. Serials '
                'cannot be issued without it, and recreating it would restart '
                'the sequence and reissue numbers that are already in members\' '
                'hands. Restore it from a backup at the correct value.'
            )
        end = SerialCounter.objects.get(name=sequence).next_value

    start = end - count
    return [format_serial(number) for number in range(start, end)]


class PlantStatus(models.TextChoices):
    """Where a plant is in its life. ``member-roles.md``, cultivator section.

    The five the brief names, in order, and the cultivator moves a plant along
    them. Lower-case machine values with separate labels, following
    ``accounts.UserStatus``.

    ``PREFLOWERING`` and ``IN_BLOOM`` are the two that matter legally: the
    Cannabis for Private Purposes Act limits an adult to four *flowering* plants,
    and C16's recommendation is that a harvested plant does not count toward it.
    :meth:`PlantQuerySet.flowering_held_by` is the one place that reading is
    expressed.
    """

    PREFLOWERING = 'preflowering', 'Preflowering'
    IN_BLOOM = 'in_bloom', 'In bloom'
    HARVESTED = 'harvested', 'Harvested'
    PROCESSED = 'processed', 'Processed'
    SHIPPED = 'shipped', 'Shipped'


#: The statuses that count toward a member's four-plant holding limit. C16, and
#: `twp-tasks/stock-holding-limit.md`.
FLOWERING_STATUSES = (PlantStatus.PREFLOWERING, PlantStatus.IN_BLOOM)

#: The statuses at or past harvest. `harvest.md`: after harvest a paying member
#: may not swap, and an actual harvest date exists from here on.
HARVESTED_STATUSES = (
    PlantStatus.HARVESTED, PlantStatus.PROCESSED, PlantStatus.SHIPPED
)

#: How many flowering plants one member may hold at once. C15, off the Cannabis
#: for Private Purposes Act through `twp-tasks/stock-holding-limit.md`.
#:
#: Since C7 this is a statutory ceiling attaching to a named adult rather than a
#: platform convention, which is why it is counted **per member and never per
#: kind of member**. C33 requires the sharing-member role to stay droppable, and
#: an owner-type branch in a holding check is precisely what would have to be
#: deleted to drop it. `accounts.services.SHARING_MEMBER_PLANT_ALLOCATION` is
#: this number, imported rather than restated, because a cultivator allocating
#: four plants to a sharing member is spending that person's own allowance.
#:
#: The other two limits in the same brief -- eight plants per household, 600g
#: dried per person and 1.2kg per household -- are **not** modelled and are not
#: going to be. C15 records them as accepted risks: the platform cannot observe
#: what a member holds off-platform, so a check here would be theatre. They are
#: stated in the club rules instead.
MEMBER_FLOWERING_PLANT_LIMIT = 4


class OwnershipReason(models.TextChoices):
    """Why a plant changed hands. Evidence, on an append-only row.

    ``CULTIVATION`` is the farm's own tenure, opened when the plant is captured
    and closed by the first transfer. It is the only reason held by a *producer*
    rather than by a person, and it is what makes "every plant has a verifiable
    owner" true of the ledger rather than only of the sale -- C13.
    ``ALLOCATION`` is a cultivator putting plants into a sharing member's hands
    so the swap zone is not empty -- ``platform.allocate_sharing_member_stock``.
    ``ADJUSTMENT`` is staff correcting a record, and is the one that should be
    rare enough to notice. It is also the only reason a plant may return to the
    farm under: a member-held plant that reverts is an adjustment, not a fresh
    cultivation, because the plant was not captured twice.
    """

    CULTIVATION = 'cultivation', 'Held by the cultivator'
    PURCHASE = 'purchase', 'Purchased'
    SWAP = 'swap', 'Swapped'
    ALLOCATION = 'allocation', 'Allocated to a sharing member'
    ADJUSTMENT = 'adjustment', 'Adjusted by staff'


#: The reasons a *member* holds a plant under. Every reason but the farm's own
#: tenure and the correction that can go either way -- see
#: ``PlantOwnership.tenure_reason_matches_holder``, which is the constraint this
#: exists for.
MEMBER_OWNERSHIP_REASONS = (
    OwnershipReason.PURCHASE,
    OwnershipReason.SWAP,
    OwnershipReason.ALLOCATION,
)


class Batch(models.Model):
    """An optional crop or batch, as the cultivator numbers it.

    ``cultivator-stock-upload.md`` lists "Optional: Crop / batch Number", and
    Block 4 scopes promotions by batch while Block 3 gives an administrator
    ``platform.disable_batch``. So it is a record rather than a string on the
    plant: a string could not be disabled, promoted or traced.

    Points at a user and should point at the Block 2 cultivator organisation --
    the same note :class:`Plant` carries, for the same reason.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The producer whose crop this is. Points at the organisation rather than at
    # a person, so a batch outlives the grower who keyed it in. See
    # `strains.CultivatorStrainListing.cultivator` on why the field keeps its
    # name.
    cultivator = models.ForeignKey(
        'producers.Producer',
        on_delete=models.PROTECT,
        related_name='plant_batches',
    )
    reference = models.CharField(
        max_length=50,
        help_text="Your own crop or batch number. Unique among your batches.",
    )
    notes = models.TextField(blank=True)

    # `platform.disable_batch`. A timestamp rather than a boolean, because
    # "when was this stopped" is the question asked afterwards and a boolean
    # cannot answer it. Disabling a batch does not disable its plants: a
    # cultivator who mis-numbered a crop should not thereby void stock a member
    # has bought.
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)
        verbose_name_plural = 'batches'
        constraints = [
            # One reference per cultivator, and unconditional -- two cultivators
            # numbering their crops `2026-01` is not a collision, and a partial
            # index is a shape MySQL will not build (backend.md section 8.1).
            models.UniqueConstraint(
                fields=('cultivator', 'reference'),
                name='one_batch_reference_per_cultivator',
                violation_error_message=(
                    'You already have a batch with that reference.'
                ),
            ),
        ]

    def __str__(self):
        return self.reference

    @property
    def is_disabled(self):
        return self.disabled_at is not None


class PlantQuerySet(models.QuerySet):
    """The reads Blocks 5, 6 and 10 are built on.

    These are what section 3 of ``design/backend.md`` means when it says a
    cultivator's *stock* is a queryset over this table rather than a model of its
    own. There is no quantity anywhere in this schema: stock on hand is the
    plants a cultivator holds unsold, and the four-plant limit is a count.
    """

    def live(self):
        """Plants that still exist as far as the platform is concerned."""
        return self.filter(disabled_at__isnull=True)

    def available(self):
        """Unsold and not withdrawn: what a member can actually buy."""
        return self.live().filter(owner__isnull=True)

    def available_from(self, cultivator):
        """One cultivator's stock on hand. `member-roles.md`, "adjust available
        plants"; `todo.md` Block 3, "stock on hand import and export"."""
        return self.available().filter(listing__cultivator=cultivator)

    def held_by(self, member):
        """A member's own inventory. `member-roles.md`, and C13's object-level
        rule that has nothing enforcing it yet."""
        return self.live().filter(owner=member)

    def flowering_held_by(self, member):
        """The count the four-plant statutory limit applies to.

        Preflowering and in bloom only. C16's recommendation is that a harvested
        plant does not count toward the limit -- the Act's limit is on
        *flowering* plants, and ``harvest.md`` explicitly permits a member to
        swap for a harvested one, so counting those would have two briefs
        refusing the same transaction.

        Enforced since C15, in :meth:`Plant.assert_may_be_held_by` and through
        it in :meth:`Plant.transfer_to`. This is the read the refusal counts and
        the read a screen shows a member who has to swap one out to make room.
        """
        return self.held_by(member).filter(status__in=FLOWERING_STATUSES)

    def flowering_allowance_for(self, member):
        """How many more flowering plants this member may take on. C15.

        Never negative. A member can legitimately be over the ceiling without
        the platform having allowed it -- a plant that reverts under C9's
        substitution path, or an allowance spent before a record was corrected
        -- and a screen reading "you may take on -1 plants" helps nobody. Zero
        is the answer that matters, and it is the same answer either way.
        """
        return max(
            MEMBER_FLOWERING_PLANT_LIMIT - self.flowering_held_by(member).count(),
            0,
        )

    def swappable(self):
        """Plants that may enter the swap zone.

        ``harvest.md``: "After harvest no further swapping for paying members."
        The sharing-member exception in the same document is a rule about *who*,
        not about the plant, so it belongs to Block 10 rather than here.

        Also excludes a plant priced too low to earn a whole step of leaf rating
        -- :data:`LEAF_RATING_FLOOR`. This is the query half of that rule and
        :meth:`Plant.assert_swappable` is the half a caller holding one plant
        hits; the two have to agree, and ``tests/test_leaf_rating.py`` asserts
        that they do.
        """
        return self.live().filter(
            status__in=FLOWERING_STATUSES,
            leaf_rating__gte=SWAP_MINIMUM_LEAF_RATING,
        )

    def by_planting_date(self):
        """Step 3 of ``member-plant-purchase.md``, as one query.

        "Planting/harvest dates with number of plants per date. (Not necessary to
        see each serialised plant)" -- so the member is shown an aggregate, and
        the system allocates specific serials afterwards.
        """
        return (
            self.values('planting_date', 'estimated_harvest_date')
            .annotate(plants=Count('id'))
            .order_by('estimated_harvest_date', 'planting_date')
        )


class Plant(models.Model):
    """One plant, from a cultivator's upload to a member's certificate.

    **``listing`` points at a listing whose cultivator is a user, and should
    point at a farm.** Block 2 makes the cultivator organisation the record, and
    every "their own" rule in the brief scopes to it. The note is on
    ``CultivatorStrainListing`` at length; this inherits it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    # Allocated by `allocate_serials`, never typed. `plant-id-numbers.md`: the
    # platform "will also allocate a unique serial number for each plant. These
    # ID numbers will be used for tracking ownership changes" -- so it has to
    # outlive every transfer, which is the reason ownership is a column on this
    # row rather than a different table's row pointing at a copy of it.
    serial = models.CharField(
        max_length=32,
        editable=False,
        help_text='Allocated by the platform. Appears on the certificate of '
                  'ownership.',
    )

    # The cultivator's own number for the plant, required at upload. Kept beside
    # the platform serial rather than replaced by it, because a cultivator walks
    # into a greenhouse and reads their own label off a pot.
    cultivator_plant_id = models.CharField(
        max_length=50,
        help_text='Your own identifier for this plant, as it is labelled in '
                  'your greenhouse.',
    )

    listing = models.ForeignKey(
        'strains.CultivatorStrainListing',
        on_delete=models.PROTECT,
        related_name='plants',
        help_text='Which of your strain offerings this plant is grown against. '
                  'Determines the strain, and the finished product types the '
                  'owner may choose from at harvest.',
    )

    batch = models.ForeignKey(
        Batch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='plants',
        help_text='Optional crop or batch this plant belongs to.',
    )

    # ------------------------------------------------------------------
    # Commercial terms, copied onto the row
    # ------------------------------------------------------------------

    # Required per plant by `cultivator-stock-upload.md`, and copied rather than
    # read from the listing for the reason `payments.Subscription` gives about
    # its own amount: what a member agreed to must not change because a
    # cultivator later repriced their offering. The listing's
    # `default_grow_price` is what an upload defaults *from*.
    #
    # Block 4 adds price changes on unsold inventory, a was-price for two weeks
    # after a reduction, and promotions. All three are properties of a change
    # over time and want rows of their own; nothing is put here for them.
    grow_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='What a member pays to have this plant grown, in Rand.',
    )

    # Derived from `grow_price`, and stored because Block 10 has to match plants
    # of equal swap value -- a `WHERE` clause cannot call a Python property.
    #
    # Nothing displays it until Block 10; it is a property of the plant, and
    # `swap-zone.md` is emphatic that the swap zone shows this and never Rands.
    #
    # The denormalisation risk is real and, unlike `nickname_key` or
    # `live_for_user`, it is **not** closed by a check constraint. Tying it to
    # `grow_price` in SQL needs the rounding rule expressed as a database
    # expression, and division plus ROUND behaves differently enough across
    # SQLite and MySQL -- and on decimal-versus-float arithmetic -- that a
    # constraint would risk refusing the model's own write. So `save` is the only
    # thing keeping this true, and **a price change must go through the model**.
    # `tests/test_models.py` asserts the gap rather than pretending it is closed.
    leaf_rating = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        editable=False,
        help_text='Swap value: grow price ÷ 1000, to the nearest 0.5, with a '
                  'floor of 0.1 for a price too low to earn a whole step. '
                  'Never shown alongside a Rand value.',
    )

    minimum_yield_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='The least dry weight, in grams, undertaken for this plant.',
    )

    # ------------------------------------------------------------------
    # The grow
    # ------------------------------------------------------------------

    planting_date = models.DateField()
    estimated_bloom_date = models.DateField()
    estimated_harvest_date = models.DateField()

    status = models.CharField(
        max_length=16,
        choices=PlantStatus.choices,
        default=PlantStatus.PREFLOWERING,
        db_index=True,
    )

    # `harvest.md`: "Cultivators will convert estimated harvest date to actual
    # harvest date when the plants are harvested." Both are kept -- the estimate
    # is what a member bought against and what the browse screens group by, and
    # overwriting it would erase the promise.
    harvested_on = models.DateField(null=True, blank=True, editable=False)

    # ------------------------------------------------------------------
    # Ownership
    # ------------------------------------------------------------------

    # Null means the cultivator still holds it, which is what makes
    # `available()` a one-column filter rather than a join. Written only by
    # `transfer_to`.
    #
    # **Null is not "no owner" any more -- C13.** The farm holds an open
    # cultivation tenure from the moment the plant is captured, so the owner of
    # record is always answerable; this column answers the narrower question
    # *which member*, which is the one every browse and inventory query asks.
    # `holder` is the property that answers the wider one.
    #
    # PROTECT, like every other relation to a member outside `payments`: the
    # routine answer to a departing member is erasure, which keeps the row, and
    # a hard delete must not take somebody's plants with it.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='plants',
        editable=False,
        help_text='Blank while the cultivator still holds it.',
    )

    # `platform.disable_plant`. A timestamp for the same reason as on a batch.
    disabled_at = models.DateTimeField(null=True, blank=True)

    objects = PlantQuerySet.as_manager()

    class Meta:
        ordering = ('-created_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('serial',),
                name='plant_serial_unique',
                violation_error_message=(
                    'That platform serial has already been issued.'
                ),
            ),
            # A cultivator's own numbering has to be unique among their own
            # plants, or "which plant is CC-00000042" has two answers in the
            # greenhouse. Scoped to the listing's cultivator would be the exact
            # rule; scoped to the listing is what a single foreign key can
            # express without denormalising the cultivator onto this row, and it
            # is close enough that the difference is one cultivator reusing a
            # label across two strains. Recorded rather than hidden.
            models.UniqueConstraint(
                fields=('listing', 'cultivator_plant_id'),
                name='one_cultivator_plant_id_per_listing',
                violation_error_message=(
                    'You have already used that plant ID for this strain.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=PlantStatus.values),
                name='plant_status_is_known',
                violation_error_message=(
                    'That is not a plant status this platform recognises.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(grow_price__gt=0),
                name='plant_grow_price_is_positive',
                violation_error_message='A grow price must be more than zero.',
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_yield_grams__gt=0),
                name='plant_minimum_yield_is_positive',
                violation_error_message='A minimum yield must be more than zero.',
            ),
            models.CheckConstraint(
                condition=models.Q(leaf_rating__gte=0),
                name='plant_leaf_rating_is_not_negative',
                violation_error_message='A leaf rating cannot be negative.',
            ),
            # `harvest.md` makes the actual harvest date the thing a cultivator
            # sets *when* they harvest, so the date and the status are one fact
            # recorded in two columns. Said in SQL because the harvest
            # notification in Block 6 reads the status and the certificate reads
            # the date: a plant harvested with no date, or dated without being
            # harvested, breaks one of the two silently.
            #
            # `harvested_on__isnull=False` beside the status test is not
            # redundant -- see `payments.Subscription` on why a CHECK passes when
            # its condition is unknown.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[s.value for s in HARVESTED_STATUSES],
                        harvested_on__isnull=False,
                    )
                    | (
                        ~models.Q(status__in=[s.value for s in HARVESTED_STATUSES])
                        & models.Q(harvested_on__isnull=True)
                    )
                ),
                name='harvested_plant_has_a_harvest_date',
                violation_error_message=(
                    'A harvested plant needs an actual harvest date, and an '
                    'unharvested one cannot have had one.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(
                    estimated_harvest_date__gte=models.F('planting_date')
                ),
                name='plant_harvest_follows_planting',
                violation_error_message=(
                    'A plant cannot be harvested before it was planted.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(
                    estimated_bloom_date__gte=models.F('planting_date')
                ),
                name='plant_bloom_follows_planting',
                violation_error_message=(
                    'A plant cannot flower before it was planted.'
                ),
            ),
        ]
        indexes = [
            # Step 3 of the member journey: the plants available against one
            # listing, grouped by date.
            models.Index(
                fields=('listing', 'owner', 'estimated_harvest_date'),
                name='plant_available_by_date',
            ),
            # A member's inventory, and the flowering count within it.
            models.Index(fields=('owner', 'status'), name='plant_by_owner'),
            models.Index(fields=('batch',), name='plant_by_batch'),
        ]

    def __str__(self):
        return self.serial

    def save(self, *args, update_fields=None, **kwargs):
        """Derive the leaf rating, then write.

        The same shape as ``accounts.User.save`` and
        ``payments.Subscription.save``: a column the application derives is never
        set by a caller, and a partial save that moves the source has to carry
        the derived value with it. Block 4 will reprice unsold plants, so the
        ``update_fields`` branch is not hypothetical.

        **It also opens the farm's cultivation tenure on insert -- C13.** Here
        rather than in ``services.write_plants`` because the invariant is that
        *every* plant has a verifiable owner, and the service is only the bulk
        path: the admin's add form, a management command and a test fixture
        create rows too, and an invariant three of four creation paths keep is
        not an invariant. The same argument the leaf rating makes above.

        ``bulk_create`` walks past this as it walks past the leaf rating.
        ``write_plants`` refuses to use it and says why.
        """
        self.leaf_rating = leaf_rating_for(self.grow_price)

        if update_fields is not None:
            update_fields = set(update_fields)
            if 'grow_price' in update_fields:
                update_fields.add('leaf_rating')

        # Read before the write, because `super().save()` clears it.
        #
        # `owner` is `editable=False` and written only by `transfer_to`, so on
        # insert the farm is always the holder. The `owner_id` half of the test
        # is here anyway: a fixture setting the column directly must not also get
        # a farm tenure, or the open-tenure unique index refuses the row with an
        # IntegrityError nobody could read.
        opening_a_tenure = self._state.adding and self.owner_id is None

        if not opening_a_tenure:
            # Every update -- a reprice, a status change, `transfer_to` writing
            # the owner column -- takes the plain path. No savepoint for a write
            # that touches one row.
            return super().save(*args, update_fields=update_fields, **kwargs)

        with transaction.atomic():
            super().save(*args, update_fields=update_fields, **kwargs)
            PlantOwnership.objects.create(
                plant=self,
                producer_id=self.listing.cultivator_id,
                acquired_at=timezone.now(),
                reason=OwnershipReason.CULTIVATION,
            )

    # ------------------------------------------------------------------
    # Derived, per `todo.md` Block 3
    # ------------------------------------------------------------------

    @property
    def cultivator(self):
        """Who is growing it. Read through the listing, never stored twice."""
        return self.listing.cultivator

    @property
    def strain(self):
        return self.listing.strain

    @property
    def cultivator_pseudonym(self):
        """The grower's public name, for the certificate of ownership.

        The producer's trading name and nothing else -- section 6.6 of
        ``roles-and-permissions.md``, and ``plant-id-numbers.md`` names exactly
        this on the certificate alongside the plant IDs, the planting date, the
        harvest date and the strain.

        It read a person's ``display_name`` until the listing was repointed at
        the organisation. A certificate naming whichever grower keyed the plant
        in would be wrong the day they leave; the farm is what grew it.
        """
        return self.listing.cultivator.pseudonym

    @property
    def finished_product_types(self):
        """What the owner may choose from at harvest. C18, middle level.

        Inherited from the listing with no per-plant override, which is
        ``conflict.md``'s recommendation in as many words: "the plant inherits
        from its listing and may narrow further only if a real case needs it.
        Default to no per-plant override."

        **Open, and worth deciding in Block 5 rather than later.** This reads
        live, so a cultivator who removes a product type from a listing changes
        what a member who already bought a plant may choose at harvest. The
        precedent for the answer is in ``payments.Subscription``: what a member
        agreed to is copied onto their row. The natural place to take that
        snapshot is the order, which does not exist yet.
        """
        return self.listing.finished_product_types.all()

    def days_to_bloom(self, today=None):
        """Days until the estimated bloom date, or ``None`` once in bloom.

        Not a column. It would be wrong by one every midnight, and a stored
        field that has to be recalculated daily is a scheduled job whose failure
        is invisible.
        """
        if self.status != PlantStatus.PREFLOWERING:
            return None
        return (self.estimated_bloom_date - (today or timezone.localdate())).days

    def days_to_harvest(self, today=None):
        """Days until the estimated harvest date, or ``None`` once harvested."""
        if self.status in HARVESTED_STATUSES:
            return None
        return (self.estimated_harvest_date - (today or timezone.localdate())).days

    @property
    def holder(self):
        """Who owns it now: a ``User`` while a member holds it, else the farm.

        The answer to *every plant has a verifiable owner* (C13) at row level,
        and never null. Read this on a screen or a certificate; read ``owner``
        when the question is specifically *which member*.

        Derived from the columns rather than from the open tenure, deliberately:
        the tenure is the record, but a read that has already loaded the plant
        should not need a second query to name its owner. The two agree because
        ``transfer_to`` writes both in one transaction.
        """
        return self.owner if self.owner_id is not None else self.listing.cultivator

    @property
    def holder_name(self):
        """The holder's public name. A nickname or a trading name, never a legal
        name and never an email address -- C19."""
        if self.owner_id is not None:
            return self.owner.display_name
        return self.listing.cultivator.pseudonym

    @property
    def is_available(self):
        """Unsold, and not withdrawn."""
        return self.owner_id is None and self.disabled_at is None

    @property
    def is_flowering(self):
        """Whether this plant counts toward a member's four. C16."""
        return self.status in FLOWERING_STATUSES

    @property
    def is_swappable(self):
        """Whether this plant may enter the swap zone.

        The row-level twin of :meth:`PlantQuerySet.swappable`, for a plant
        already in hand. The two must agree, and a test holds them together.
        """
        return (
            self.disabled_at is None
            and self.status in FLOWERING_STATUSES
            and self.leaf_rating is not None
            and self.leaf_rating >= SWAP_MINIMUM_LEAF_RATING
        )

    def assert_swappable(self):
        """Raise unless this plant may be swapped.

        Nothing calls this yet -- the swap zone is Block 10 and gated on a legal
        opinion. It is here because *why* a plant cannot be swapped is a property
        of the plant, and the alternative is Block 10 writing three versions of
        the same check across an offer, a request and a match.

        Raises Django's ``ValidationError`` with a code, as :meth:`transfer_to`
        and :meth:`mark_harvested` do, so an API layer maps the code to a message
        rather than matching on prose.
        """
        if self.disabled_at is not None:
            raise ValidationError(
                'That plant has been withdrawn and cannot be swapped.',
                code='plant_disabled',
            )
        if self.status not in FLOWERING_STATUSES:
            raise ValidationError(
                'Only a growing plant can be swapped. That one has been '
                'harvested.',
                code='not_flowering',
            )
        if (
            self.leaf_rating is None
            or self.leaf_rating < SWAP_MINIMUM_LEAF_RATING
        ):
            raise ValidationError(
                'That plant carries no swap value: its grow price is too low '
                'to earn a whole leaf rating step.',
                code='below_swap_value',
            )

    def assert_may_be_held_by(self, member):
        """Raise unless this member has room for this plant. C15.

        The Cannabis for Private Purposes Act allows an adult four *flowering*
        plants, and C7 settled that the four attaches to the named adult rather
        than to the club -- so a member holding four may take on nothing else
        that flowers, and a sharing member's allocation spends the same
        allowance. C16 decides what counts: preflowering and in bloom, never a
        harvested plant.

        **The plant excludes itself.** A transfer of a plant the member already
        holds is not a fifth plant, and the count has to say so or a correcting
        re-transfer of the fourth plant would be refused as an overstock.

        Raises with a code, like :meth:`assert_swappable`, and the message
        carries the remedy ``stock-holding-limit.md`` asks for: swap a flowering
        plant out for a pre-flowering one. Block 10 turns that into a prompt;
        the sentence is here so the refusal is never a bare "no" even before the
        screen exists.
        """
        if not self.is_flowering:
            return
        held = (
            type(self)
            .objects.flowering_held_by(member)
            .exclude(pk=self.pk)
            .count()
        )
        if held >= MEMBER_FLOWERING_PLANT_LIMIT:
            raise ValidationError(
                f'That member already holds {MEMBER_FLOWERING_PLANT_LIMIT} '
                'flowering plants, which is the legal limit for one adult. '
                'They can swap a flowering plant for a pre-flowering one to '
                'make room.',
                code='holding_limit_reached',
            )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    @transaction.atomic
    def transfer_to(self, member, *, reason, at=None):
        """Move the plant to a member, and record the tenure it ends.

        The only way ``owner`` is written. Closes the open
        :class:`PlantOwnership` row, opens a new one, and updates the column --
        all three in one transaction, because a certificate of ownership is
        evidence and evidence with a gap in it is not evidence.

        Since C13 there is always an open row to close: the first transfer ends
        the farm's cultivation tenure, and the trail runs unbroken from capture.
        The ``filter(...).update(...)`` below needed no change for that, which is
        the argument for having written it against "the open tenure" rather than
        against "the previous member".

        **The four-plant ceiling is enforced here** -- C15 -- because this is the
        only place ``owner`` is written, and a plant's status never moves
        *backwards* into flowering, so acquiring one is the only way a member's
        count can rise. The check is a count in Python and not a constraint: SQL
        cannot express "at most four rows matching a predicate per owner", and
        two concurrent transfers to a member holding three could therefore both
        pass and leave five. That race is worth naming and not worth a table
        lock -- a member acquires plants one deliberate purchase or swap at a
        time, and the correction is an ``ADJUSTMENT`` tenure rather than a
        prosecution.

        **The gap this leaves, named.** ``owner`` is a denormalised copy of the
        open tenure's owner, and no check constraint can compare columns in two
        tables (the same limitation ``strains`` records for exclusivity). So this
        method is the only thing keeping them in step, and a queryset
        ``.update(owner=...)`` walks past it. What *is* enforced in SQL is the
        half that can be: ``PlantOwnership`` may hold at most one open tenure per
        plant. Block 2's object-level permission work should put this behind a
        service, as ``accounts.services`` does for sharing members.
        """
        if self.disabled_at is not None:
            raise ValidationError(
                'That plant has been withdrawn and cannot change hands.',
                code='plant_disabled',
            )
        if member is None:
            raise ValidationError(
                'A plant is transferred to a member, not to nobody. To take it '
                'off sale, disable it.',
                code='no_member',
            )
        if self.owner_id == member.pk:
            raise ValidationError(
                'That member already holds this plant.', code='already_owner'
            )
        self.assert_may_be_held_by(member)

        at = at or timezone.now()

        self.ownerships.filter(released_at__isnull=True).update(
            released_at=at, current_for_plant=None
        )
        tenure = PlantOwnership.objects.create(
            plant=self, owner=member, acquired_at=at, reason=reason
        )

        self.owner = member
        self.save(update_fields=['owner', 'updated_at'])
        return tenure

    @transaction.atomic
    def mark_harvested(self, on, *, status=PlantStatus.HARVESTED):
        """Convert the estimated harvest date to an actual one.

        ``harvest.md``, first line. The estimate is kept: it is what the member
        bought against and what the browse screens group by.

        The notification this should trigger -- "the owner should receive a
        notification to finalise their transaction: final product type choice,
        courier booking and fee" -- is Block 8, and Block 6 depends on it. There
        is deliberately no half-built hook here.
        """
        if status not in HARVESTED_STATUSES:
            raise ValidationError(
                f'{status} is not a harvested status.', code='not_harvested'
            )
        if on < self.planting_date:
            raise ValidationError(
                'A plant cannot be harvested before it was planted.',
                code='harvest_before_planting',
            )

        self.harvested_on = on
        self.status = status
        self.save(update_fields=['harvested_on', 'status', 'updated_at'])

    def disable(self, at=None):
        """Withdraw the plant. ``platform.disable_plant``.

        Never a delete. A plant that has been owned is referenced by an
        ownership history and, once Block 6 exists, by a certificate -- and
        ``PlantOwnership.plant`` is ``PROTECT`` so the database refuses anyway.
        """
        self.disabled_at = at or timezone.now()
        self.save(update_fields=['disabled_at', 'updated_at'])


class PlantOwnership(models.Model):
    """One tenure: somebody held this plant from here to there.

    ``todo.md`` Block 3: "Ownership, and an ownership history that survives every
    transfer." Append-only. A row is written when a plant changes hands and
    closed when it changes hands again; nothing is ever edited, because this is
    what a certificate of ownership is evidence from and a row staff can retype
    is not evidence of anything. That is the argument
    ``documents.DocumentConsent`` makes about a member ticking a box.

    **The cultivator's own holding is a tenure here, and it used to not be --
    C13.** This class previously said the history starts at the first transfer,
    on the argument that "who has this belonged to" should read as a list of
    members rather than one beginning with the grower. The rule it now answers
    to is stricter: *each plant must always have a verifiable owner, and there
    must be an audit trail of all ownership until final ownership*. A trail that
    starts at the sale cannot say who held the plant the day before it, and "the
    farm did, by implication, because the listing says so" is an inference from
    another table rather than a record. So the farm gets a row like everybody
    else, ``Plant.save`` opens it at capture, and the first transfer closes it.

    What that costs: one row per plant that would not otherwise exist, and a
    holder that is sometimes an organisation and sometimes a person. The second
    is why there are two nullable holder columns and a constraint over them,
    rather than a single foreign key to a user with a farm-owned service account
    standing in for the farm -- an account nobody signs into, holding stock, is a
    thing the club's own permission rules would then have to exclude everywhere.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    plant = models.ForeignKey(
        Plant, on_delete=models.PROTECT, related_name='ownerships'
    )
    # **Exactly one of `owner` and `producer` is set** --
    # `tenure_has_one_holder` below, and `holder` is the property to read rather
    # than either column. Nullable since C13 for the farm's own tenure; every
    # member tenure still carries a person here, and `tenure_by_owner` is
    # unchanged, so "my inventory" and "everything this member has ever held"
    # read exactly as they did.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='plant_ownerships',
    )
    # The farm, while the farm holds it. A string reference for the same reason
    # `membership.ClubMembership.registered_by` uses one: the club vertical must
    # not import the commerce side at module load.
    #
    # PROTECT, like every other holder relation: a producer with tenures in the
    # ledger cannot be deleted out from under a certificate. Deactivating a farm
    # is `Producer.is_published`, and the plants it grew keep pointing at it.
    producer = models.ForeignKey(
        'producers.Producer',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='plant_tenures',
    )

    acquired_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=16, choices=OwnershipReason.choices)

    # The plant this row is the *current* tenure for, and null once it is
    # closed. Exactly the `payments.Subscription.live_for_user` device, and for
    # exactly the same reason: "at most one open tenure per plant" is naturally a
    # partial unique index, which MySQL builds at no version and Django omits in
    # silence. Nulls are distinct under a unique index on every backend, so any
    # number of closed tenures may sit against one plant while only one open one
    # can. `design/backend.md` section 8.2.
    current_for_plant = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ('-acquired_at',)
        verbose_name = 'plant ownership'
        verbose_name_plural = 'plant ownership history'
        constraints = [
            models.UniqueConstraint(
                fields=('current_for_plant',),
                name='one_open_tenure_per_plant',
                violation_error_message=(
                    'That plant already has an open ownership record.'
                ),
            ),
            # Keeps the index above meaning what it says. Without it a raw
            # `.update(released_at=None)` reopens a closed tenure while
            # `current_for_plant` stays null, no unique index fires, and a plant
            # has two current owners.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        released_at__isnull=True,
                        current_for_plant__isnull=False,
                        current_for_plant=models.F('plant'),
                    )
                    | models.Q(
                        released_at__isnull=False,
                        current_for_plant__isnull=True,
                    )
                ),
                name='current_for_plant_matches_released_at',
                violation_error_message=(
                    'current_for_plant is derived from released_at and cannot '
                    'be set directly.'
                ),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(released_at__isnull=True)
                    | models.Q(released_at__gte=models.F('acquired_at'))
                ),
                name='tenure_ends_after_it_starts',
                violation_error_message=(
                    'A tenure cannot end before it began.'
                ),
            ),
            # **A tenure has exactly one holder.** Two nullable foreign keys are
            # two ways to get this wrong -- a row with neither is a tenure
            # belonging to nobody, which is the gap C13 closed, and a row with
            # both is two owners of one plant at one time, which is worse than
            # none. Both null tests are explicit for the reason
            # `current_for_plant_matches_released_at` gives: a CHECK passes when
            # its condition is unknown.
            models.CheckConstraint(
                condition=(
                    models.Q(owner__isnull=False, producer__isnull=True)
                    | models.Q(owner__isnull=True, producer__isnull=False)
                ),
                name='tenure_has_one_holder',
                violation_error_message=(
                    'A tenure is held by a member or by a producer, not by '
                    'both and not by neither.'
                ),
            ),
            # The reason and the holder have to agree. A purchase held by a farm
            # or a cultivation tenure held by a member is a mis-keyed row that
            # would read as evidence, and this ledger is evidence.
            #
            # `ADJUSTMENT` is deliberately unconstrained: a staff correction
            # runs in both directions, and a member-held plant reverting to the
            # farm -- C9's substitution path, unbuilt -- is a producer tenure
            # under that reason.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        reason=OwnershipReason.CULTIVATION,
                        producer__isnull=False,
                    )
                    | models.Q(
                        reason__in=MEMBER_OWNERSHIP_REASONS,
                        owner__isnull=False,
                    )
                    | models.Q(reason=OwnershipReason.ADJUSTMENT)
                ),
                name='tenure_reason_matches_holder',
                violation_error_message=(
                    'A cultivation tenure is held by a producer and a '
                    'purchase, swap or allocation by a member.'
                ),
            ),
        ]
        indexes = [
            models.Index(fields=('plant', '-acquired_at'), name='tenure_by_plant'),
            models.Index(fields=('owner', '-acquired_at'), name='tenure_by_owner'),
            # Every plant a farm has ever held, which is the farm's own audit
            # read -- and the only way to ask it, because the cultivation tenure
            # is the one row in this table that no member appears on.
            models.Index(
                fields=('producer', '-acquired_at'), name='tenure_by_producer'
            ),
        ]

    def __str__(self):
        return f'{self.plant_id} → {self.holder_name}'

    @property
    def holder(self):
        """The ``User`` or ``Producer`` that held the plant. Never ``None`` --
        ``tenure_has_one_holder`` says so in SQL."""
        return self.owner if self.owner_id is not None else self.producer

    @property
    def holder_name(self):
        """A nickname or a trading name. Never a legal name or an email
        address -- C19, and this string reaches an export and a certificate."""
        if self.owner_id is not None:
            return self.owner.display_name
        return self.producer.pseudonym

    @property
    def is_cultivator_held(self):
        """Whether this is the farm's own tenure, before any sale."""
        return self.producer_id is not None

    def save(self, *args, update_fields=None, **kwargs):
        """Derive the open-tenure marker, then write."""
        self.current_for_plant = self.plant_id if self.released_at is None else None

        if update_fields is not None:
            update_fields = set(update_fields)
            if {'released_at', 'plant'} & update_fields:
                update_fields.add('current_for_plant')

        return super().save(*args, update_fields=update_fields, **kwargs)

    @property
    def is_open(self):
        return self.released_at is None

"""The strain catalogue, and the cultivator's offer against a strain.

Two models here, and the split between them is the whole point of this module.

``Strain`` is a **botanical fact**, curated platform-wide by an administrator.
``member-roles.md`` gives strain listings to the administrator and lets a
cultivator only *request* a new one. So nothing on ``Strain`` is a cultivator's
to vary.

``CultivatorStrainListing`` is a **commercial offer**: this grower, this strain,
at this price, yielding at least this much, in these finished product forms, with
this photograph and this description. ``member-plant-purchase.md`` describes a
member drilling down through exactly that -- strains, then "which cultivators
offer the strain with prices, average star-ratings, cultivator's short
description for the strain, minimum yield, and available finished product types"
-- and every item in that second list is a property of the offer, not of the
plant genetics.

The earlier version of this module put the yield on ``Strain`` and left the
listing as a bare join table carrying nothing but two foreign keys. That is the
mistake worth naming: with the offer's fields on the platform record, two
cultivators growing the same strain cannot state different yields, and an
administrator editing the catalogue edits a grower's commercial terms.

Three further changes from that version, each recorded because a reader will
otherwise wonder where the field went:

* ``genetic_lineage`` and ``strain_type`` held the same three choices --
  Indica, Sativa, Hybrid -- as two separate columns, free to disagree. Lineage is
  now parentage as text ("OG Kush x Durban Poison"); type is the classification.
* ``medicinal_uses`` is gone. Nothing in the brief asks for it, and "Pain
  Relief" or "Anxiety Relief" published against a cannabis product is a
  therapeutic claim, which engages the Medicines and Related Substances Act and
  the ASA code. If the club wants it, it belongs behind the same compliance
  governance as the landing-page copy, not in a choice list.
* ``cultivator_locked`` is now ``exclusive_to``. The boolean said a strain was
  locked "by the cultivator" without naming which one, so nothing could act on
  it. A nullable foreign key says both halves in one column: null is the normal
  case -- any cultivator may list against it -- and a value restricts the strain
  to that grower. A grower's own genetics stay their own, and the strain record
  itself is still administrator-curated.

**Aroma and effect are lookup tables, not choice lists.** Both were single
``CharField``s with ``choices``, so a strain could carry exactly one aroma and
exactly one effect. Real strains carry several of each, and ``member-roles.md``
has cultivators requesting additions to the club's vocabularies -- which is
runtime data by definition.

**MySQL.** QA and production run MySQL, and four things here follow from that.

1. **No partial unique indexes.** MySQL cannot express a unique index with a
   ``WHERE`` clause, and Django *silently omits* a ``UniqueConstraint`` carrying
   a ``condition`` on a backend that does not support one -- no error, no index.
   Every unique rule below is therefore unconditional. Where a rule only applies
   to some rows, it is written as a ``CheckConstraint`` instead.
2. **No expression indexes either**, before MySQL 8.0.13 and never on MariaDB,
   with the same silent-omission behaviour. So case-insensitive uniqueness on a
   name is carried by a derived ``slug`` column, which is unique on the column
   itself. ``slugify`` folds case and spacing, so "OG Kush" and "og  kush"
   collide on every backend the project might run on -- which is the point, and
   is not true of a plain unique index on ``name``, whose behaviour differs
   between MySQL's case-insensitive default collation and SQLite's
   case-sensitive one.
3. **Check constraints need MySQL 8.0.16 or later.** Before that ``CHECK`` is
   parsed and discarded.
4. **JSON columns cannot be indexed** without a generated column, so the three
   here are for display and are never filtered on. Anything the browse filters
   in Block 5 have to search has to be a column or a lookup table.
"""
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify

#: The largest a cannabinoid percentage can sensibly be. Guards a typo -- a THC
#: figure of 220 is a decimal point in the wrong place, not a strong plant.
MAX_PERCENT = Decimal('100.00')

#: What a member is shown beside a cultivator's name on the strain page. Long
#: enough for two sentences and short enough that the comparison screen in
#: `member-plant-purchase.md` stays a comparison rather than a wall of prose.
SHORT_DESCRIPTION_LENGTH = 280


def listing_image_upload_to(instance, filename):
    """``strain-listings/<listing id>/image<ext>``.

    One path per listing, overwritten in place: a cultivator replacing the
    photograph of their offer has no use for the previous one, and this follows
    ``accounts.storage.avatar_upload_to`` rather than the documents rule, where a
    published revision must never change.

    The uploaded file name is discarded. What a cultivator's phone called the
    image tells us nothing and would otherwise reach a storage path. The
    extension is kept because nothing here re-encodes the upload -- unlike
    ``accounts.avatars``, which guarantees a JPEG.

    **Open:** this writes to the default storage, which is local disk. A listing
    photograph is public catalogue imagery, so it wants a CDN-fronted container
    -- but ``documents.storage`` says in as many words that its container is for
    published club documents, and ``accounts.storage`` is deliberately private.
    A third, public store is a Block 1 leftover.
    """
    extension = (filename.rsplit('.', 1)[-1] or 'jpg').lower()[:8]
    return f'strain-listings/{instance.pk}/image.{extension}'


class StrainStatus(models.TextChoices):
    """Where a strain sits in the administrator's curation.

    Values are lower-case machine strings and the labels are separate, following
    ``accounts.UserStatus``. The earlier version stored the display text --
    ``'Active'`` -- in the column, which makes renaming a label a data
    migration.

    ``PENDING`` is the state a cultivator's request for a new strain lands in
    (``member-roles.md``: "Send requests to admin for listing of new strains").
    ``HIDDEN`` is curated and deliberately not shown; ``INACTIVE`` is retired.
    Only ``ACTIVE`` may be listed against or browsed.
    """

    PENDING = 'pending', 'Pending'
    ACTIVE = 'active', 'Active'
    HIDDEN = 'hidden', 'Hidden'
    INACTIVE = 'inactive', 'Inactive'


class StrainType(models.TextChoices):
    """The classification. Not the lineage -- see the module docstring."""

    INDICA = 'indica', 'Indica'
    SATIVA = 'sativa', 'Sativa'
    HYBRID = 'hybrid', 'Hybrid'


class GrowingEnvironment(models.TextChoices):
    INDOOR = 'indoor', 'Indoor'
    OUTDOOR = 'outdoor', 'Outdoor'
    GREENHOUSE = 'greenhouse', 'Greenhouse'


class DifficultyLevel(models.TextChoices):
    EASY = 'easy', 'Easy'
    INTERMEDIATE = 'intermediate', 'Intermediate'
    ADVANCED = 'advanced', 'Advanced'


class ListingStatus(models.TextChoices):
    """Whether a cultivator's offer is in front of members.

    ``DRAFT`` is being prepared and is invisible. ``WITHDRAWN`` is taken down
    without being deleted, because plants already sold against it point at it.
    """

    DRAFT = 'draft', 'Draft'
    LISTED = 'listed', 'Listed'
    WITHDRAWN = 'withdrawn', 'Withdrawn'


def check_offered_types(status, types):
    """The C18 subset rule, as a function both a form and a model can call.

    Returns a :class:`~django.core.exceptions.ValidationError` for
    ``finished_product_types``, or ``None``.

    It lives out here because a many-to-many is validated in two different
    places and neither can do the other's job. ``Model.clean`` cannot see the
    relation until the row exists, so on a first save it has nothing to look at;
    a ``ModelForm`` sees the submitted set in ``cleaned_data`` before anything is
    written, which is where a field error belongs. Rather than write the rule
    twice and let the two drift, both call this.

    Nothing in SQL enforces it. There is no way to say "no row in this join table
    may point at an unavailable type" without a trigger, so a ``.set()`` from a
    shell walks past it -- named here rather than left to be discovered.

    :param status: the listing's :class:`ListingStatus`.
    :param types: an iterable of ``finished_product.FinishedProductType``.
    """
    offered = list(types)

    withdrawn = sorted(t.name for t in offered if not t.is_available)
    if withdrawn:
        return ValidationError(
            'These product types are no longer offered by the platform: '
            '%(types)s.',
            code='type_not_available',
            params={'types': ', '.join(withdrawn)},
        )

    if status == ListingStatus.LISTED and not offered:
        return ValidationError(
            'A listed offer needs at least one finished product type -- it is '
            'what the member chooses from at harvest.',
            code='no_types',
        )

    return None


class SlugFromName(models.Model):
    """A named vocabulary entry whose slug is derived and is the unique key.

    Abstract. See point 2 of the module docstring for why uniqueness hangs off
    the slug rather than off ``Lower(name)``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    name = models.CharField(max_length=40)
    slug = models.SlugField(max_length=40, editable=False)
    is_available = models.BooleanField(
        default=True,
        help_text='Clear this to stop offering the term on new strains. '
                  'Existing strains keep it.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ('name',)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Derived on every write, not only on insert, so a corrected spelling
        # takes the key with it. `update_fields` is extended for the same reason
        # `accounts.User.save` extends it: a partial save must not be able to
        # change the name and leave the key behind.
        self.slug = slugify(self.name)[:40]
        if (update_fields := kwargs.get('update_fields')) is not None:
            update_fields = set(update_fields)
            if 'name' in update_fields:
                kwargs['update_fields'] = update_fields | {'slug'}
        return super().save(*args, **kwargs)


class Aroma(SlugFromName):
    """One term in the aroma vocabulary. Pungent, earthy, citrus, and so on."""

    class Meta(SlugFromName.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(
                fields=('slug',),
                name='aroma_slug_unique',
                violation_error_message='That aroma is already in the list.',
            ),
        ]


class Effect(SlugFromName):
    """One term in the effects vocabulary. Relaxing, uplifting, and so on.

    Effects as members describe them. Therapeutic claims are a different thing
    and are not modelled -- see the module docstring.
    """

    class Meta(SlugFromName.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(
                fields=('slug',),
                name='effect_slug_unique',
                violation_error_message='That effect is already in the list.',
            ),
        ]


class StrainQuerySet(models.QuerySet):
    def browsable(self):
        """Strains a member may see on the generic strain listing page.

        ``member-plant-purchase.md`` step 1. Pending, hidden and retired strains
        are not the member's business, and a listing against one of them is
        refused by ``CultivatorStrainListing.clean``.

        An exclusive strain is browsable like any other. Exclusivity restricts
        who may *offer* it, not who may see it -- a member browsing simply finds
        one cultivator behind it instead of several.
        """
        return self.filter(status=StrainStatus.ACTIVE)

    def listable_by(self, cultivator):
        """Strains this cultivator may create a listing against.

        The catalogue minus the strains reserved to somebody else. This is what
        the listing form's strain picker reads, so a grower is never offered a
        strain the save would then refuse.
        """
        return self.browsable().filter(
            models.Q(exclusive_to__isnull=True) | models.Q(exclusive_to=cultivator)
        )


class Strain(models.Model):
    """A strain, as the platform holds it. Administrator-curated, platform-wide.

    Nothing commercial belongs here. Price, minimum yield, imagery and the
    available finished product types are all properties of a cultivator's offer
    and live on :class:`CultivatorStrainListing`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    status = models.CharField(
        max_length=16, choices=StrainStatus.choices, default=StrainStatus.PENDING
    )

    # A strain is platform-wide by default and this is the one exception: set,
    # it reserves the strain to a single cultivator, and no other grower may
    # create a listing against it. Null -- the normal case -- means open to all.
    #
    # One nullable foreign key rather than a boolean beside a foreign key,
    # because the two could disagree: a `cultivator_locked` flag set with no
    # cultivator named locks a strain against everybody, and a cultivator named
    # with the flag clear does nothing at all. Here the column *is* the answer.
    #
    # It does not make the strain the cultivator's record to edit. An
    # administrator still curates the botanical facts; exclusivity governs who
    # may offer it, and `StrainQuerySet.listable_by` is how a listing form asks.
    #
    # PROTECT, for the reason `CultivatorStrainListing` gives at length: a
    # departing grower must not take a catalogue entry with them, and clearing
    # this column is what releases a strain back to the club.
    # Points at the **producer**, not at a person. It used to point at a user,
    # with a note saying it should point at a farm; exclusivity is a commercial
    # arrangement with an organisation, and it must survive the departure of
    # whichever grower negotiated it.
    #
    # A string reference rather than an import, so `strains` does not depend on
    # `cultivators` at module load.
    exclusive_to = models.ForeignKey(
        'producers.Producer',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='exclusive_strains',
        help_text='Leave blank for a strain any cultivator may offer. Set it to '
                  'reserve the strain to one producer -- their own genetics, '
                  'which nobody else may list against.',
    )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    name = models.CharField(max_length=100, help_text='The name of the strain.')

    # Derived from `name`, and the reason there is no unique index on `name`
    # itself. Also the URL segment the strain listing page needs, which is why
    # it is a slug rather than the `nickname_key`-style opaque digest
    # `accounts` uses for the same job.
    slug = models.SlugField(max_length=100, editable=False)

    strain_type = models.CharField(
        max_length=16,
        choices=StrainType.choices,
        help_text='Indica, Sativa or Hybrid.',
    )
    genetic_lineage = models.CharField(
        max_length=200,
        blank=True,
        help_text="Parentage as text, e.g. 'OG Kush x Durban Poison'. Not the "
                  'classification -- that is Strain type.',
    )
    breeder_origin = models.CharField(
        max_length=100, blank=True, help_text='The breeder or origin, if known.'
    )
    description = models.TextField(
        blank=True,
        help_text='Shown on the generic strain page. Compliance-governed copy: '
                  'describe the plant, claim nothing about what it treats.',
    )

    # ------------------------------------------------------------------
    # Chemical profile
    # ------------------------------------------------------------------
    #
    # Single typical values, as the previous version had them. **Open:** real
    # catalogues quote a range, and the brief specifies neither. If ranges are
    # wanted these become `thc_min` / `thc_max` pairs, which is a migration
    # against data an administrator has typed by hand -- so it is worth
    # deciding before the catalogue is populated rather than after.
    thc_content = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(MAX_PERCENT)],
        help_text='Typical THC, as a percentage. Blank if unknown.',
    )
    cbd_content = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(MAX_PERCENT)],
        help_text='Typical CBD, as a percentage. Blank if unknown.',
    )

    # `default=dict, blank=True` on all three. Without a default these were
    # required on every insert, and `makemigrations` would have prompted for a
    # one-off value the day they were added to a populated table.
    #
    # Never filtered on: MySQL cannot index a JSON column without a generated
    # column beside it. Display only. See point 4 of the module docstring.
    other_cannabinoids = models.JSONField(
        default=dict,
        blank=True,
        help_text='Minor cannabinoids as a JSON object, e.g. {"CBG": 0.8}. '
                  'Display only -- not searchable.',
    )
    terpene_profile = models.JSONField(
        default=dict,
        blank=True,
        help_text='Terpenes as a JSON object, e.g. {"myrcene": 0.5}. Display '
                  'only -- not searchable.',
    )
    disease_resistance = models.JSONField(
        default=dict,
        blank=True,
        help_text='Resistance to pests and diseases as a JSON object. Display '
                  'only -- not searchable.',
    )

    # ------------------------------------------------------------------
    # Sensory and effects
    # ------------------------------------------------------------------

    aromas = models.ManyToManyField(
        Aroma, blank=True, related_name='strains',
        help_text='One or more. A strain rarely has exactly one aroma.',
    )
    effects = models.ManyToManyField(
        Effect, blank=True, related_name='strains',
        help_text='One or more, as members describe them.',
    )

    # ------------------------------------------------------------------
    # Cultivation
    # ------------------------------------------------------------------
    #
    # Genetics, not commerce: how long this plant takes and what it needs is the
    # same fact whoever grows it. The *estimated* bloom and harvest dates a
    # cultivator supplies per plant are Block 3, and `flowering_time_weeks` is
    # what a sanity check on them will read.
    flowering_time_weeks = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(52)],
        help_text='Weeks in flower. Blank if unknown.',
    )
    preferred_growing_environment = models.CharField(
        max_length=16, choices=GrowingEnvironment.choices, blank=True
    )
    difficulty_level = models.CharField(
        max_length=16, choices=DifficultyLevel.choices, blank=True
    )

    objects = StrainQuerySet.as_manager()

    class Meta:
        ordering = ('name',)
        constraints = [
            # The catalogue is platform-wide, so two rows wearing one name is
            # the obvious failure -- a cultivator listing against the wrong one
            # and a member comparing offers that are not comparable. Enforced on
            # the derived slug, which folds case and spacing identically on
            # SQLite and MySQL. See point 2 of the module docstring.
            models.UniqueConstraint(
                fields=('slug',),
                name='strain_slug_unique',
                violation_error_message='A strain with that name already exists.',
            ),
            # `choices` is a form-level rule, and the failure mode without this
            # is quiet: `browsable()` filters on ACTIVE, so a strain written by
            # a data migration with a stale status simply stops appearing, with
            # nothing to explain why. Same argument as `user_role_is_known`.
            models.CheckConstraint(
                condition=models.Q(status__in=StrainStatus.values),
                name='strain_status_is_known',
                violation_error_message='That is not a strain status this platform recognises.',
            ),
            models.CheckConstraint(
                condition=models.Q(strain_type__in=StrainType.values),
                name='strain_type_is_known',
                violation_error_message='That is not a strain type this platform recognises.',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(thc_content__isnull=True)
                    | models.Q(thc_content__gte=0, thc_content__lte=MAX_PERCENT)
                ),
                name='strain_thc_is_a_percentage',
                violation_error_message='THC must be a percentage between 0 and 100.',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(cbd_content__isnull=True)
                    | models.Q(cbd_content__gte=0, cbd_content__lte=MAX_PERCENT)
                ),
                name='strain_cbd_is_a_percentage',
                violation_error_message='CBD must be a percentage between 0 and 100.',
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Derived on every write. See `SlugFromName.save` -- the same reasoning,
        # and the same `update_fields` guard.
        self.slug = slugify(self.name)[:100]
        if (update_fields := kwargs.get('update_fields')) is not None:
            update_fields = set(update_fields)
            if 'name' in update_fields:
                kwargs['update_fields'] = update_fields | {'slug'}
        return super().save(*args, **kwargs)

    @property
    def is_browsable(self):
        return self.status == StrainStatus.ACTIVE

    @property
    def is_exclusive(self):
        """Whether this strain is reserved to one cultivator."""
        return self.exclusive_to_id is not None

    def may_be_listed_by(self, cultivator):
        """Whether this cultivator is allowed to offer this strain.

        The single-object form of :meth:`StrainQuerySet.listable_by`, and what
        ``CultivatorStrainListing.clean`` asks. Compares ids rather than objects
        so it costs no query on either side.
        """
        if not self.is_browsable:
            return False
        return (
            self.exclusive_to_id is None
            or self.exclusive_to_id == getattr(cultivator, 'pk', cultivator)
        )


class CultivatorStrainListingQuerySet(models.QuerySet):
    def visible(self):
        """Offers a member may see: listed, against a browsable strain.

        Both halves are needed. Retiring a strain platform-wide must take every
        offer against it off the shelf without an administrator having to visit
        each grower's listings.
        """
        return self.filter(
            status=ListingStatus.LISTED, strain__status=StrainStatus.ACTIVE
        )


class CultivatorStrainListing(models.Model):
    """One cultivator's offer against one strain.

    The middle level of C18: the platform defines the finished product type
    catalogue, this selects the subset this grower will produce for this strain,
    and a plant inherits from here.

    Any cultivator may hold a listing against any active strain, with one
    exception: a strain carrying ``exclusive_to`` may only be listed by the
    cultivator it names. That rule has nothing enforcing it in SQL -- see
    ``clean`` -- because it spans two tables.

    **``cultivator`` points at a user, and should point at a farm.** Block 2
    makes the cultivator organisation the record -- primary cultivator, appointed
    staff, collection address -- and every "their own" rule in the brief scopes
    to it rather than to a person. Pointed there now, this column would not
    exist; pointed at a user, it becomes a migration across listings, prices and
    stock the moment Block 2 lands. It is a user because a user is the only thing
    that exists today, and this comment is the note that says so.

    ``on_delete`` is ``PROTECT`` on both keys, for the same reason
    ``accounts.User.registered_by`` is: deleting a grower must not delete the
    offers members have bought plants against. The routine answer to a
    departing cultivator is withdrawal, which keeps the row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # **Points at the producer now, and the field keeps its name.** The model's
    # own docstring said this pointed at a user and should point at a farm; it
    # does. The name stays `cultivator` because that is what the club calls a
    # farm -- renaming it to `producer` here would rename the club's own
    # vocabulary to match a table, and the club vertical is where this model
    # lives.
    #
    # A string reference rather than an import, so `strains` does not depend on
    # `cultivators` at module load.
    cultivator = models.ForeignKey(
        'producers.Producer',
        on_delete=models.PROTECT,
        related_name='strain_listings',
    )
    strain = models.ForeignKey(
        Strain, on_delete=models.PROTECT, related_name='listings'
    )

    status = models.CharField(
        max_length=16, choices=ListingStatus.choices, default=ListingStatus.DRAFT
    )

    # ------------------------------------------------------------------
    # What a member sees
    # ------------------------------------------------------------------

    # `member-plant-purchase.md`, step 2: "cultivators short description for the
    # strain". Its own field rather than a truncation of `description`, because
    # the comparison screen puts several growers side by side and a cut-off
    # sentence is not a comparison.
    short_description = models.CharField(
        max_length=SHORT_DESCRIPTION_LENGTH,
        blank=True,
        help_text='One or two sentences, shown beside your name when a member '
                  'compares cultivators offering this strain.',
    )
    description = models.TextField(
        blank=True, help_text='The fuller description on your own listing page.'
    )
    image = models.ImageField(
        upload_to=listing_image_upload_to,
        blank=True,
        help_text='Your photograph of this strain.',
    )

    # ------------------------------------------------------------------
    # Commercial terms
    # ------------------------------------------------------------------

    # The cultivator's standard asking price for growing one plant of this
    # strain. **Not the price a member pays.** `cultivator-stock-upload.md`
    # makes Grow Price a required field on each plant, so the plant's own price
    # is authoritative and this is what the upload defaults from and what a
    # listing with no stock can still advertise.
    #
    # Named `default_grow_price` rather than `price` so that the relationship
    # cannot be misread. "Grow price from" on the generic strain page is a
    # minimum over available *plants*, computed in Block 5, and is not this
    # column either.
    #
    # Block 4 adds the was-price and the promotions. Both are properties of a
    # price change over time and want their own rows; nothing is put here for
    # them now.
    default_grow_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='Your standard price, in Rand, to grow one plant of this '
                  'strain. Each plant you upload carries its own grow price; '
                  'this is what it defaults to.',
    )

    # `member-plant-purchase.md` shows this to a member choosing between
    # growers, and `cultivator-stock-upload.md` collects it per plant. Grams,
    # because that is the unit the statutory limits and the courier both use.
    minimum_yield_grams = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text='The least dry weight, in grams, you undertake to deliver '
                  'from one plant of this strain.',
    )

    # The middle level of C18. A subset of the platform catalogue, and the set a
    # plant inherits.
    #
    # A many-to-many cannot be constrained in SQL -- there is no way to say "no
    # row here may point at an unavailable type" without a trigger -- so the
    # subset rule is enforced in `clean` and has to be re-checked by whatever
    # writes the relation. That is a real gap and is named rather than papered
    # over: `.set()` from a shell bypasses it.
    finished_product_types = models.ManyToManyField(
        'finished_product.FinishedProductType',
        blank=True,
        related_name='strain_listings',
        help_text='Which forms you will deliver this strain in. A plant you '
                  'upload may offer these and no others.',
    )

    objects = CultivatorStrainListingQuerySet.as_manager()

    class Meta:
        ordering = ('strain__name', 'default_grow_price')
        verbose_name = 'cultivator strain listing'
        constraints = [
            # One offer per grower per strain. Two would mean a member choosing
            # between two prices from the same cultivator for the same plant,
            # and a stock upload with no way to tell which listing a plant
            # belongs to.
            #
            # Unconditional, deliberately: a withdrawn listing still occupies
            # the pair. Scoping this to live listings would need a partial
            # unique index, which MySQL cannot express and which Django would
            # silently drop -- see point 1 of the module docstring. A cultivator
            # returning to a strain reinstates the withdrawn row.
            models.UniqueConstraint(
                fields=('cultivator', 'strain'),
                name='one_listing_per_cultivator_and_strain',
                violation_error_message=(
                    'You already have a listing for that strain. Edit it rather '
                    'than creating a second one.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=ListingStatus.values),
                name='listing_status_is_known',
                violation_error_message='That is not a listing status this platform recognises.',
            ),
            models.CheckConstraint(
                condition=models.Q(default_grow_price__gt=0),
                name='listing_grow_price_is_positive',
                violation_error_message='A grow price must be more than zero.',
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_yield_grams__gt=0),
                name='listing_minimum_yield_is_positive',
                violation_error_message='A minimum yield must be more than zero.',
            ),
            # A listed offer is one a member reads, so it needs the sentence
            # that goes beside the grower's name on the comparison screen. Said
            # as a check rather than by making the field non-blank, because a
            # draft is allowed to be incomplete -- and as a check rather than a
            # partial index, per point 1 of the module docstring.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=ListingStatus.LISTED)
                    | ~models.Q(short_description='')
                ),
                name='listed_listing_has_a_short_description',
                violation_error_message=(
                    'A listed offer needs a short description -- it is what a '
                    'member reads beside your name.'
                ),
            ),
        ]
        indexes = [
            # Step 2 of the member journey: every cultivator offering this
            # strain. The status column is in the index because `visible()`
            # always filters on it.
            models.Index(fields=('strain', 'status'), name='listing_by_strain'),
            # A cultivator's own listings screen.
            models.Index(fields=('cultivator', 'status'), name='listing_by_cultivator'),
        ]

    def __str__(self):
        # The producer's trading name, never a person's name and never an
        # email address. Section 6.6 of `roles-and-permissions.md`, and
        # `__str__` reaches admin log entries.
        #
        # It read `display_name` off a user until the listing was repointed at
        # the organisation. `pseudonym` is the producer's equivalent and exists
        # so every caller wanting a grower's public name reads one thing.
        return f'{self.cultivator.pseudonym} - {self.strain.name}'

    def clean(self):
        """The rules a foreign key and a check constraint cannot state.

        Called by the admin and by any service that calls it. Not called by
        ``save``, by ``.update()`` or by ``ManyToManyField.set``, which is why
        everything expressible in SQL is in ``Meta.constraints`` instead and only
        these three are here.
        """
        errors = {}

        # Exclusivity, checked on every save and not only on publication: a draft
        # against another grower's reserved strain is already wrong, and finding
        # out at publication is finding out after the photograph, the price and
        # the yield have been entered.
        #
        # `Strain.exclusive_to` is a column on another table, which no check
        # constraint can reach and no unique index can express. So this is the
        # only thing enforcing it, and the gap is real: a queryset `.create()`
        # or a shell `.save()` walks past it. Anything that writes a listing
        # outside the admin has to call `full_clean` -- which is why Block 2's
        # object-level permission work should put this behind a service, as
        # `accounts.services` does for sharing members.
        if self.strain_id and self.cultivator_id:
            if self.strain.is_exclusive and self.strain.exclusive_to_id != self.cultivator_id:
                errors['strain'] = ValidationError(
                    'That strain is reserved to another cultivator, so it '
                    'cannot be listed against.',
                    code='strain_is_exclusive',
                )

        # Publication is where the strain's own status starts to matter. A draft
        # against a pending strain is allowed on purpose: a cultivator who has
        # asked an administrator to add a strain can prepare the offer while the
        # request sits in the queue, and `member-roles.md` gives them that
        # request. What they cannot do is put it in front of members first.
        if self.status == ListingStatus.LISTED and self.strain_id:
            if not self.strain.is_browsable:
                errors.setdefault('strain', ValidationError(
                    'That strain is not active, so it cannot be listed against '
                    'yet. Ask an administrator to publish it first.',
                    code='strain_not_browsable',
                ))

        # The C18 subset rule, for callers that reach the model directly.
        #
        # `_state.adding`, not `self.pk`. The primary key here is a UUID with a
        # default, so it is populated the moment the instance is constructed and
        # `if self.pk` is true of a row that does not exist yet -- which would
        # make this reject every newly created listed offer, including one whose
        # form had types selected, because the join rows are written after
        # validation. `_state.adding` is the only thing that distinguishes the
        # two, and it is why the admin validates the submitted set in its form
        # instead. Both routes go through `check_offered_types`, so the rule
        # exists once.
        if not self._state.adding:
            if error := check_offered_types(self.status, self.finished_product_types.all()):
                errors['finished_product_types'] = error

        if errors:
            raise ValidationError(errors)

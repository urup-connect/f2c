"""The catalogue of forms a harvested plant can be turned into.

This app owns a **catalogue of types**, not a saleable product. The club sells a
plant with a grow service attached; when that plant is harvested the owner
chooses what it becomes. ``product-types.md`` names two to begin with -- a
pre-roll and loose cannabis -- and says others may follow. So the list has to be
data an administrator can extend, which is why this is a model rather than a
``TextChoices`` on the plant.

The earlier version of this module modelled a finished *product*: a name, a
price, a shelf life, storage requirements and packaging details. That is a
stock-keeping unit, and the club has none. Shelf life and packaging belong to
fulfilment, which is Block 6 and does not exist; they are deliberately absent
here rather than carried forward unused.

**Where this sits in C18.** ``conflict.md`` records three documents putting the
list of available product types in three places, and settles it as three levels
narrowing in one direction:

    platform catalogue  ->  cultivator strain listing  ->  plant

This model is the first of those, and it is the only one that may invent a type.
``strains.CultivatorStrainListing.finished_product_types`` selects a subset of
it, a plant inherits from its listing, and nothing overrides per plant. The
dependency runs one way, per ``backend.md`` section 3: this app knows nothing
about strains, listings or plants, and the reverse accessors it gains are
declared over there.

**MySQL.** QA and production run MySQL, and three things about this schema are
chosen for it. ``price`` is a ``DECIMAL`` rather than a float, so money is exact
and comparisons in the browse queries are too. ``code`` is short enough that its
unique index is nowhere near InnoDB's key-length limit under ``utf8mb4``. And
the check constraint below needs **MySQL 8.0.16 or later** -- earlier versions
parse ``CHECK`` and ignore it, which would leave a negative price to be caught
by nothing at all.
"""
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

#: Free, and the default. ``product-types.md``: "Pre-rolls and loose will not
#: have a cost to start with, so nothing is due to be paid when the member makes
#: this choice." A type that costs nothing is the normal case rather than a
#: special one, so zero is the default and a price is the exception.
NO_CHARGE = Decimal('0.00')


class FinishedProductTypeQuerySet(models.QuerySet):
    """Reads the member-facing and cultivator-facing screens both need."""

    def available(self):
        """Types that may be offered on a new listing or chosen at harvest.

        Withdrawing a type is a matter of clearing ``is_available``, never of
        deleting the row -- see the field's own comment.
        """
        return self.filter(is_available=True)

    def chargeable(self):
        """Types whose choice puts something on a member's bill."""
        return self.filter(price__gt=NO_CHARGE)


class FinishedProductType(models.Model):
    """One form a harvest can be delivered in. Administrator-curated.

    Created and priced platform-wide by an administrator. A cultivator may
    *request* a new one -- ``member-roles.md`` gives them that -- but the request
    is a support ticket in Block 11, not a write to this table.
    """

    #: UUIDv7, as `plan.md` section 3 specifies for this project's primary keys.
    #: Time-ordered, so inserts land at the end of the index rather than
    #: scattering across it -- which matters more on MySQL than it did on
    #: SQLite, because InnoDB clusters the table on its primary key and a random
    #: key means page splits on every insert. The cost is that MySQL has no
    #: native UUID type, so this is stored as `char(32)` and is copied into
    #: every secondary index. Accepted: this table holds a handful of rows.
    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # The stable machine key. Application code, an Excel upload column and a
    # frontend that renders an icon per type all need to name a type without
    # depending on what it is currently called; `name` is copy and will be
    # edited. Unique on the column rather than on `Lower(code)`: a slug field
    # accepts no uppercase, so there is no case to fold, and an expression index
    # is one of the things MySQL will not do before 8.0.13 -- and never on
    # MariaDB.
    code = models.SlugField(
        max_length=32,
        help_text="Stable machine key, e.g. 'pre-roll'. Referenced in code and "
                  'in the cultivator upload template, so it is not renamed.',
    )

    name = models.CharField(
        max_length=60, help_text='What a member sees, e.g. Pre-rolls.'
    )
    description = models.TextField(
        blank=True,
        help_text='Shown to a member choosing a type at harvest. Plain '
                  'description of the form only -- no claim about what it does.',
    )

    # What choosing this type costs the member, on top of the grow price they
    # have already paid for the plant. Zero for both launch types.
    #
    # `product-types.md`: "When other types come online, it may require the
    # member to pay something based on their choice as processing will have
    # extra costs." So the column exists from the first migration, at zero,
    # rather than being added the day a priced type is introduced -- the
    # alternative is a migration against live plants at the point where a
    # harvest flow starts having to handle payment for the first time.
    #
    # This is the *current* price. Nothing here is a historical record: what a
    # member was charged belongs on the harvest transaction in Block 6, because
    # this row can be repriced afterwards.
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=NO_CHARGE,
        validators=[MinValueValidator(NO_CHARGE)],
        help_text='Processing cost to the member, in Rand. Zero means the '
                  'choice is free, which is the case for pre-rolls and loose.',
    )

    # Retirement is a flag, not a delete. A plant harvested two years ago
    # records the type its owner chose, and a certificate of ownership has to
    # stay readable; deleting the row would either cascade into that history or
    # be refused by the PROTECT on whatever points at it. So a type that is no
    # longer offered stops appearing on new listings and at harvest, and stays
    # legible everywhere it was already chosen.
    is_available = models.BooleanField(
        default=True,
        help_text='Clear this to stop offering the type. Never delete a type '
                  'that has been chosen -- the harvest records point at it.',
    )

    display_order = models.PositiveSmallIntegerField(
        default=0,
        help_text='Lower sorts first. Ties fall back to name.',
    )

    objects = FinishedProductTypeQuerySet.as_manager()

    class Meta:
        ordering = ('display_order', 'name')
        verbose_name = 'finished product type'
        constraints = [
            models.UniqueConstraint(
                fields=('code',),
                name='finished_product_type_code_unique',
                violation_error_message='Another product type already uses that code.',
            ),
            # `validators` is a form-level rule that a queryset `.update()`, a
            # data migration or raw SQL walks straight past, and a negative
            # price would read as a credit to the member at harvest. Said in
            # SQL as well, in the same spirit as the constraints on
            # `accounts.User`.
            #
            # Requires MySQL 8.0.16 or later. See the module docstring.
            models.CheckConstraint(
                condition=models.Q(price__gte=NO_CHARGE),
                name='finished_product_type_price_not_negative',
                violation_error_message='A product type cannot have a negative price.',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def requires_payment(self):
        """Whether choosing this type puts something on the member's bill.

        A property rather than a stored flag: it is a fact about ``price`` and a
        second column would be free to disagree with it. The harvest flow in
        Block 6 asks this to decide whether a choice completes on its own or
        goes to checkout.
        """
        return self.price > NO_CHARGE

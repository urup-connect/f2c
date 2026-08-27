"""The catalogue as the administrator's screens read and write it.

Written out by hand rather than generated from the models, following
``accounts.schemas`` and ``documents.schemas``: a model change must not be able
to silently alter the payload a screen depends on, and adding a column to
``Strain`` should be a decision about whether the API exposes it rather than an
automatic yes.

**Three shapes for one model, and the split is deliberate.**
``StrainRowOut`` is a list row: the eight facts a decision to open, publish or
retire a strain turns on, and nothing else. ``StrainOut`` is the record, with
the vocabularies and every offer against it. ``StrainIn`` is the submission.

The list carries no descriptions, no JSON columns and no listings, and the
reason is the retire decision: the list screen exists to be scanned, and a
catalogue of two hundred strains each carrying three free-form JSON objects and
a prose description is a payload nobody reads and a screen nobody can scan.

**Numbers cross the wire as strings.** ``thc_content``, ``cbd_content``,
``default_grow_price`` and ``minimum_yield_grams`` are ``DECIMAL`` columns, and
``Decimal`` serialises to a JSON string here rather than to a float. That is the
point: a float cannot hold ``12.35`` exactly, and money and percentages that
round on their way to a browser are money and percentages that disagree with the
database. The frontend types them as strings and never does arithmetic on one.

**A submission's aromas and effects are lists of ids, not names.** The names are
what an administrator picks from, and a payload naming them would have the API
guessing which "citrus" was meant when a term is renamed mid-edit. The ids come
straight back from ``VocabulariesOut``.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from ninja import Schema

# ----------------------------------------------------------------------
# The vocabularies
# ----------------------------------------------------------------------


class TermOut(Schema):
    """One aroma or one effect, with how many strains carry it.

    ``strain_count`` is annotated by ``services.vocabularies`` and is the field
    that makes retirement a considered act rather than a guess: a term twelve
    strains carry is not a term to withdraw casually, and a term nobody has used
    is a term somebody guessed at.

    ``slug`` is reported and never submitted. It is derived from ``name`` on
    every write and is the unique key, so a screen offering it as a field would
    let the two drift -- the same reason ``admin.AromaEffectAdmin`` keeps it out
    of the form.
    """

    id: UUID
    name: str
    slug: str
    is_available: bool
    strain_count: int = 0


class CultivatorOut(Schema):
    """One grower, as the *Reserved to* picker needs them.

    Two fields, and the second is the only name this payload carries. Section 6.6
    of ``roles-and-permissions.md`` makes ``display_name`` the rule for every
    payload, and a picker is where that rule is most easily broken -- an email
    address would make an autocomplete marginally better and would put every
    grower's address in a browser on an administrator's desk.

    No status, no role, no counts. The endpoint has already filtered to
    cultivators who have not left; anything more would be a directory, which this
    is not.
    """

    id: UUID
    display_name: str


class VocabulariesOut(Schema):
    """Both lists, in one payload. Both pickers are on one form."""

    aromas: list[TermOut]
    effects: list[TermOut]


class TermIn(Schema):
    """A new term, or a rename, or a withdrawal.

    ``is_available`` carries the withdrawal, and there is no delete: clearing it
    stops the term being offered on new strains and leaves every strain that
    already carries it untouched. See ``services`` on why the row stays.
    """

    name: str
    is_available: bool = True


# ----------------------------------------------------------------------
# Strains
# ----------------------------------------------------------------------


class StrainRowOut(Schema):
    """One strain on the administrator's list.

    ``reserved_to`` is a ``display_name``, never a legal name or an email
    address -- section 6.6 of ``roles-and-permissions.md`` makes that a property
    of every payload, and a list column is no different. ``null`` for the normal
    case, which is a strain any cultivator may offer.

    The two counts come from the query's annotations. ``listings_live`` is what
    a retirement takes off the shelf; ``listings_total`` is what stays pointing
    at the row afterwards, and the gap between them is the offers a grower has
    already withdrawn themselves.
    """

    id: UUID
    name: str
    slug: str
    status: str
    strain_type: str
    reserved_to: str | None
    listings_live: int
    listings_total: int
    updated_at: datetime

    @staticmethod
    def resolve_reserved_to(obj):
        return obj.exclusive_to.display_name if obj.exclusive_to_id else None

    @staticmethod
    def resolve_listings_live(obj):
        return getattr(obj, 'listing_live', 0)

    @staticmethod
    def resolve_listings_total(obj):
        return getattr(obj, 'listing_total', 0)


class ListingRowOut(Schema):
    """One cultivator's offer against a strain, read-only.

    Read-only is a decision rather than an omission. A listing is the grower's
    commercial terms, and an administrator curating botanical facts has no
    business editing a price in passing -- the same line
    ``admin.CultivatorStrainListingInline`` draws. What this is *for* is the
    question that has to be asked before a strain is retired or reserved: is
    anybody selling it, and does anybody own a plant grown against it.

    ``plant_count`` answers the second half. ``Plant.listing`` is ``PROTECT``,
    so a listing with plants behind it can never go away, and a strain behind
    that listing is permanent too.
    """

    id: UUID
    cultivator: str
    status: str
    default_grow_price: Decimal
    minimum_yield_grams: Decimal
    short_description: str
    finished_product_types: list[str]
    plant_count: int
    updated_at: datetime

    @staticmethod
    def resolve_cultivator(obj):
        """``display_name``, for the reason ``StrainRowOut.reserved_to`` gives."""
        return obj.cultivator.display_name

    @staticmethod
    def resolve_finished_product_types(obj):
        return [product_type.name for product_type in obj.finished_product_types.all()]

    @staticmethod
    def resolve_plant_count(obj):
        return getattr(obj, 'plant_count', 0)


class StrainOut(Schema):
    """One strain in full, as the edit screen reads it.

    ``exclusive_to`` is sent twice over, as an id and as a name, and both are
    needed: the picker is set from the id and the screen shows the name, and
    having the screen look the name up from a list it also holds would break the
    moment a reserved cultivator was not in the picker's page of results.

    ``aromas`` and ``effects`` are full terms rather than bare ids, so the screen
    can show a retired term the strain still carries -- which the picker's own
    list, being the offerable vocabulary, does not have to contain.
    """

    id: UUID
    name: str
    slug: str
    status: str
    strain_type: str
    exclusive_to: UUID | None
    reserved_to: str | None

    genetic_lineage: str
    breeder_origin: str
    description: str

    thc_content: Decimal | None
    cbd_content: Decimal | None
    other_cannabinoids: dict[str, str | float]
    terpene_profile: dict[str, str | float]
    disease_resistance: dict[str, str | float]

    aromas: list[TermOut]
    effects: list[TermOut]

    flowering_time_weeks: int | None
    preferred_growing_environment: str
    difficulty_level: str

    listings: list[ListingRowOut]

    created_at: datetime
    updated_at: datetime

    @staticmethod
    def resolve_exclusive_to(obj):
        return obj.exclusive_to_id

    @staticmethod
    def resolve_reserved_to(obj):
        return obj.exclusive_to.display_name if obj.exclusive_to_id else None


class StrainIn(Schema):
    """Everything an administrator may write about a strain.

    Every field is present on every write, and none of the blanks is optional in
    the sense of "leave it alone". This is a replace: the screen holds the whole
    record and sends the whole record, so behaviour does not depend on what a
    browser chose to omit -- the same argument ``accounts.schemas.ProfileIn``
    makes, and the failure mode here is a cleared JSON column quietly surviving
    the save that cleared it.

    Absent on purpose: ``slug``, which is derived; ``id``, ``created_at`` and
    ``updated_at``, which are the record's own; and everything commercial, which
    belongs to a cultivator's listing and is not an administrator's to set.

    ``status`` and the three choice fields are validated against their choice
    lists by ``full_clean`` in the service rather than by a ``Literal`` here.
    One place, and it is the place the check constraints agree with.
    """

    name: str
    status: str
    strain_type: str
    #: The cultivator a strain is reserved to, or ``null`` for the normal case.
    #: Validated in the service against the role, because the column is a
    #: foreign key to any account -- see ``services._validated_exclusive_to``.
    exclusive_to: UUID | None = None

    genetic_lineage: str = ''
    breeder_origin: str = ''
    description: str = ''

    #: Strings, not floats. See the module docstring -- these are ``DECIMAL``
    #: columns and a float cannot hold two decimal places exactly. Pydantic
    #: parses a JSON string into a ``Decimal`` without going through binary
    #: floating point, which is the whole reason the frontend sends one.
    thc_content: Decimal | None = None
    cbd_content: Decimal | None = None

    #: Free-form by design, bounded by the service. A value may be a number or a
    #: string, because ``{"CBG": 0.8}`` and ``{"botrytis": "good"}`` are both
    #: things these columns hold.
    other_cannabinoids: dict[str, str | float] = {}
    terpene_profile: dict[str, str | float] = {}
    disease_resistance: dict[str, str | float] = {}

    #: Ids from ``VocabulariesOut``, never names. See the module docstring.
    aromas: list[UUID] = []
    effects: list[UUID] = []

    flowering_time_weeks: int | None = None
    preferred_growing_environment: str = ''
    difficulty_level: str = ''


class StrainRetiredOut(Schema):
    """What a retirement did, and what it took down with it.

    ``listings_taken_down`` is the consequence the strain's own row does not
    show: ``CultivatorStrainListingQuerySet.visible`` filters on the strain's
    status as well as the listing's, so one retirement takes every live offer
    against the strain off the shelf at once. An administrator should be told
    that number rather than have to count it.
    """

    strain: StrainOut
    listings_taken_down: int


class RefusedOut(Schema):
    """Why a catalogue write was refused, per field where it has one.

    The same shape as ``accounts.schemas.ProfileRefusedOut``, deliberately: the
    frontend already knows how to render that, and a second refusal shape would
    be a second renderer. ``detail`` is a sentence for a caller reading the
    endpoint directly; ``fields`` is what the form marks up against each input.

    Unlike the profile form, the frontend here does **not** duplicate every rule
    -- uniqueness across the catalogue and whether an account holds the
    cultivator role are not questions a browser can answer -- so these messages
    are the primary way an administrator learns what is wrong, not a backstop
    against drift.
    """

    detail: str
    fields: dict[str, list[str]] = {}


class CatalogueFilters(Schema):
    """The three narrowings the list screen offers, all optional.

    A schema rather than three loose query parameters so that the set is
    documented in one place and the endpoint signature stays readable. Blank and
    absent mean the same thing -- unfiltered -- because a ``select`` reset to
    "any" submits an empty string.
    """

    status: str = ''
    strain_type: str = ''
    #: Matched against the name, the lineage and the breeder. Never against the
    #: JSON columns: MySQL cannot index one, and a filter that table-scans on a
    #: screen somebody types into gets slower with the catalogue.
    search: str = ''

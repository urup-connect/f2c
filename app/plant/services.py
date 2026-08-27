"""Turning a filled-in template into stock.

``spreadsheet`` reads the file and knows nothing about the database;
this decides whether what it read is true. The split means every coercion is
testable without a query and every lookup here is testable without a workbook.

Three decisions shape it.

**Nothing is written unless every row is valid.** A five-hundred-row upload that
loads four hundred and eighty and reports twenty is a cultivator who now has to
work out which four hundred and eighty, and a second upload that either
duplicates or skips. `cultivator-stock-upload.md` expects "an error report a
cultivator can act on", and the action is: fix the file, upload it again. That
only works if the file is the unit.

**The cultivator comes from the caller, never from the file.** The reason is in
``spreadsheet``'s docstring; the consequence is here, in
``_resolve_listing``: a row names a strain, and the listing is looked up as
*this* cultivator's listing for that strain. There is no path by which a
spreadsheet loads stock into somebody else's inventory.

**The C18 column confirms and never overrides.** ``conflict.md`` settles that a
plant inherits its finished product types from its listing, with no per-plant
override. But ``cultivator-stock-upload.md`` lists "Finished Product Types
Available" as an upload field, and both can be true: the column is optional, and
filling it in asserts what the cultivator expects the listing to offer. A
mismatch is an error telling them to change the listing -- which is the one place
that list is edited. Left blank, the plant inherits silently.

**Both entry points share everything but their source.**
``cultivator-stock-upload.md`` opens with "Cultivators can load individual plants
**or** batch upload multiple plants using an excel template" and then gives *one*
list of required fields for both. So there is one list here:
``upload_plants`` reads a workbook and ``capture_plant`` takes a mapping, and from
that point they are the same three checks and the same write. The alternative --
a second validator for the single-plant form -- would eventually disagree with
this one, and the half that disagreed would be whichever was used less.

**Not built here.** The stock-on-hand export, which is a read over
``Plant.objects.available_from``; and any notification, which is Block 8.
"""
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from app.finished_product.models import FinishedProductType
from app.strains.models import CultivatorStrainListing, ListingStatus

from .models import Batch, Plant, allocate_serials
from .spreadsheet import RowError, build_export, read_row, read_rows


@dataclass
class UploadReport:
    """What an upload did, or would have done.

    ``created`` is empty on a dry run and on any upload with errors, and
    ``ok`` says which of those it was -- a caller should never have to infer
    "it worked" from an empty list.
    """

    ok: bool = False
    dry_run: bool = False
    rows_read: int = 0
    created: list = field(default_factory=list)
    batches: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    @property
    def error_count(self):
        return len(self.errors)

    def summary(self):
        """One line, for a command's last word or a log."""
        if self.errors:
            return (
                f'{self.error_count} problem(s) in {self.rows_read} row(s). '
                'Nothing was loaded.'
            )
        if self.dry_run:
            return f'{self.rows_read} row(s) are valid. Nothing was loaded.'
        return f'{len(self.created)} plant(s) loaded.'


def upload_plants(cultivator, source, *, dry_run=False):
    """Load a workbook of plants for one cultivator. Returns an
    :class:`UploadReport`.

    Raises ``spreadsheet.SheetError`` when the file is the wrong shape -- a
    missing column or a workbook that is not one. That is not a row a cultivator
    can fix and it is not reported as one.
    """
    rows, errors = read_rows(source)

    # Distinct rows the reader looked at, not the ones it managed to parse. A
    # file whose single row failed coercion would otherwise be reported as
    # "1 problem in 0 rows", which reads like a bug in the report.
    rows_read = len({row['_row'] for row in rows} | {error.row for error in errors})
    report = UploadReport(dry_run=dry_run, rows_read=rows_read, errors=list(errors))

    resolved, prepare_errors = prepare_rows(cultivator, rows)
    report.errors.extend(prepare_errors)

    if report.errors:
        report.errors.sort(key=lambda error: (error.row, error.column or ''))
        return report

    if dry_run:
        report.ok = True
        return report

    created = write_plants(cultivator, resolved)

    report.ok = True
    report.created = created
    report.batches = sorted({
        plant.batch.reference for plant in created if plant.batch_id
    })
    return report


def capture_plant(cultivator, **raw):
    """Load one plant. Returns the :class:`~app.plant.models.Plant`.

    The other half of ``cultivator-stock-upload.md``: "Cultivators can load
    individual plants **or** batch upload multiple plants". The brief describes
    one list of requirements for both, so this is the same list -- literally the
    same functions. ``raw`` is a mapping keyed like ``spreadsheet.COLUMNS``,
    holding whatever the caller has: form input, JSON, or values typed at a
    shell.

    That reuse is the whole point of the shape. Two implementations of "is this a
    date" would eventually disagree, and the one that disagreed would be
    whichever was exercised less -- which is this one, until Block 9 puts an
    endpoint in front of it.

    Raises ``ValidationError`` with a dict keyed by the internal field names, so
    a form can attach each message to the field it belongs to. That is what
    ``RowError.key`` exists for.
    """
    row, errors = read_row(raw)

    resolved = []
    if row is not None:
        resolved, prepare_errors = prepare_rows(cultivator, [row])
        errors = list(errors) + list(prepare_errors)

    if errors:
        raise ValidationError({
            error.key: ValidationError(error.message, code='invalid')
            for error in errors
        })

    return write_plants(cultivator, resolved)[0]


def prepare_rows(cultivator, rows):
    """Check coerced rows against the database. Returns ``(resolved, errors)``.

    ``resolved`` is a list of ``(row, listing)`` pairs for the rows that survived;
    every row with a complaint is left out of it, because nothing is written when
    there is a complaint at all.

    Shared by both entry points above, which is what makes "the same validation"
    a fact about the code rather than a claim in a docstring.
    """
    listings = _listings_for(cultivator)
    product_types = _product_types()

    resolved = []
    errors = []
    for row in rows:
        listing, row_errors = _resolve_listing(row, listings)
        if listing is not None:
            row_errors.extend(_check_product_types(row, listing, product_types))
        errors.extend(row_errors)
        if listing is not None and not row_errors:
            resolved.append((row, listing))

    # Against the database as well as within the source. `spreadsheet` catches a
    # plant ID repeated inside one workbook; this catches one that collides with
    # stock already loaded, which is the more likely mistake -- a cultivator
    # re-uploading a file they have already used, or retyping a plant they
    # entered yesterday.
    errors.extend(_check_existing_plant_ids(resolved))
    if errors:
        # A row named in a duplicate complaint must not also be written. Recomputed
        # rather than tracked, because `_check_existing_plant_ids` reports by row
        # number and the pairs are what the caller writes from.
        blamed = {error.row for error in errors}
        resolved = [pair for pair in resolved if pair[0]['_row'] not in blamed]

    return resolved, errors


@transaction.atomic
def write_plants(cultivator, resolved):
    """Write validated rows as stock. Returns the plants, in the order given.

    The only place a plant is created, so a serial is allocated the same way and
    a batch is resolved the same way whether one plant arrived or five hundred.
    """
    batches = _batches_for(cultivator, resolved)
    # One allocation for the whole write, so the serials in a crop come out
    # contiguous. See `models.allocate_serials`.
    serials = allocate_serials(len(resolved))

    created = []
    for serial, (row, listing) in zip(serials, resolved):
        # `Plant.objects.create` one at a time rather than `bulk_create`,
        # deliberately. `bulk_create` does not call `save`, and `save` is the
        # only thing deriving the leaf rating -- which, uniquely among this
        # project's derived columns, has no check constraint to catch the
        # omission (see the field). Five hundred inserts in one transaction is a
        # cost worth paying for a column nothing else guards.
        created.append(Plant.objects.create(
            serial=serial,
            cultivator_plant_id=row['cultivator_plant_id'],
            listing=listing,
            batch=batches.get(row['batch'].casefold()) if row['batch'] else None,
            grow_price=row['grow_price'],
            minimum_yield_grams=row['minimum_yield_grams'],
            planting_date=row['planting_date'],
            estimated_bloom_date=row['estimated_bloom_date'],
            estimated_harvest_date=row['estimated_harvest_date'],
        ))
    return created


#: The scopes an export can be taken at. They are the cultivator story's own
#: two inventory screens -- "My inventory for sale" and "My member-owned
#: inventory" -- rather than an invented set of filters, and `FOR_SALE` is the
#: default because that is what "stock on hand" means.
SCOPE_FOR_SALE = 'for-sale'
SCOPE_MEMBER_OWNED = 'member-owned'
SCOPE_ALL = 'all'

SCOPES = {
    SCOPE_FOR_SALE: 'Unsold — my inventory for sale',
    SCOPE_MEMBER_OWNED: 'Sold — my member-owned inventory',
    SCOPE_ALL: 'Everything I am growing',
}


def stock_for_export(cultivator, scope=SCOPE_FOR_SALE):
    """The plants an export covers. Returns a queryset.

    ``drawio``, cultivator story v1: "Manage inventory — harvest update,
    add/remove, upload, **SOH imports and exports**". The import half is the Excel
    upload; this is the other.

    Withdrawn plants are excluded at every scope. A plant somebody disabled is
    not stock on hand, and a report that includes it overstates the farm.
    """
    if scope not in SCOPES:
        raise ValueError(
            f'{scope!r} is not a scope. Use one of: {", ".join(SCOPES)}.'
        )

    plants = Plant.objects.live().filter(listing__cultivator=cultivator)
    if scope == SCOPE_FOR_SALE:
        plants = plants.filter(owner__isnull=True)
    elif scope == SCOPE_MEMBER_OWNED:
        plants = plants.filter(owner__isnull=False)

    return (
        plants
        .select_related('listing__strain', 'listing__cultivator', 'batch', 'owner')
        .prefetch_related('listing__finished_product_types')
        .order_by('estimated_harvest_date', 'serial')
    )


def stock_rows(plants, *, today=None):
    """Flatten plants into rows of plain values for ``spreadsheet.build_export``.

    ``today`` is resolved once for the whole export rather than per row, so the
    day counts in one file are consistent with each other. A report whose first
    row was computed a second before midnight and its last a second after is a
    report with two answers in it.

    **The owner is a nickname and nothing else.** ``member-roles.md`` conceals
    members behind one, section 6.6 of ``roles-and-permissions.md`` makes that a
    property of every payload, and C19 is the open question about what a
    cultivator may see of a member at all. An export is a file that leaves the
    platform and gets forwarded, so it carries the least that is useful: the
    nickname, so a cultivator can talk about the plant, and no name, address or
    contact detail.
    """
    today = today or timezone.localdate()
    rows = []

    for plant in plants:
        days_to_harvest = plant.days_to_harvest(today=today)
        rows.append({
            'serial': plant.serial,
            'cultivator_plant_id': plant.cultivator_plant_id,
            'strain': plant.listing.strain.name,
            'batch': plant.batch.reference if plant.batch_id else '',
            'status': plant.get_status_display(),
            'leaf_rating': plant.leaf_rating,
            'grow_price': plant.grow_price,
            'minimum_yield_grams': plant.minimum_yield_grams,
            'planting_date': plant.planting_date,
            'estimated_bloom_date': plant.estimated_bloom_date,
            'estimated_harvest_date': plant.estimated_harvest_date,
            'harvested_on': plant.harvested_on,
            'days_to_bloom': plant.days_to_bloom(today=today),
            'days_to_harvest': days_to_harvest,
            # "Late items", which the cultivator story asks the inventory screen
            # for by name. A plant past its estimated harvest date and not
            # harvested is one somebody has to chase, and it is invisible in a
            # list sorted by date unless it is labelled.
            'overdue': (
                'Yes' if days_to_harvest is not None and days_to_harvest < 0
                else ''
            ),
            'finished_product_types': ', '.join(
                product.name
                for product in plant.listing.finished_product_types.all()
            ),
            'held_by': plant.owner.display_name if plant.owner_id else '',
        })

    return rows


def stock_summary(rows):
    """Counts for the export's summary sheet, from the rows already flattened."""
    by_status = Counter(row['status'] for row in rows)
    by_strain = Counter(row['strain'] for row in rows)

    return {
        'plants': len(rows),
        'grow_price_total': sum(
            (row['grow_price'] for row in rows), Decimal('0.00')
        ),
        'yield_total': sum(
            (row['minimum_yield_grams'] for row in rows), Decimal('0.00')
        ),
        'overdue': sum(1 for row in rows if row['overdue']),
        'by_status': sorted(by_status.items()),
        'by_strain': sorted(by_strain.items()),
    }


def build_stock_export(plants, *, scope_label='', held_by=None, today=None):
    """A workbook of stock. Returns an openpyxl ``Workbook``.

    Takes plants rather than a cultivator, so the same writer serves the command
    (one cultivator, one scope) and the admin action (whatever staff had
    filtered). ``held_by`` defaults to including the owner column only when some
    plant actually has an owner — an empty column reads as missing data, and a
    populated one is a POPIA decision (see :func:`stock_rows`).

    **An export is not a re-import.** Every plant in it already exists, so
    uploading one back is refused by the duplicate check, correctly — the import
    half of "SOH imports and exports" is the template, which is for stock that is
    new. The export carries the platform-generated columns the template
    deliberately has none of, which is the other half of why the two files are
    not interchangeable.
    """
    rows = stock_rows(plants, today=today)
    if held_by is None:
        held_by = any(row['held_by'] for row in rows)

    return build_export(
        rows,
        stock_summary(rows),
        scope_label=scope_label,
        held_by=held_by,
    )


def template_reference(cultivator):
    """``(strain name, product types as text)`` for this cultivator's listings.

    What ``spreadsheet.build_template`` turns into a dropdown and a Reference
    sheet. Listed offerings only: a draft listing is one a member cannot buy
    against, so loading stock into it would put plants behind a wall.
    """
    listings = (
        CultivatorStrainListing.objects
        .filter(cultivator=cultivator, status=ListingStatus.LISTED)
        .select_related('strain')
        .prefetch_related('finished_product_types')
        .order_by('strain__name')
    )
    reference = []
    for listing in listings:
        offered = ', '.join(
            product.name for product in listing.finished_product_types.all()
        )
        reference.append((listing.strain.name, offered or '— nothing set —'))
    return reference


# ----------------------------------------------------------------------
# Lookups
# ----------------------------------------------------------------------


def _listings_for(cultivator):
    """This cultivator's listed offerings, keyed by folded strain name.

    Folded, because a cultivator typing `og kush` into a column whose dropdown
    says `OG Kush` has not made a mistake worth refusing -- and the strain
    catalogue is already unique case-insensitively, so the fold cannot make two
    strains collide.
    """
    listings = (
        CultivatorStrainListing.objects
        .filter(cultivator=cultivator, status=ListingStatus.LISTED)
        .select_related('strain')
        .prefetch_related('finished_product_types')
    )
    return {listing.strain.name.casefold(): listing for listing in listings}


def _product_types():
    """Every available product type, keyed by folded code *and* folded name.

    Both, because the template's Reference sheet shows names and the codes are
    what appear in an export -- and a cultivator pasting either back in is doing
    something reasonable.
    """
    index = {}
    for product in FinishedProductType.objects.available():
        index[product.code.casefold()] = product
        index[product.name.casefold()] = product
    return index


def _resolve_listing(row, listings):
    listing = listings.get(row['strain'].casefold())
    if listing is not None:
        return listing, []

    return None, [RowError(
        row['_row'],
        'strain',
        row['strain'],
        'You have no listed offering for that strain. Check the spelling '
        'against the Reference sheet, publish the listing if it is still a '
        'draft, or ask an administrator to add the strain.',
    )]


def _check_product_types(row, listing, product_types):
    """The C18 confirmation. Blank inherits; filled in must match.

    Named values are checked to exist at all before they are checked against the
    listing, so a typo is reported as a typo rather than as a listing problem.
    """
    named = row['finished_product_types']
    if not named:
        return []

    offered = {product.pk for product in listing.finished_product_types.all()}
    errors = []
    for label in named:
        product = product_types.get(label.casefold())
        if product is None:
            errors.append(RowError(
                row['_row'],
                'finished_product_types',
                label,
                'No such finished product type is available. The Reference '
                'sheet lists what your strains will be delivered as.',
            ))
        elif product.pk not in offered:
            errors.append(RowError(
                row['_row'],
                'finished_product_types',
                label,
                f'Your {listing.strain.name} listing does not offer that. Add '
                'it to the listing first -- a plant cannot offer something its '
                'listing does not.',
            ))
    return errors


def _check_existing_plant_ids(resolved):
    """Plant IDs already used against the same listing.

    One query for the whole upload rather than one per row. The unique constraint
    would catch these too, but on the insert -- which is partway through a
    transaction, with a message naming an index rather than a row.
    """
    if not resolved:
        return []

    wanted = {}
    for row, listing in resolved:
        wanted.setdefault(listing.pk, {})[
            row['cultivator_plant_id'].casefold()
        ] = row['_row']

    errors = []
    existing = Plant.objects.filter(listing_id__in=wanted).values_list(
        'listing_id', 'cultivator_plant_id'
    )
    for listing_id, plant_id in existing:
        row_number = wanted.get(listing_id, {}).get(plant_id.casefold())
        if row_number is not None:
            errors.append(RowError(
                row_number,
                'cultivator_plant_id',
                plant_id,
                'You have already loaded a plant with that ID for this strain.',
            ))
    return errors


def _batches_for(cultivator, resolved):
    """The batches this upload needs, keyed by folded reference.

    ``get_or_create`` because a cultivator loading the second half of a crop
    names the same batch, and a second row would be a second batch with one
    reference -- which the unique constraint refuses anyway.
    """
    references = {}
    for row, _ in resolved:
        reference = row['batch']
        if reference:
            references.setdefault(reference.casefold(), reference)

    batches = {}
    for folded, reference in references.items():
        batch, _ = Batch.objects.get_or_create(
            cultivator=cultivator, reference=reference
        )
        batches[folded] = batch
    return batches

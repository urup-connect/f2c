"""Stock capture as an endpoint reads and writes it.

Written by hand rather than generated from ``Plant``, following
``strains.schemas`` and ``accounts.schemas``: adding a column to the model must
be a decision about whether the API exposes it rather than an automatic yes.

**Every submitted field is a string, and that is the whole design of
``PlantIn``.** ``spreadsheet.read_row`` already decides what a date is, what a
price is and what "more than two decimal places" means, and it does so for the
workbook and the individual capture alike -- one list of rules, because
``cultivator-stock-upload.md`` gives one list of fields for both. Typing
``grow_price`` as ``Decimal`` here would put pydantic in front of that: the
caller would get django-ninja's own 422 body for a malformed price and this
module's ``RefusedOut`` for a price with three decimals, and the screen would
need two renderers for one form. So the schema carries the payload across
unexamined and the service is the only thing that judges it.

The one exception is ``cultivator``, which is a ``UUID`` because it is not a
field a cultivator fills in -- it names the farm, it is checked against the
caller's own appointments before anything else happens, and a malformed
identifier is a broken client rather than a mistake somebody can correct on a
form.

**A plant comes back with its derived values and no ownership.** Serial, leaf
rating, pseudonym and the two day counts are what the platform added; ``owner``
is absent because a plant that has just been captured has none, and a capture
response is not the place to learn about a transfer.
"""
from datetime import date
from decimal import Decimal
from uuid import UUID

from ninja import Schema


class PlantIn(Schema):
    """One plant, as the individual-capture form submits it.

    The field names are ``spreadsheet.COLUMNS``' internal keys rather than the
    spreadsheet headings, because those keys are what ``RowError.key`` reports
    against -- so a refusal maps onto an input without the form matching on
    display text.

    ``finished_product_types`` is comma-separated and optional. C18: a plant
    inherits from its listing with no per-plant override, so filling this in
    *asserts* what the listing offers and a mismatch is an error naming the
    listing as the place to fix it. Left blank, the plant inherits silently.

    There is no ``cultivator_plant_id`` default and no ``strain`` default. The
    brief lists both as required and the service refuses a blank one; a default
    here would only move the refusal.
    """

    cultivator: UUID
    cultivator_plant_id: str = ''
    strain: str = ''
    grow_price: str = ''
    planting_date: str = ''
    estimated_bloom_date: str = ''
    estimated_harvest_date: str = ''
    minimum_yield_grams: str = ''
    finished_product_types: str = ''
    batch: str = ''


class PlantOut(Schema):
    """A plant as stored, which is not a plant as submitted.

    ``serial`` and ``leaf_rating`` were allocated and derived on the way in, and
    ``strain`` and ``cultivator`` are read through the listing rather than off
    the row -- so answering with the submission would have a screen showing the
    caller their own input and calling it a record.

    **Decimals cross the wire as strings**, for the reason
    ``strains.schemas`` gives: a float cannot hold ``950.00`` exactly, and money
    that rounds on its way to a browser is money that disagrees with the
    database. The frontend types them as strings and does no arithmetic on one.

    ``leaf_rating`` is reported and nothing displays it before Block 10 --
    ``swap-zone`` is emphatic that the swap zone shows a rating and never Rands,
    so a screen showing both beside each other would be the one thing that
    document forbids. It is here because the capture screen's confirmation is
    where a cultivator would notice a grow price they mistyped by a factor of
    ten.

    ``days_to_bloom`` and ``days_to_harvest`` are properties rather than
    columns, and are ``null`` once the plant is past that stage.
    """

    id: UUID
    serial: str
    cultivator_plant_id: str
    cultivator_pseudonym: str
    strain_name: str
    batch: str | None = None
    status: str
    grow_price: Decimal
    leaf_rating: Decimal
    minimum_yield_grams: Decimal
    planting_date: date
    estimated_bloom_date: date
    estimated_harvest_date: date
    days_to_bloom: int | None = None
    days_to_harvest: int | None = None
    finished_product_types: list[str] = []

    @staticmethod
    def resolve_strain_name(obj):
        return obj.strain.name

    @staticmethod
    def resolve_batch(obj):
        return obj.batch.reference if obj.batch_id else None

    @staticmethod
    def resolve_days_to_bloom(obj):
        return obj.days_to_bloom()

    @staticmethod
    def resolve_days_to_harvest(obj):
        return obj.days_to_harvest()

    @staticmethod
    def resolve_finished_product_types(obj):
        return [product.name for product in obj.finished_product_types]


class RowErrorOut(Schema):
    """One complaint about one field, carrying both of its audiences.

    ``row`` is the number Excel shows in its own margin and ``column`` is the
    heading somebody is looking at -- together they are the upload report a
    cultivator reads off the screen and fixes in the file. ``key`` is the
    internal field name, which is what an individual-capture form attaches the
    message to.

    Both, rather than one, for the reason ``spreadsheet.RowError`` carries both:
    a report naming only the heading would have a form matching on display text,
    and one naming only the key would have a cultivator translating.

    ``value`` is what was in the cell, as text. It is what turns "this must be a
    date" into a sentence somebody can act on without opening the file.
    """

    row: int
    key: str
    column: str
    value: str = ''
    message: str

    @staticmethod
    def resolve_value(obj):
        return '' if obj.value in (None, '') else str(obj.value)


class UploadReportOut(Schema):
    """What an upload did, or would have done, or refused to do.

    One shape for all three outcomes, deliberately: the screen has one renderer
    and branches on ``ok``, and the status code says the same thing again for a
    caller reading the endpoint directly.

    ``created`` is empty on a dry run and on any upload with errors, and ``ok``
    is what distinguishes those two -- a caller should never have to infer "it
    worked" from an empty list. That is ``services.UploadReport``'s own rule and
    this schema keeps it.

    ``summary`` is the service's sentence rather than one composed here, so the
    command line's last word and the screen's banner cannot come to differ.

    ``created`` carries serials rather than whole plants. A five-hundred-row
    upload answering with five hundred records is a payload nobody renders, and
    the serial is the one thing a cultivator writes on a label.
    """

    ok: bool
    dry_run: bool
    rows_read: int
    created: list[str] = []
    batches: list[str] = []
    errors: list[RowErrorOut] = []
    summary: str


class RefusedOut(Schema):
    """Why a capture was refused, per field where it has one.

    The same shape as ``strains.schemas.RefusedOut`` and
    ``accounts.schemas.ProfileRefusedOut``, so the frontend has one renderer for
    every refused write in the project.
    """

    detail: str
    fields: dict[str, list[str]] = {}

"""The endpoints behind loading stock: one plant, a workbook of them, and the
template a workbook is filled in on.

Three endpoints and no decisions. Every rule is in ``plant.services`` and every
permission question is in ``plant.stock``, so each function here is a
translation of an exception into a status code -- the shape ``strains.api`` and
``membership.administration_api`` already have, and the reason the authorisation
call is not in this module: a router that authorised its own callers would be
the only thing between one cultivator and another's greenhouse.

**Capture only.** There is no read, no export and no withdrawal here.
``design/todo.md`` Block 3 asks for "an endpoint for either" -- either being the
individual capture and the batch upload -- and the stock-on-hand export and the
disable actions are staff work that ``manage.py export_stock`` and the admin
already do. Adding them would mean deciding the cultivator-facing read model
ahead of Block 5, which browses the same rows for a different audience.

**The producer is a field, not the session.** It matches the management
commands, and ``plant.stock`` is what makes it safe: the identifier is checked
against the caller's own appointments before anything is read or written, so
naming somebody else's farm is a 403 rather than a load into their inventory.
When Block 9 gives a cultivator their own portal, the session supplies the
identifier and nothing else about these endpoints changes.

**Four outcomes, and each has a status code that means it.**

* **201** on a captured plant, answering with the record as stored.
* **200** on an upload that loaded, and on a dry run whose every row was valid.
* **422** on an upload with row-level complaints, carrying *the same report
  shape* as the 200 -- nothing was written, the file is what needs fixing, and
  the screen renders one payload either way.
* **400** when the file is not a template at all: a missing sheet, a renamed
  heading, a PDF. ``spreadsheet`` is emphatic that this is a different kind of
  problem from a bad row -- it is the wrong file, not something a cultivator
  fixes line by line -- and answering 422 with an empty error list would hide
  that distinction behind an empty screen.
"""
from io import BytesIO

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from ninja import File, Form, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from app.commerce.producers.models import Producer

from . import stock
from .schemas import PlantIn, PlantOut, RefusedOut, UploadReportOut
from .spreadsheet import SheetError, build_template

router = Router(tags=['stock'])

#: What Excel is served as. Stated rather than guessed: ``build_template``
#: produces an ``.xlsx`` and nothing else, so there is nothing to sniff.
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _refusal(error):
    """A ``ValidationError`` as the refusal body, per field where it has one.

    Everything ``services.capture_plant`` raises is field-keyed by construction
    -- it builds the dictionary out of ``RowError.key`` -- but ``full_clean``
    can contribute a non-field error from a check constraint, and ``detail`` is
    where that lands so it is not silently dropped.

    The same four lines as ``strains.api._refusal`` and ``accounts.api``, and a
    third copy rather than a shared helper for the same reason the second one
    is: they would have to agree about which exception types they translate, and
    they do not.
    """
    fields = getattr(error, 'message_dict', None) or {}
    return {
        'detail': ' '.join(error.messages),
        'fields': {field: list(messages) for field, messages in fields.items()},
    }


def _cultivator_or_404(cultivator_id):
    """The producer at that identifier, or a 404.

    A 404 rather than a 403, and the order matters: this runs *before*
    ``stock._authorise``, so an identifier naming nothing is "there is nothing
    at that address" and an identifier naming somebody else's farm is "you may
    not". Reversing them would tell a caller which unknown identifiers happen to
    be real farms.

    A malformed identifier is a 404 rather than a parse error, because
    ``cultivator`` arrives as a form field on the upload and as a query string
    on the template -- both of which are text, and neither of which should
    answer in a different shape from the other.
    """
    producer = None
    try:
        producer = Producer.objects.filter(pk=cultivator_id).first()
    except (ValidationError, ValueError):
        producer = None

    if producer is None:
        raise HttpError(404, 'There is no producer at that address.')
    return producer


def _report(report):
    """A ``services.UploadReport`` as the payload, with its own sentence."""
    return {
        'ok': report.ok,
        'dry_run': report.dry_run,
        'rows_read': report.rows_read,
        'created': [plant.serial for plant in report.created],
        'batches': report.batches,
        'errors': report.errors,
        'summary': report.summary(),
    }


# ----------------------------------------------------------------------
# Capture
# ----------------------------------------------------------------------


@router.post('/plants', response={201: PlantOut, 422: RefusedOut})
def capture_plant(request, payload: PlantIn):
    """Load one plant.

    The other half of ``cultivator-stock-upload.md``: "Cultivators can load
    individual plants **or** batch upload multiple plants using an excel
    template." This is the individual half, and it runs the same coercion, the
    same three database checks and the same write as the upload below --
    literally the same functions, so the two cannot come to disagree about what
    a date is.

    * **201** -- loaded. The body is the plant as stored: the serial the
      platform allocated, the leaf rating it derived, and the strain and
      pseudonym read through the listing.
    * **403** -- the caller does not hold ``platform.manage_plant_stock``, or is
      not appointed to that producer.
    * **404** -- no producer at that identifier.
    * **422** -- refused, field by field. A strain the cultivator has no listed
      offering for, a plant ID they have already used, a product type the
      listing does not offer, a price with three decimals, a date that is not
      one.

    Nothing partial: a refusal writes no plant and consumes no serial.
    """
    cultivator = _cultivator_or_404(payload.cultivator)
    raw = payload.dict(exclude={'cultivator'})

    try:
        plant = stock.capture(request.user, cultivator, **raw)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 201, plant


@router.post('/uploads', response={200: UploadReportOut, 422: UploadReportOut})
def upload_plants(
    request,
    workbook: UploadedFile = File(...),
    cultivator: str = Form(...),
    dry_run: bool = Form(False),
):
    """Load a filled-in template. Answers with a report either way.

    **Nothing is written unless every row is valid.** A five-hundred-row upload
    that loads four hundred and eighty and reports twenty is a cultivator
    working out which four hundred and eighty, and a second upload that either
    duplicates or skips. The file is the unit: fix it, upload it again.

    ``dry_run`` checks the file and writes nothing, which is what a screen
    should do on the first press so a cultivator sees the whole error report
    before anything is committed.

    A multipart POST, so ``cultivator`` and ``dry_run`` arrive as form fields
    beside the file rather than as JSON -- a body cannot be both.

    * **200** -- loaded, or a dry run whose every row was valid. ``created``
      carries the serials.
    * **400** -- not a template. A workbook with no ``Plants`` sheet, a renamed
      heading, more rows than the reader will look at, or a file that is not a
      spreadsheet. No row was examined, so there is no row report.
    * **403** -- as above.
    * **404** -- no producer at that identifier.
    * **422** -- rows were refused and nothing was loaded. The body is the same
      report shape as the 200, with ``ok`` false and ``errors`` filled in, so
      the screen has one renderer.
    """
    producer = _cultivator_or_404(cultivator)

    try:
        report = stock.upload(
            request.user, producer, workbook, dry_run=dry_run
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except SheetError as wrong_file:
        # Not 422. A missing column is not a row anybody can fix, and a refusal
        # carrying an empty error list would leave the screen showing a failure
        # with nothing under it.
        raise HttpError(400, str(wrong_file))

    return (200 if report.ok else 422), _report(report)


@router.get('/template', response=None)
def download_template(request, cultivator: str):
    """The upload template, generated for this producer.

    Generated per cultivator rather than published as one static file, because
    the useful half of a template is the part that stops a mistake: the Strain
    column is a dropdown of this farm's own listed strains, and the Reference
    sheet says what each will be delivered as. A generic template has somebody
    typing strain names from memory into a column that refuses what it does not
    recognise.

    ``response=None`` so django-ninja returns the response untouched rather than
    trying to serialise a workbook. This and ``/accounts/me/avatar`` are the two
    endpoints in the project that answer with something other than JSON.

    A producer with no listed offerings still gets a template -- an appointment
    without a published listing is a normal state and the shape is still right
    to fill in -- but its dropdown is empty, and an upload against it would
    refuse every row. That is the same warning ``manage.py plant_template``
    prints, and ``X-Strain-Count`` is where a screen reads it without parsing
    the file it has just downloaded.

    * **200** -- the workbook, as a download.
    * **403** -- as above. The template lists a farm's own offerings and what
      each is delivered as, which is their commercial position rather than a
      public document.
    * **404** -- no producer at that identifier.
    """
    producer = _cultivator_or_404(cultivator)

    try:
        reference = stock.template_for(request.user, producer)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))

    buffer = BytesIO()
    build_template(reference).save(buffer)

    response = HttpResponse(buffer.getvalue(), content_type=XLSX)
    filename = f'stock-template-{producer.pseudonym}.xlsx'.replace(' ', '-')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['X-Strain-Count'] = str(len(reference))
    return response

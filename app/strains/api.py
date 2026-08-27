"""The endpoints behind the administrator's strain catalogue screens.

Eight endpoints and no decisions. Every rule is in ``strains.services``, so each
function here is a translation of exceptions into status codes -- the shape
``accounts.api`` and ``membership.api`` already have, and the reason the
permission check is not in this module: a router that authorised its own callers
would be the only thing between a member and the catalogue, and a second caller
(a management command, a Block 11 support-ticket handler acting on a cultivator's
request) would have nothing.

**There is no DELETE in here.** ``platform.manage_strain_catalogue`` says
"create, read, update and delete", and the delete half is served by
``POST /{id}/retire``, which sets ``StrainStatus.INACTIVE``. Both foreign keys
into a strain are ``PROTECT`` -- a strain has listings behind it and those
listings have plants behind them -- so a strain the club has sold against cannot
be deleted, and an endpoint that sometimes could and sometimes could not is an
endpoint whose behaviour depends on data the caller cannot see. Retirement is
the whole answer, it is platform-wide through
``CultivatorStrainListingQuerySet.visible``, and it is reversible. The
vocabularies work the same way through ``is_available``.

**Why the two 404s are different.** An unknown strain id is a 404 because there
is nothing at the address. An unknown vocabulary segment -- anything other than
``aromas`` or ``effects`` -- is also a 404, and for the same reason rather than a
422: a path naming a list that does not exist is a path with nothing behind it,
not a malformed submission.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from ninja import Query, Router
from ninja.errors import HttpError

from . import services
from .models import Strain
from .schemas import (
    CatalogueFilters,
    CultivatorOut,
    RefusedOut,
    StrainIn,
    StrainOut,
    StrainRetiredOut,
    StrainRowOut,
    TermIn,
    TermOut,
    VocabulariesOut,
)

router = Router(tags=['catalogue'])


def _refusal(error):
    """A ``ValidationError`` as the refusal body, per field where it has one.

    Django puts field errors in ``message_dict`` and non-field ones in
    ``messages``. Everything ``strains.services`` raises is field-keyed by
    construction -- it builds the dictionary itself -- but ``full_clean`` can
    contribute a non-field error from a check constraint, and ``detail`` is where
    that lands so it is not silently dropped.

    The same shape as ``accounts.api._refusal``. Two copies of four lines rather
    than a shared helper in ``common``, because the two would have to agree
    about which exception types they translate, and they do not: this one never
    sees a ``MobileUnavailable``.
    """
    fields = getattr(error, 'message_dict', None) or {}
    return {
        'detail': ' '.join(error.messages),
        'fields': {field: list(messages) for field, messages in fields.items()},
    }


def _strain_or_404(request, strain_id):
    """One strain in full, or a 404. Authorises through the service.

    ``services.strain_detail`` asks the permission question before it reads, so
    a caller without ``manage_strain_catalogue`` gets a 403 here rather than a
    404 -- which is the right way round. Hiding the existence of a strain from
    somebody who may not manage it buys nothing: the catalogue is browsable by
    every member in Block 5.
    """
    try:
        return services.strain_detail(request.user, strain_id)
    except Strain.DoesNotExist:
        raise HttpError(404, 'There is no strain at that address.')
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))


# ----------------------------------------------------------------------
# The catalogue
# ----------------------------------------------------------------------


@router.get('/strains', response=list[StrainRowOut])
def list_strains(request, filters: Query[CatalogueFilters]):
    """The catalogue, narrowed by whatever the list screen is filtering on.

    Unpaginated, and that is a decision with a shelf life. A club's strain
    catalogue is tens of rows, the list is meant to be scanned rather than paged
    through, and the screen filters and searches server-side -- so the honest
    answer today is the whole list. When it stops being tens of rows this needs
    ``ninja.pagination`` and the screen needs a pager; the note is here so that
    is a change rather than a discovery.
    """
    try:
        return services.catalogue(
            request.user,
            status=filters.status,
            strain_type=filters.strain_type,
            search=filters.search,
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))


@router.post('/strains', response={201: StrainOut, 422: RefusedOut})
def create_strain(request, payload: StrainIn):
    """Add a strain to the catalogue.

    * **201** -- created, and the body is the record as stored rather than as
      submitted: the slug the catalogue keyed it on, the terms as they resolved,
      and an empty list of listings.
    * **403** -- the caller does not hold ``manage_strain_catalogue``.
    * **422** -- refused, field by field. A duplicate name, an ``exclusive_to``
      that is not a cultivator, a retired aroma, a THC figure over 100.

    The record is read back through ``strain_detail`` rather than echoed from
    the instance the service returned. The instance has no ``listings`` to
    prefetch and no annotations, and a screen that received one shape on create
    and another on read would need two code paths for one payload.
    """
    try:
        strain = services.create_strain(
            request.user,
            aromas=payload.aromas,
            effects=payload.effects,
            **_writable(payload),
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 201, services.strain_detail(request.user, strain.pk)


@router.get('/strains/{uuid:strain_id}', response=StrainOut)
def read_strain(request, strain_id):
    """One strain, its vocabularies, and every offer against it."""
    return _strain_or_404(request, strain_id)


@router.put('/strains/{uuid:strain_id}', response={200: StrainOut, 422: RefusedOut})
def write_strain(request, strain_id, payload: StrainIn):
    """Replace every editable field on a strain.

    A PUT carrying the whole record, matching ``StrainIn``: the screen holds
    every field and sends every field, so nothing depends on what a browser
    chose to omit. See that schema on why a patch would be worse here than it is
    on a profile.

    A refused write leaves the strain exactly as it was, including its terms --
    ``services._apply`` validates everything before it saves anything, inside one
    transaction.
    """
    strain = _strain_or_404(request, strain_id)

    try:
        services.update_strain(
            request.user,
            strain,
            aromas=payload.aromas,
            effects=payload.effects,
            **_writable(payload),
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 200, services.strain_detail(request.user, strain_id)


@router.post('/strains/{uuid:strain_id}/retire', response=StrainRetiredOut)
def retire_strain(request, strain_id):
    """Take a strain out of the catalogue. This is what stands in for a delete.

    Sets ``StrainStatus.INACTIVE``, which ``StrainQuerySet.browsable`` excludes
    -- so the strain leaves the member-facing catalogue and every live offer
    against it leaves the shelf, platform-wide, in one act. The listings
    themselves are not touched: a withdrawn listing is a grower's own decision
    and this is the club retiring the strain underneath them, so the difference
    is kept and the offers come back if the strain does.

    A POST rather than a DELETE, because nothing is deleted and a DELETE that
    left the row behind would be a lie about what happened. Reinstating is a PUT
    with ``status`` set back to ``active``, which the edit form already offers.

    Idempotent: retiring an already-retired strain answers 200 with
    ``listings_taken_down`` of zero.
    """
    strain = _strain_or_404(request, strain_id)

    try:
        _, taken_down = services.retire_strain(request.user, strain)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))

    return {
        # Re-read, so the body carries the new status and the same shape every
        # other strain response has.
        'strain': services.strain_detail(request.user, strain_id),
        'listings_taken_down': taken_down,
    }


# ----------------------------------------------------------------------
# The vocabularies
# ----------------------------------------------------------------------


@router.get('/terms', response=VocabulariesOut)
def list_terms(request):
    """Both vocabularies, each term with how many strains carry it.

    One call, because both pickers are on one form and no screen has a use for
    one list without the other.
    """
    try:
        return services.vocabularies(request.user)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))


@router.get('/cultivators', response=list[CultivatorOut])
def list_cultivators(request):
    """The growers a strain may be reserved to, for the form's picker.

    Its own endpoint rather than a field on the vocabularies payload, because the
    two answer to different things: the vocabularies are catalogue data an
    administrator edits on a screen of their own, and this is the membership.
    Folding them together would have a term being renamed invalidate a cached
    list of growers.

    Only an id and a ``display_name`` cross the wire. See ``CultivatorOut``.
    """
    try:
        return services.reservable_cultivators(request.user)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))


@router.post('/terms/{kind}', response={201: TermOut, 422: RefusedOut})
def create_term(request, kind: str, payload: TermIn):
    """Add one aroma or effect to the club's vocabulary.

    ``kind`` is ``aromas`` or ``effects``. Anything else is a 404 -- see the
    module docstring on why that is not a 422.
    """
    try:
        term = services.create_term(
            request.user, kind, name=payload.name, is_available=payload.is_available
        )
    except KeyError:
        raise HttpError(404, 'The club keeps no list by that name.')
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 201, _with_count(term)


@router.put('/terms/{kind}/{uuid:term_id}', response={200: TermOut, 422: RefusedOut})
def write_term(request, kind: str, term_id, payload: TermIn):
    """Rename a term, or withdraw it by clearing ``is_available``.

    Withdrawal is not a separate endpoint because it is not a separate act: it
    is a column on the row the rename writes, and there is no delete to
    distinguish it from. Every strain already carrying the term keeps it -- see
    ``services.update_term``.
    """
    model = services.TERM_MODELS.get(kind)
    if model is None:
        raise HttpError(404, 'The club keeps no list by that name.')

    try:
        term = services.update_term(
            request.user,
            kind,
            term_id,
            name=payload.name,
            is_available=payload.is_available,
        )
    except model.DoesNotExist:
        raise HttpError(404, 'There is no term at that address.')
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 200, _with_count(term)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

#: The two fields on ``StrainIn`` that are not columns on ``Strain``. They are
#: passed to the service by name because writing a many-to-many is a different
#: act from ``setattr`` -- see ``services._apply``.
RELATION_FIELDS = ('aromas', 'effects')


def _writable(payload):
    """A ``StrainIn`` as keyword arguments for the service.

    The relations come out because they are passed separately. Everything else
    goes through, and ``services.WRITABLE_FIELDS`` is the inner allow-list that
    refuses anything this schema grows by accident -- loudly, as a ``ValueError``
    rather than as a response body, because that would be a drift between two
    modules in this project and not something a caller did.
    """
    return {
        field: value
        for field, value in payload.dict().items()
        if field not in RELATION_FIELDS
    }


def _with_count(term):
    """A freshly written term with the count ``TermOut`` expects.

    ``services.vocabularies`` annotates ``strain_count`` in the query; a term
    just created or renamed has come back from ``save`` with no annotation, and
    the schema's default of zero would be wrong for a rename. Counted here, on
    one row, rather than re-reading the whole vocabulary to serialise one term.
    """
    term.strain_count = term.strains.count()
    return term

"""The endpoints behind the administrator's membership screens.

Six endpoints and no decisions. Every rule is in ``membership.administration``,
so each function here is a translation of exceptions into status codes -- the
shape ``strains.api``, ``accounts.api`` and ``membership.api`` already have, and
the reason the permission check is not in this module: a router that authorised
its own callers would be the only thing between a member and the register, and a
second caller would have nothing.

**A second router on the same prefix, deliberately.** ``/api/members`` already
carries the two unauthenticated sign-up endpoints in ``membership.api``. They
stay where they are: joining the club and administering the register are
different concerns with different auth, and folding them into one module would
put an ``auth=None`` endpoint two screens away from one that reads a member's
identity number. The URL is shared because the noun is -- ``/api/members`` is
where members live -- and django-ninja mounts both without either knowing about
the other.

**There is no DELETE in here, and no create either.**

*No create*, because there is exactly one route into the membership and it is
``POST /api/members/register``. An administrator typing a member in by hand
would be an account with no consent ledger behind it -- no club rules agreed to,
no annexures, no constitution -- and ``documents`` is where the club's lawful
basis for holding that person's identity number lives. A second creation path
would be a way to make that basis optional.

*No delete*, for the reason ``strains.api`` gives about strains and a stronger
one besides. Every record in the club points at a member -- who paid what, who
grew what, who agreed to which revision -- and hard deletion cascades through
all of it. The two answers are suspension, which is reversible and is here, and
erasure, which is ``User.soft_delete`` and is deliberately **not** here: it is
the POPIA route, it is irreversible, and ``design/backend.md`` section 10 makes
it an explicit action in the Django admin rather than a button beside an edit
form. An erased record still appears on this register, marked, and every write
against it is refused.

**Why the 404 is a 404 and not a 403.** An unknown member id is a 404 because
there is nothing at the address. A caller who does not hold
``platform.disable_user`` gets a 403 first, from the service, before the read --
which is the right way round: hiding the existence of an account from somebody
who may not manage it buys nothing here, because they cannot ask this router
about an id they did not already have.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from ninja import Query, Router
from ninja.errors import HttpError

from . import administration
from .schemas import (
    IdentityDisclosureIn,
    IdentityNumberOut,
    MemberIn,
    MemberOut,
    MemberRefusedOut,
    MemberRowOut,
    RegisterFilters,
)

router = Router(tags=['membership-administration'])

User = get_user_model()


def _refusal(error):
    """A ``ValidationError`` as the refusal body, per field where it has one.

    Django puts field errors in ``message_dict`` and non-field ones in
    ``messages``. Both matter here, and the balance is the other way round from
    the catalogue: ``administration`` raises field-keyed errors for the five
    editable columns and *non-field* errors for the three refusals that are
    about the record rather than the submission -- an erased account, a sharing
    member, an administrator suspending themselves. Those land in ``detail``.

    The same shape as ``strains.api._refusal`` and ``accounts.api._refusal``.
    A third copy of four lines rather than a shared helper in ``common``,
    following the note in ``strains.api``: the copies would have to agree about
    which exception types they translate, and they do not.
    """
    fields = getattr(error, 'message_dict', None) or {}
    return {
        'detail': ' '.join(error.messages),
        'fields': {field: list(messages) for field, messages in fields.items()},
    }


def _member_or_404(request, member_id):
    """One member in full, or a 404. Authorises through the service."""
    try:
        return administration.member_detail(request.user, member_id)
    except User.DoesNotExist:
        raise HttpError(404, 'There is no member at that address.')
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))


# ----------------------------------------------------------------------
# The register
# ----------------------------------------------------------------------


@router.get('', response=list[MemberRowOut])
def list_members(request, filters: Query[RegisterFilters]):
    """The membership register, narrowed by whatever the list screen is filtering on.

    Newest first, always, which is what makes ``joined_within`` the whole of the
    *recent sign-ups* view rather than a second endpoint: the register with a
    window on it already is the list of who joined lately, in the order somebody
    would want to read it.

    Unpaginated, and that is a decision with a shelf life -- see
    ``administration.register``, which says when it expires and what it needs
    then.
    """
    try:
        return administration.register(
            request.user,
            status=filters.status,
            role=filters.role,
            search=filters.search,
            joined_within=filters.joined_within,
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))


@router.get('/{uuid:member_id}', response=MemberOut)
def read_member(request, member_id):
    """One member's record, with their membership standing and disclosure history."""
    return _member_or_404(request, member_id)


@router.put(
    '/{uuid:member_id}', response={200: MemberOut, 422: MemberRefusedOut}
)
def write_member(request, member_id, payload: MemberIn):
    """Correct a member's details.

    A PUT carrying the whole record, matching ``MemberIn``: the screen holds
    every field and sends every field, so nothing depends on what a browser
    chose to omit.

    * **403** -- the caller does not hold ``platform.disable_user``.
    * **404** -- there is no member at that address.
    * **422** -- refused. Per field for the five editable columns; in ``detail``
      for the two records this screen may not write to at all, which are an
      erased account and a cultivator's sharing member.

    A refused write leaves the member exactly as they were:
    ``administration._apply`` validates everything before it assigns anything,
    inside one transaction.
    """
    member = _member_or_404(request, member_id)

    try:
        administration.update_member(
            request.user,
            member,
            first_name=payload.first_name,
            last_name=payload.last_name,
            nickname=payload.nickname,
            email=payload.email,
            mobile=payload.mobile,
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    # Re-read rather than echoed from the instance the service returned. The
    # instance carries no prefetch and no disclosure history, and a screen that
    # received one shape on save and another on read would need two code paths
    # for one payload -- the same argument `strains.api.create_strain` makes.
    return 200, administration.member_detail(request.user, member_id)


# ----------------------------------------------------------------------
# Standing
# ----------------------------------------------------------------------


@router.post(
    '/{uuid:member_id}/suspend', response={200: MemberOut, 422: MemberRefusedOut}
)
def suspend_member(request, member_id):
    """Block an account from signing in, reversibly.

    ``platform.disable_user`` -- "disable or remove any account" -- and this is
    the disable half. It moves the status to Suspended and ends every live
    session the account holds, without which an already signed-in browser would
    keep working until its cookie expired.

    A POST rather than a DELETE, because nothing is deleted. Reinstating is the
    endpoint below.

    Idempotent: suspending an already-suspended account answers 200 with the
    record unchanged.

    * **422** -- an erased account, a sharing member, or the caller's own
      account. The last is not paternalism: suspension signs the caller out on
      the way, and they cannot sign back in to undo it.
    """
    member = _member_or_404(request, member_id)

    try:
        administration.suspend_member(request.user, member)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 200, administration.member_detail(request.user, member_id)


@router.post(
    '/{uuid:member_id}/reinstate', response={200: MemberOut, 422: MemberRefusedOut}
)
def reinstate_member(request, member_id):
    """Lift a suspension, returning the account to Active.

    Only from Suspended. Nothing records where an account sat before it was
    suspended, so this cannot restore it -- and an account at Pending payment is
    not suspended, it is unpaid, which ``payments`` owns.

    Idempotent for an already-active account; a 422 for one that is neither
    active nor suspended, naming where it actually sits.
    """
    member = _member_or_404(request, member_id)

    try:
        administration.reinstate_member(request.user, member)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 200, administration.member_detail(request.user, member_id)


# ----------------------------------------------------------------------
# The identity number
# ----------------------------------------------------------------------


@router.post(
    '/{uuid:member_id}/identity-number',
    response={200: IdentityNumberOut, 422: MemberRefusedOut},
)
def disclose_identity_number(request, member_id, payload: IdentityDisclosureIn):
    """Read a member's identity number in full, recording that it happened.

    The masked form is on every record screen and costs nothing. This is the
    exception to it, and the exception is what the record in
    ``accounts.IdentityNumberDisclosure`` pays for: the row is written before
    the column is decrypted, inside the transaction the decrypt is part of, so
    the number cannot be read without the read being logged.

    **A POST, and the number is in the response body rather than a GET's URL.**
    Two reasons, and both are the reason this endpoint exists at all. A GET is
    cacheable, prefetchable and logged by every proxy between here and the
    administrator's desk; and a GET has no body to carry the reason, which is
    the field that makes the disclosure reviewable.

    * **422** -- no reason given, a reason too short to review, or no identity
      number on file for that member.
    * **500** -- deliberately, for a row that will not decrypt. The transaction
      rolls back, so no disclosure is left claiming somebody read something they
      did not. The record screen's masked field shows ``UNREADABLE`` for the same
      row, which is where an administrator meets the problem first.
    """
    member = _member_or_404(request, member_id)

    try:
        number, disclosure = administration.disclose_id_number(
            request.user, member, reason=payload.reason
        )
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    return 200, {'id_number': number, 'disclosure': disclosure}

"""The endpoint sign-up writes through, and the one it asks a question of.

``POST /api/members/register`` takes the six details and three agreements the
sign-up form collects, and leaves a member at ``Pending payment`` with a
subscription opened against them. It is unauthenticated because there is no
account until it returns.

What actually takes the money is ``app.core.payments``, and nothing in this module
knows how. All that crosses back is a checkout token -- an opaque handle the
caller turns into a Payfast redirect through ``GET /api/payments/checkout``.

What comes back is deliberately thin. A success is a status and a sentence, and
it is the *same* success whether a row was written or the submission named an
address or an identity number already on file -- see ``services`` on why a
duplicate is not disclosed. Only a nickname collision and a document that moved
on while the form was open come back as something to correct, because those are
the two the member can act on.

``POST /api/members/nickname/availability`` is the second endpoint, and it
answers one question while the form is still open: is this nickname free. It
exists because a nickname is the only collision this app discloses, so it is the
only field that can be checked ahead of the submission without the form becoming
a way to ask whether a named person is a member here. It is a courtesy and not a
gate -- ``/register`` asks again inside the transaction that writes.

Nothing here decides anything. Every rule is in ``services`` and
``common.validators``, so each endpoint is a translation of exceptions into
status codes and nothing more.
"""
from django.core.exceptions import ValidationError
from ninja import Router
from ninja.errors import HttpError

from app.core.documents import services as document_services

from . import services
from .schemas import (
    NicknameAvailabilityIn,
    NicknameAvailabilityOut,
    NicknameRejectedOut,
    RegisterIn,
    RegistrationOut,
    RegistrationRefusedOut,
)
from .throttles import NicknameAvailabilityThrottle, RegisterThrottle

router = Router(tags=['membership'])

#: What a member is told on the way out. Said here rather than in the frontend
#: as well, because the screen that shows it reads `status` from this response.
ACCEPTED_DETAIL = (
    'Your details are with the club. Your membership becomes active once '
    'payment is complete.'
)


@router.post(
    '/register',
    response={
        200: RegistrationOut,
        409: RegistrationRefusedOut,
        422: RegistrationRefusedOut,
    },
    auth=None,
    throttle=[RegisterThrottle()],
)
def register(request, payload: RegisterIn):
    """Register a member, leaving them at ``Pending payment``.

    * **200** -- accepted, carrying the ``checkout_token`` that sends the member
      to Payfast. Also the answer to a submission naming an address or an
      identity number already on file, which writes nothing and carries no
      token -- see ``RegistrationOut`` on the disclosure that costs.
    * **409** -- the nickname is taken, or a club document moved on while the
      form was open. Both name what to fix.
    * **422** -- a field is not acceptable, or the submission does not match the
      documents in force. The frontend has already refused these, so a member
      reaching one has bypassed the form.
    * **503** -- a required club document has no published revision. There is
      nothing lawful to agree to, so nobody may be recorded as having agreed.
    """
    submitted = [
        {'document': entry.document, 'version': entry.version}
        for entry in payload.consents
    ]

    try:
        registration = services.register_member(
            first_name=payload.first_name,
            last_name=payload.last_name,
            nickname=payload.nickname,
            email=payload.email,
            mobile=payload.mobile,
            id_number=payload.id_number,
            consents=submitted,
        )
    except services.NicknameTaken as refusal:
        return 409, {'detail': str(refusal), 'nickname_unavailable': True}
    except services.ConsentSuperseded as refusal:
        return 409, {
            'detail': str(refusal),
            'superseded_documents': refusal.documents,
        }
    except document_services.DocumentsNotReady as error:
        # 503 rather than 422: nothing is wrong with the submission, and the
        # member can do nothing but come back. The same code `/documents/current`
        # answers with, for the same reason.
        raise HttpError(503, str(error))
    except ValidationError as error:
        # Joined rather than returned per field. The frontend validates every
        # field itself and refuses first, so a member never reads this -- it is
        # for whoever is calling the endpoint directly.
        return 422, {'detail': ' '.join(error.messages)}

    return 200, {
        # The **membership's** status, which is what a joining member is
        # waiting on. Their account is Active from the moment it exists.
        'status': services.REGISTERED_MEMBERSHIP_STATUS,
        'detail': ACCEPTED_DETAIL,
        # Null for a duplicate submission, which writes nothing. That is the one
        # asymmetry in this response and it is documented in `RegistrationOut`;
        # the caller sends a member with a token to Payfast and everyone else to
        # the confirmation screen.
        'checkout_token': registration.checkout_token,
    }


@router.post(
    '/nickname/availability',
    response={200: NicknameAvailabilityOut, 422: NicknameRejectedOut},
    auth=None,
    throttle=[NicknameAvailabilityThrottle()],
)
def nickname_availability(request, payload: NicknameAvailabilityIn):
    """Whether a nickname is free, asked while the form is still open.

    * **200** -- ``{"available": true|false}``. False covers taken and reserved
      alike; there is nothing to do about either but choose again.
    * **422** -- the nickname is not well formed. The frontend refuses every one
      of these before asking, so reaching this means the caller bypassed the
      form or the two rule sets have drifted.
    * **429** -- the per-IP limit, from ``NicknameAvailabilityThrottle``.

    A POST, and the nickname travels in the body: a value in a query string is a
    value in every access log between here and the member.

    This is a courtesy, not a gate. ``/register`` asks the same question again
    inside the transaction that writes, because a nickname free at the moment
    the field loses focus can be taken before the form is sent -- and because an
    answer given here is an answer the caller could have chosen not to ask for.
    """
    try:
        available = services.nickname_is_available(payload.nickname)
    except ValidationError as error:
        return 422, {'detail': ' '.join(error.messages)}

    return 200, {'available': available}

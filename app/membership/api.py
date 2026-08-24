"""The one endpoint sign-up writes through.

``POST /api/members/register`` takes the six details and three agreements the
sign-up form collects, and leaves a member at ``Pending payment``. It is
unauthenticated because there is no account until it returns.

What comes back is deliberately thin. A success is a status and a sentence, and
it is the *same* success whether a row was written or the submission named an
address or an identity number already on file -- see ``services`` on why a
duplicate is not disclosed. Only a nickname collision and a document that moved
on while the form was open come back as something to correct, because those are
the two the member can act on.

Nothing here decides anything. Every rule is in ``services`` and
``common.validators``, so the endpoint is a translation of exceptions into
status codes and nothing more.
"""
from django.core.exceptions import ValidationError
from ninja import Router
from ninja.errors import HttpError

from app.documents import services as document_services

from . import services
from .schemas import RegisterIn, RegistrationOut, RegistrationRefusedOut
from .throttles import RegisterThrottle

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

    * **200** -- accepted. Also the answer to a submission naming an address or
      an identity number already on file, which writes nothing.
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
        services.register_member(
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

    return 200, {'status': services.REGISTERED_STATUS, 'detail': ACCEPTED_DETAIL}

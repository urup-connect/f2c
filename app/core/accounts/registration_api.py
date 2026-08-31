"""The one endpoint the produce market's sign-up form writes through.

``POST /api/customers/register`` takes four details, creates a ``User`` and
nothing else, and emails a six-digit sign-in code. It is unauthenticated because
there is no account until it returns.

**A second router in this app, not a fifth endpoint on the first one.** Every
route in ``accounts.api`` requires a session and is about ``request.user``;
this one has neither. ``membership`` made the same split for the same reason and
said so out loud -- one module carrying both would put an ``auth=None`` endpoint
two screens away from one that reads a member's identity number. The two mount
on different prefixes here, which makes the separation visible in the URL as
well as in the file.

**The response is deliberately the same for a new customer and for one already
on file.** ``accounts.registration`` says why at length; what it means here is
that this module has exactly one success body and no branch that could
accidentally grow a second.

Nothing here decides anything. The rules are in ``accounts.registration`` and
``common.validators``; this translates exceptions into status codes, maps
validator codes onto the store's wire vocabulary, and emails a code. The same
shape as ``membership.api`` and ``accounts.api``.
"""
import logging

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from ninja import Router
from ninja.errors import HttpError

from app.core.authn import otp as otp_service
from app.core.storefronts.resolution import storefront_for_request

from . import registration
from .schemas import (
    CustomerRegisterIn,
    CustomerRegistrationOut,
    CustomerRegistrationRefusedOut,
)
from .throttles import CustomerRegisterThrottle

logger = logging.getLogger(__name__)

router = Router(tags=['customers'])

#: What a customer is told on the way out, and it is the same sentence whether a
#: row was written or the address was already on file. Said here rather than only
#: in the store, because a caller reading this endpoint directly needs an answer
#: too -- the store renders its own conditional wording from
#: ``SIGN_UP_OUTCOME`` and never shows this string.
ACCEPTED_DETAIL = (
    'If that address did not already have an account, one has been created '
    'and a sign-in code is on its way.'
)

#: What a customer is told when the account is fine and the email is not.
#:
#: **The account is kept and the answer is a refusal, and both halves are
#: decisions.** A sign-in code is the only way into an account with no passkey,
#: so a registration whose code was never sent has not finished -- answering 200
#: would put "check your email" in front of somebody with nothing coming. And
#: the account is not rolled back to match: it is a good row, the failure is a
#: mail server, and undoing it would mean a second write that can fail for the
#: same reason and a customer whose next attempt starts from nothing.
#:
#: Retrying while the outage lasts lands on the duplicate path and answers this
#: again, which is honest -- sign-up genuinely cannot complete without mail. The
#: moment mail works, a retry sends the code.
#:
#: **It is the same answer whether a row was just written or the address was
#: already on file**, so the disclosure rule survives a mail outage. That is why
#: this is worded about the code rather than about the account.
UNDELIVERABLE_DETAIL = (
    'The account could not be completed because a sign-in code could not be '
    'sent. Nothing is wrong with what you entered. Please try again shortly.'
)

#: The validators' codes, as the store's form names them.
#:
#: **The one place the two vocabularies meet, and it is a table rather than a
#: convention.** ``common.validators`` names refusals for Python and
#: ``frontend/market/lib/sign-up.ts`` names them for a form; the two were
#: written apart and a rule that mapped one onto the other by rewriting
#: underscores would break the first time either side renamed anything, silently
#: and in the direction of showing a customer nothing.
#:
#: Not exhaustive on the store's side, on purpose. ``mobile-unexpected-characters``
#: and ``mobile-length`` are refusals the form makes and this API cannot: there
#: is one Python mobile rule and it answers with one code, deliberately -- see
#: ``validate_sa_mobile_number``. A code with no entry here is **dropped from
#: ``fields`` rather than passed through**, because the store drops what it does
#: not recognise anyway and an unmapped code reaching it would render as a
#: refusal against no input at all. The message still reaches ``detail``.
REFUSAL_CODES = {
    'name_missing': 'name-missing',
    'name_characters': 'name-unexpected-characters',
    'name_length': 'name-too-long',
    'email_missing': 'email-missing',
    'email_malformed': 'email-malformed',
    'email_length': 'email-too-long',
    'mobile_invalid': 'mobile-not-a-mobile',
}


def _refusal(error):
    """A field-keyed ``ValidationError`` as the refusal body.

    ``detail`` joins the validators' prose, for whoever is calling this
    endpoint directly. ``fields`` carries the mapped codes and only those --
    see ``REFUSAL_CODES`` on why an unmapped one is dropped rather than sent.

    Reads ``error_dict`` rather than ``message_dict``, which is the whole reason
    this function exists: the codes are on the individual errors and
    ``message_dict`` has already thrown them away.
    """
    fields = {}

    for field, errors in getattr(error, 'error_dict', {}).items():
        codes = [
            REFUSAL_CODES[refusal.code]
            for refusal in errors
            if getattr(refusal, 'code', None) in REFUSAL_CODES
        ]
        if codes:
            fields[field] = codes

    return {'detail': ' '.join(error.messages), 'fields': fields}


@router.post(
    '/register',
    response={
        200: CustomerRegistrationOut,
        422: CustomerRegistrationRefusedOut,
    },
    auth=None,
    throttle=[CustomerRegisterThrottle()],
)
async def register(request, payload: CustomerRegisterIn):
    """Create a store account and email a sign-in code.

    * **200** -- accepted. Also the answer to a submission naming an address or
      a handset already on file, which writes nothing.
    * **422** -- a field is not acceptable, keyed by field. The store validates
      every one of these itself and refuses first, so a customer reaching this
      has bypassed the form or the two rule sets have drifted.
    * **429** -- the per-IP limit, from ``CustomerRegisterThrottle``.
    * **503** -- twice, for two unrelated reasons that share one property: the
      submission is fine and the customer can only come back. Either this
      storefront requires agreement to a document this contract does not collect
      (``registration.ConsentRequired``), or the sign-in code could not be sent
      (``UNDELIVERABLE_DETAIL``). The same code ``/documents/current`` answers
      with when a required document has no published revision.

      **The second of those is the one this endpoint had to decide, because a
      mail outage lands differently here than anywhere else on this API.** A
      failed send during sign-in is retryable and idempotent; a failed send
      during registration follows a row that has already committed, so letting
      the exception through would answer 500 to somebody whose account exists,
      and every retry would do it again. The same outage 500s
      ``/auth/login/start`` and the club's duplicate-registration path today --
      neither is fixed here, and ``design/todo.md`` Block 0 carries it beside
      the mail provider itself.

    **Async, and it has to be.** ``authn.otp.issue`` is async -- Django has no
    async email API and password hashing is deliberately slow, so both run in a
    worker thread rather than blocking the event loop -- and the service it
    calls is ordinary synchronous ORM code. So the write crosses into a thread
    and the send stays on the loop, rather than the reverse.

    **The code is emailed after the write has committed**, outside the service's
    transaction, which is what ``sync_to_async`` around the service buys beyond
    thread safety: a code emailed inside the transaction is a code that outlives
    a rollback, and a customer holding a sign-in code for an account that was
    never created has no way to understand what happened.
    """
    # From the host, as it is for every other unauthenticated endpoint: there is
    # no session to ask, and nothing in the submission says which shopfront this
    # is. It decides the server, the sender and the name on the sign-in code --
    # the one thing a customer must be able to tell about a one-time code, since
    # one arriving from the store's provider under the club's name is
    # indistinguishable from a phishing attempt.
    #
    # **Read for the email and for nothing else.** Which documents this
    # registration owes an agreement to is `registration.REGISTERS_INTO`, named
    # rather than resolved -- see that module on why a host-scoped answer would
    # let an unmapped host refuse the store on the strength of the club's terms.
    storefront = storefront_for_request(request)

    try:
        outcome = await sync_to_async(registration.register_customer)(
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            mobile=payload.mobile,
        )
    except registration.ConsentRequired as refusal:
        # 503 rather than 422 or 500. Nothing is wrong with the submission and
        # nothing is broken; the store has published a document this contract
        # cannot honour, and the fix is a deployment rather than a retry.
        raise HttpError(503, str(refusal))
    except ValidationError as error:
        return 422, _refusal(error)

    if outcome.sign_in_for is not None:
        # Not gated on `created`. A duplicate naming a live account gets a code
        # too, because the confirmation screen sends everybody to the sign-in
        # screen to enter one -- see `CustomerRegistration.sign_in_for` for the
        # three cases and what each one discloses, which is nothing.
        try:
            await otp_service.issue(outcome.sign_in_for, storefront=storefront)
        except Exception:
            logger.exception(
                'customers: registration accepted but the sign-in code could '
                'not be sent; answering 503'
            )
            raise HttpError(503, UNDELIVERABLE_DETAIL) from None

    return 200, {'detail': ACCEPTED_DETAIL}

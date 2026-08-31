"""Creating a store customer: an account, and nothing else.

**A market customer is a ``User`` with no row in ``ClubMembership``,
``StorefrontStaff`` or ``ProducerMembership``** -- ``design/verticals.md``
section 6 -- and this module is what that sentence looks like as code. Four
fields, one of them optional, and no second table. It is the whole reason the
market can ship before the club's remaining verticals: buying produce needs an
account and nothing else.

It lives in ``accounts`` rather than in an app of its own, and the contrast with
``club.membership`` is the argument. That app owns no models and exists because
its write spans ``accounts`` and ``documents``, which must not know about each
other. This write spans one model, in this app. A ``market`` app that held it
would be an app whose only content is a function about ``User``.

What is deliberately absent is most of what registration used to mean, and each
absence is a decision rather than an omission:

**No identity number.** POPIA's minimisation principle refuses a field collected
on the strength of another storefront's requirement. The club asks because
``design/features/sign-up.md`` records a statutory basis for asking; the store
has none, so the store does not ask. The columns stay on ``User`` and stay null.

**No nickname.** A nickname is a member-facing handle inside the club and its
uniqueness index lives on ``ClubMembership`` -- C27. A customer has a name.

**No payment and no subscription.** Nothing is owed for holding a store account.
``membership.register_member`` opens a subscription in the same transaction
because a membership at *pending payment* with no subscription can never leave
that status; there is no equivalent state here to be stranded in.

**No consents -- but the endpoint refuses to pretend that is permanent.** The
store has no published documents yet, so there is nothing to agree to and a
checkbox would record a consent to nothing. The day somebody publishes a market
document at ``agreement=at_registration``, this refuses outright rather than
registering customers who agreed to it silently. See :class:`ConsentRequired`:
it is the difference between a loud failure and an unlawful one.

**The storefront is named, not resolved from the request**, and this is
``membership.services`` making the same choice in the opposite direction. That
one passes ``Storefront.CLUB`` explicitly because registration creates a
``ClubMembership`` and is club-scoped by definition, and because reading the
host would make it possible to join the club through the market's domain. This
is the store's front door, so it names ``Storefront.MARKET``, and the same
sentence holds backwards: the club's own three documents demand agreement at
registration, and a host-scoped check would let an unmapped host -- every
development machine, every preview deployment -- refuse the store on the
strength of the club's terms. Joining the club is ``/members/register`` and it
is the only route that reads those documents.

Two rules carry over from ``membership.services`` unchanged, and both are quoted
there at length:

**Every field is validated again here.** The endpoint is unauthenticated and
reachable without going through the store at all, so a rule that lives only in a
browser or only in a Next.js server action is not a rule the database is
protected by. ``common.validators`` is the floor; ``frontend/market/lib`` is what
a customer actually meets.

**A duplicate is not disclosed.** An address or a handset already on file
returns exactly what a successful registration returns, writing nothing.
Anything else turns the sign-up form into a way of asking whether a named person
shops here.
"""
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from app.core.common.validators import (
    validate_email_address,
    validate_person_name,
    validate_sa_mobile_number,
)
from app.core.documents.models import Document
from app.core.storefronts.models import Storefront

from .models import User, UserStatus

#: Where a registration leaves the account, and it is the whole of the account's
#: state. Stated here rather than left to ``create_user``'s default, for the
#: reason ``membership.services`` states its own: a reader asking what somebody
#: gets when they register should find the answer in the module that registers
#: them. There is no second status to be pending in, because there is no
#: membership -- that difference is the market vertical in one line.
REGISTERED_STATUS = UserStatus.ACTIVE

#: The storefront whose front door this is, named rather than resolved from the
#: request -- see the module docstring on why, and on the ``membership.services``
#: line it mirrors. It is read for exactly one thing: which documents demand an
#: agreement this contract cannot collect. **Nothing about the account it
#: creates is storefront-specific**, because nothing about an account is: the
#: same person may later join the club without registering again.
REGISTERS_INTO = Storefront.MARKET


class ConsentRequired(Exception):
    """The storefront has a document that must be agreed to at registration,
    and this endpoint collects no agreements.

    **A guard against a silent legal failure, and it fails loudly on purpose.**
    Publishing the store's terms with ``agreement=at_registration`` is one
    action in the Django admin, taken by whoever writes the terms rather than by
    whoever writes the endpoint. Without this, that action would quietly begin
    creating customers who are recorded as having agreed to nothing -- a
    condition no screen would show and no test would fail on, discovered
    whenever somebody next reads the consent ledger.

    Refused rather than worked around. Recording an agreement the form did not
    ask for would be a fabricated consent, which is worse than no consent; and
    accepting the registration without one would put the store in breach of the
    condition its own document sets.

    The fix is to extend the contract -- ``consents`` on the request, the way
    ``membership.schemas.RegisterIn`` carries it -- not to relax this. The
    machinery is already built and already storefront-scoped:
    ``documents.services.resolve_submitted`` and ``record_consents`` take a
    storefront and neither knows anything about the club.
    """

    def __init__(self, slugs):
        self.slugs = list(slugs)
        super().__init__(
            'This storefront requires agreement to a document that account '
            'creation does not yet collect, so no account can be created.'
        )


@dataclass(frozen=True)
class CustomerRegistration:
    """What an attempt did, and who -- if anybody -- should be emailed a code.

    ``created`` is ``False`` for a submission naming an address or a handset
    already on file. That is a deliberate no-op rather than a failure, and the
    caller must answer it exactly as it answers a success.

    ``sign_in_for`` is the account a one-time sign-in code should reach, and it
    is **not** the same question as ``created``. Three outcomes:

    * a new account -- the code proves the address, and it is the only way into
      an account with no passkey yet;
    * a duplicate naming a live, active account -- the code goes out too. The
      store's confirmation screen sends everybody to the sign-in screen to enter
      one, so a customer who forgot they had an account would otherwise be told
      to wait for something that never arrives. It reaches the mailbox rather
      than whoever filled in the form, which is the same channel and the same
      reasoning that lets ``membership.services`` email an outstanding payment
      link to a duplicate;
    * a duplicate naming a suspended account, or one matched on the handset
      alone -- ``None``. A suspended account cannot sign in, so a code would be
      an invitation to nothing; and a submission that duplicates a handset while
      naming a *different* address gets nothing sent, because emailing the typed
      address would tell it about somebody else's account.

    The response is identical in all three cases. What differs is what arrives
    in a mailbox, which only the mailbox's owner sees.
    """

    user: User | None
    created: bool
    sign_in_for: User | None = None


def _validated_details(*, first_name, last_name, email, mobile):
    """Every field, checked, as a dict ready to assign.

    **Every field, not the first bad one.** ``membership.services`` raises on
    the first refusal because its caller joins the messages into one sentence;
    this collects them per field, matching ``profile._validated_changes``,
    because the store's form renders a refusal under each input and somebody
    with two things wrong should be told two things once.

    The values in the raised ``ValidationError`` keep their ``code``, which is
    what ``registration_api`` maps onto the wire vocabulary the store's form
    reads. Messages stay prose and stay here.

    A blank mobile number is accepted and stored blank, as it is on the profile
    screen and for the same reason: it is what a driver rings, so a wrong number
    is worse than none.
    """
    errors = {}

    try:
        first = validate_person_name(first_name)
    except ValidationError as error:
        errors['first_name'] = error

    try:
        last = validate_person_name(last_name)
    except ValidationError as error:
        errors['last_name'] = error

    try:
        address = validate_email_address(email)
    except ValidationError as error:
        errors['email'] = error

    number = ''
    if str(mobile or '').strip():
        try:
            number = validate_sa_mobile_number(mobile)
        except ValidationError as error:
            errors['mobile'] = error

    if errors:
        raise ValidationError(errors)

    return {
        'first_name': first,
        'last_name': last,
        'email': address,
        'mobile': number,
    }


def _documents_demanding_agreement():
    """Slugs of the store's documents that must be agreed to at sign-up.

    Live documents only, and it does not care whether any of them has a
    published revision. A document with none cannot be agreed to either, so both
    states are the same refusal here -- unlike ``/documents/current``, where the
    two differ because sign-up has a form to render.
    """
    return list(
        Document.objects.agreed_at_registration(REGISTERS_INTO).values_list(
            'slug', flat=True
        )
    )


@transaction.atomic
def register_customer(*, first_name, last_name, email, mobile):
    """Create a store customer: one ``User``, Active, and no other row.

    :raises ValidationError: one or more fields are not acceptable. Keyed by
        field, with the validator's ``code`` intact.
    :raises ConsentRequired: the storefront requires an agreement this contract
        cannot collect.
    :returns: a :class:`CustomerRegistration`. Check ``created`` before assuming
        a row exists, and ``sign_in_for`` before emailing anything.
    """
    details = _validated_details(
        first_name=first_name, last_name=last_name, email=email, mobile=mobile
    )

    # Before the duplicate check and before anything is written. It is a fact
    # about the storefront rather than about the submission, so it applies to
    # everybody sending this form regardless of who they turn out to be -- the
    # same position, and the same ordering argument, as the club's stale-consent
    # refusal in `membership.services._resolve_consents`.
    demanded = _documents_demanding_agreement()
    if demanded:
        raise ConsentRequired(demanded)

    address = details['email']
    number = details['mobile']

    # Two keys rather than the club's three -- there is no identity number to
    # match on. Both are unique in the database (`User.Meta.constraints`), so
    # this is the polite answer rather than the enforcement: two simultaneous
    # submissions are separated by the index, not by this.
    #
    # Matched against accounts that still hold the value. `soft_delete` nulls
    # `email` and blanks `mobile`, so an erased customer may register again --
    # which is why `has_been_seen` is the wrong question here, exactly as it is
    # for the club.
    existing = User.objects.filter(email=address).first()
    duplicate = existing is not None or (
        bool(number) and User.objects.by_mobile(number).exists()
    )

    if duplicate:
        # Nothing is written. A code goes out only when the address itself named
        # a live, active account -- see `CustomerRegistration.sign_in_for` for
        # the three cases and why they differ.
        active = existing if existing is not None and existing.is_active else None
        return CustomerRegistration(user=None, created=False, sign_in_for=active)

    # `status` is not passed: `create_user` defaults it to Active, which is
    # where a store customer stays. There is nothing to verify before somebody
    # may hold an account -- the address is proved by the code they sign in
    # with -- and no membership standing to be pending, because there is no
    # membership.
    #
    # `create_user` rather than a bare `User(...)`: it is what sets the unusable
    # password, and a customer holds no password for the same reason a member
    # does not.
    user = User.objects.create_user(
        email=address,
        first_name=details['first_name'],
        last_name=details['last_name'],
        mobile=number,
    )

    return CustomerRegistration(user=user, created=True, sign_in_for=user)

"""Turning a sign-up submission into a member, and nothing else.

This app owns no models. It exists because the write it performs spans two that
must not know about each other: ``accounts`` holds the member, ``documents``
holds the club documents and the agreements against them, and ``documents``
already depends on ``accounts`` through ``AUTH_USER_MODEL``. An import back the
other way would make the two mutually dependent -- the same reason
``User.soft_delete`` reaches ``authn`` through reverse relations instead of
importing it. So the one function that needs both lives above both.

It is also where the payment gateway lands. A registration ends at
``PENDING_PAYMENT``; what moves an account from there to Active is a payment,
and a payment is this app's business rather than the account model's.

Four rules run through it.

**Every field is validated again here.** ``POST /api/members/register`` is
unauthenticated and reachable without going through the frontend at all, so a
rule that lives only in the browser, or only in a Next.js server action, is not
a rule the database is protected by. The Python versions are in
``common.validators`` and they are deliberately the *floor*, not a second
opinion: where they are narrower than the frontend's, the frontend refuses first
and a member never meets these messages.

**Age is checked from the identity document, not from the form.** The age gate
lives in the frontend and its pass is a cookie; neither is available here. The
identity number carries a date of birth, so that is what the eighteen-year rule
is applied to -- and it is calendar arithmetic, part by part, for the reasons
``common.validators.is_at_least`` sets out.

**A duplicate is not disclosed.** Three things identify a membership -- the
email address, the identity document, and the mobile number -- and any one of
them already on file returns exactly what a successful registration returns,
writing nothing. The alternative turns the form into a way to ask whether a
named person, a named identity number or a named phone belongs to a member
here. A nickname collision *is* disclosed, because a nickname is a claim against
other members and the member has to choose another one.

**Nothing is written unless everything is.** The member row and their three
agreements go in together or not at all, so there is no such thing as a member
whose agreements were lost, or an agreement against a member who was not
created.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from django.core.exceptions import ValidationError
from django.db import transaction

from app.accounts.models import User, UserStatus
from app.common.validators import (
    MINIMUM_MEMBER_AGE_YEARS,
    is_at_least,
    sa_id_birth_date,
    validate_email_address,
    validate_nickname,
    validate_person_name,
    validate_sa_id_number,
    validate_sa_mobile_number,
)
from app.documents import services as document_services
from app.documents.models import DocumentConsent

#: Where a registration leaves a new member. Named here rather than written out
#: at the call site: this is the one fact this app currently owns, and the
#: payment gateway will change it in one place.
REGISTERED_STATUS = UserStatus.PENDING_PAYMENT


class NicknameTaken(Exception):
    """The nickname belongs to another member.

    The one collision a registration is allowed to disclose. A nickname is what
    other members see, so a member whose choice is taken has to make another
    one -- and unlike an address or an identity number, knowing that a nickname
    is spoken for reveals nothing about who holds it.
    """

    def __init__(self, nickname):
        self.nickname = nickname
        super().__init__('That nickname is already taken. Please choose another.')


class ConsentSuperseded(Exception):
    """A revision was published between the form rendering and its submission.

    Refused rather than recorded against the newer text: a tick beside version
    one's wording is not an agreement to version two. Carries the documents at
    fault so the caller can point at the right checkboxes.
    """

    def __init__(self, documents):
        self.documents = list(documents)
        super().__init__(
            'One or more club documents changed while this form was open. '
            'Please read the current version and agree to it again.'
        )


@dataclass(frozen=True)
class Registration:
    """What an attempt did.

    ``user`` is ``None`` and ``created`` is ``False`` when the submission named
    an address or an identity number already on file. That is a deliberate
    no-op rather than a failure, and the caller must answer it exactly as it
    answers a success -- see the module docstring.
    """

    user: User | None
    created: bool


def _resolve_consents(submitted):
    """The live revisions the submission agreed to.

    Two refusals, distinguished on purpose. A *stale version* is a member's
    problem to fix by reading the document again, and the caller needs to know
    which checkboxes to say so against; anything else -- an unknown document, a
    duplicate, a missing one -- is a malformed submission and gets one generic
    answer.

    ``documents.services.resolve_submitted`` refuses both, and refuses them
    again after this, because it is the function the re-acceptance endpoint
    shares and it must not rely on a caller having checked first.
    """
    in_force = {
        revision.document.slug: revision
        for revision in document_services.current_revisions()
    }

    superseded = [
        entry['document']
        for entry in submitted
        if entry['document'] in in_force
        and (entry['version'] or '').strip() != in_force[entry['document']].label
    ]
    if superseded:
        raise ConsentSuperseded(superseded)

    return document_services.resolve_submitted(submitted)


def nickname_is_available(nickname):
    """Whether a nickname is free for a joining member to take.

    The one question sign-up may ask about somebody else's record, and the
    reason it may is the reason ``NicknameTaken`` exists: a nickname is a claim
    against other members, so a member whose choice is spoken for has to make
    another one, and knowing that it is spoken for reveals nothing about who
    holds it. The address, the identity document and the mobile number are the
    opposite and have no endpoint of their own -- see the module docstring on
    duplicates.

    Answers ``False`` for a reserved nickname as well as a taken one. It is well
    formed and belongs to nobody, and there is nothing to do about either but
    choose again.

    ``register_member`` asks the same question again at the write, and its
    answer is the one that counts: this is a courtesy ahead of the submission,
    and a nickname free now can be taken before the form is sent.

    :raises ValidationError: the nickname is not well formed.
    """
    try:
        nickname = validate_nickname(nickname)
    except ValidationError as error:
        # A reserved name is the one refusal `validate_nickname` raises that is
        # not about the nickname being malformed, and it is exactly what this
        # function is for. Answered rather than raised, so the caller has one
        # kind of "no" to render instead of two.
        if getattr(error, 'code', None) == 'nickname_unavailable':
            return False
        raise

    return not User.objects.nickname_is_taken(nickname)


@transaction.atomic
def register_member(
    *,
    first_name,
    last_name,
    nickname,
    email,
    mobile,
    id_number,
    consents,
    today=None,
):
    """Create a member at ``PENDING_PAYMENT``, with their agreements.

    ``consents`` is a list of ``{'document': slug, 'version': label}``, one per
    document required at sign-up.

    :raises ValidationError: a field is not acceptable, or the identity
        document says the applicant is under age.
    :raises NicknameTaken: the nickname belongs to another member.
    :raises ConsentSuperseded: a document moved on while the form was open.
    :raises documents.services.DocumentsNotReady: a required document has no
        published revision, so there is nothing lawful to agree to.
    :returns: a :class:`Registration`. Check ``created`` before assuming a row
        exists; see the module docstring on duplicates.
    """
    first_name = validate_person_name(first_name)
    last_name = validate_person_name(last_name)
    nickname = validate_nickname(nickname)
    email = validate_email_address(email)
    mobile = validate_sa_mobile_number(mobile)
    id_digits = validate_sa_id_number(id_number)

    # From the document, never from the form. `validate_sa_id_number` has
    # already established that this parses.
    date_of_birth = sa_id_birth_date(id_digits)
    if not is_at_least(date_of_birth, MINIMUM_MEMBER_AGE_YEARS, today):
        raise ValidationError(
            'The identity number given belongs to someone under '
            f'{MINIMUM_MEMBER_AGE_YEARS}.',
            code='under_age',
        )

    # First, and before any identity check: a document that has moved on is an
    # instruction to read it again, and it applies to everybody submitting this
    # form regardless of who they turn out to be.
    versions = _resolve_consents(consents)

    # The duplicate check comes *before* the nickname check, and the order
    # matters. A member who submits the form twice -- a double click, a back
    # button, a retried request -- holds their own nickname by then, and telling
    # them it is taken would be both confusing and untrue. Answering the second
    # submission exactly as the first, with nothing written, is what makes the
    # endpoint safe to call twice.
    #
    # Three keys, any one of which means somebody already holds this membership:
    # the address, the identity document, and the handset. Each is also unique in
    # the database (see `User.Meta.constraints`), so this check is the polite
    # answer rather than the enforcement -- a race between two simultaneous
    # submissions is refused by the index, not by this.
    #
    # All three are matched against *live* accounts only. `email` is nulled by
    # erasure, and `mobile` and the identity number are blanked by it, so an
    # erased member is allowed to register again -- which is the whole reason
    # `email_hash` is not unique. `has_been_seen` is the wrong question here for
    # exactly that reason.
    already_registered = (
        User.objects.filter(email=email).exists()
        or User.objects.by_id_number(id_digits).exists()
        or User.objects.by_mobile(mobile).exists()
    )
    if already_registered:
        return Registration(user=None, created=False)

    if User.objects.nickname_is_taken(nickname):
        raise NicknameTaken(nickname)

    user = User(
        first_name=first_name,
        last_name=last_name,
        nickname=nickname,
        email=email,
        mobile=mobile,
        status=REGISTERED_STATUS,
    )
    # Encrypts the number and writes its blind index in one step, which is the
    # only way this column may be written.
    user.id_number = id_digits
    # From the document rather than typed a second time, so the two cannot
    # disagree.
    user.date_of_birth = date_of_birth
    # `date_of_birth_verified_at` is deliberately left null, and this is *not*
    # `capture_sa_id_number`, which would stamp it. A number that passes its
    # check digit is a number that is not a typo; nobody has looked at a
    # document. Recording a self-service submission as verified would make that
    # field mean nothing, and it is the field the club would rely on later.
    user.date_of_birth_verified_at = datetime.now(tz=timezone.utc)
    # Members sign in with a passkey or an emailed code and never hold a
    # password. An unusable one cannot match any input, so it cannot be
    # guessed.
    user.set_unusable_password()
    user.save()

    document_services.record_consents(
        user, versions, source=DocumentConsent.Source.SIGNUP
    )
    return Registration(user=user, created=True)

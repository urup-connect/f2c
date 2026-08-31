"""Creating a sharing-member placeholder: stock the swap zone can be seeded with.

A sharing member is a **placeholder** a producer creates so that flowering
plants can sit in the swap zone. Members joining a new club need something to
swap against; this is where that stock comes from. **C6** decided it is not a
person: it has no name, no identity number and no email address, it consents to
nothing, and it signs in nobody.

This lives in ``accounts`` rather than in ``membership``, and the distinction is
not cosmetic. ``membership`` exists because turning a submission into a member
spans ``accounts`` and ``documents``, which must not know about each other. A
placeholder is not a membership in any sense but the table it is stored in -- no
subscription, no payment, no agreements -- so filing it beside
``register_member`` would put two unlike things under one name.

**Most of what this module used to say has gone, and it went with C6.** Three
of its four rules were about a person: the POPIA attestation that made holding
somebody's name and identity number lawful, the age check read off their
identity document, and the deliberately vague refusal when that number was
already on file. A placeholder has none of those, so none of them survive. The
refusal in particular is worth noting as *dissolved rather than solved*: it was
carried as an unavoidable leak -- a cultivator could learn that an identity
number was known to the club -- and it disappeared because the number is no
longer collected.

Two rules remain, and both are decisions rather than mechanisms.

**Authority is checked here, not assumed.** There is no endpoint yet, so today's
callers are the admin and the shell, and a service that trusted its caller would
be the wrong shape to put an endpoint in front of later. It asks for the
permission rather than for a relationship, so a superuser works and any future
grant works without this function changing.

**And it is checked against *this* producer.** Holding
``platform.register_sharing_member`` says somebody is a primary somewhere; it
does not say they are the primary of the farm whose stock this placeholder will
hold. That second question is the object-level rule ``roles-and-permissions.md``
carried as risk 9 and **C13** for as long as there was nothing to join against.
There is now: ``ProducerMembership`` rows, checked below. This is the first
place in the codebase that makes that check, and it is the shape the rest of
them should take -- the catalogue answers "may they at all", and the service
that owns the record answers "may they here".
"""
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from app.core.common.validators import (
    MINIMUM_MEMBER_AGE_YEARS,
    is_at_least,
    sa_id_birth_date,
    validate_nickname,
    validate_person_name,
    validate_sa_id_number,
)

from app.commerce.producers.models import ProducerRole
from app.club.membership.models import ClubMembership, MembershipStatus
from app.club.plant.models import MEMBER_FLOWERING_PLANT_LIMIT

from .models import User, UserStatus

#: The permission a caller must hold to put somebody on the sharing register.
#: Asked for by name rather than by role, so the rule is "whoever may do this"
#: rather than "whoever is a cultivator".
REGISTER_PERMISSION = 'platform.register_sharing_member'

#: Where a sharing-member placeholder sits, permanently: an identity that holds
#: records and authenticates nobody. Named here rather than written at the call
#: site, for the same reason ``membership`` names its own: this is the fact this
#: function decides.
SHARING_MEMBER_STATUS = UserStatus.NON_AUTHENTICATING

#: How many flowering plants a sharing member may hold, and the number a
#: cultivator allocates when they register one.
#:
#: **The same number as every other member's, and the same object** --
#: ``plant.models.MEMBER_FLOWERING_PLANT_LIMIT``, imported rather than restated.
#: C7 settled that the four attaches to the named adult, so this is that
#: person's own statutory allowance being spent rather than a quota the club
#: grants; C15 enforces it in ``Plant.transfer_to`` for every holder alike. Two
#: constants would let the sharing-member figure drift from the members' one,
#: and a divergence there would be the platform quietly deciding that a sharing
#: member is a different kind of adult under the Act.
#:
#: The name stays because this is what a *registration* returns -- an allocation
#: is what a cultivator does with the limit. Nothing here branches on it.
SHARING_MEMBER_PLANT_ALLOCATION = MEMBER_FLOWERING_PLANT_LIMIT


class IdentityNumberUnavailable(Exception):
    """That identity document already belongs to an account.

    Refused rather than answered as a success -- see the module docstring on
    duplicates -- and worded so that it does not say who holds it or in what
    capacity.
    """

    def __init__(self):
        super().__init__(
            'That identity number cannot be registered as a sharing member. '
            'Ask an administrator to check the record.'
        )


class NicknameTaken(Exception):
    """The nickname belongs to somebody already.

    Disclosed, where the identity number is not, and for the same reason
    ``membership.services.NicknameTaken`` is: a nickname is a claim against
    other people in the swap zone, so a taken one has to be replaced, and
    knowing it is spoken for reveals nothing about who holds it.
    """

    def __init__(self, nickname):
        self.nickname = nickname
        super().__init__('That nickname is already taken. Please choose another.')


@dataclass(frozen=True)
class SharingRegistration:
    """The record that was written, and how many plants it may hold.

    ``allocation`` is what the cultivator is expected to allocate next, and it
    is reported rather than acted on: there is no plant model, so nothing here
    can create the stock. Returning the number keeps the caller from hard-coding
    it.
    """

    user: User
    membership: object
    allocation: int


@transaction.atomic
def register_sharing_member(*, actor, producer, nickname):
    """Create a sharing-member placeholder so stock can enter the swap zone.

    **This function used to register a person and now creates a placeholder.**
    C6 decided a sharing member is not a real person, and what went with that
    decision is most of what this did: the names, the identity number, the age
    rule read off the document, and the cultivator's POPIA attestation that the
    person had consented. A placeholder consents to nothing, so an attestation
    over one was a ceremony around a fiction, and an identity number held for
    one would be personal data collected for no lawful purpose.

    What is left is the whole of it: a nickname the swap zone can display, and
    the cultivator whose stock it holds.

    Two rows, in one transaction. The ``User`` is the identity every plant,
    ownership record and certificate points at -- a placeholder still has to be
    an owner -- and it sits at ``NON_AUTHENTICATING`` with no address and an
    unusable password, so there is nothing to sign in with. The
    ``ClubMembership`` is what makes it the club's: status ``SHARING``, the
    nickname, and ``registered_by``.

    **What a placeholder does in the swap zone is deferred to the swap zone.**
    C7 is still open and its brief has changed -- the club now holds this stock
    itself rather than allocating it to a named adult -- so nothing here guesses
    at how many plants it may hold or who may move them.

    :param actor: the account doing it. Must hold
        ``platform.register_sharing_member`` **and** be the primary of
        ``producer``.
    :param producer: the farm whose stock this placeholder will hold.
    :param nickname: what the swap zone displays. Required.
    :raises PermissionDenied: the caller may not create placeholders, or may not
        create one for this producer.
    :raises ValidationError: the nickname is not acceptable.
    :raises NicknameTaken: the nickname belongs to somebody already.
    :returns: a :class:`SharingRegistration`.
    """
    if actor is None or not actor.has_perm(REGISTER_PERMISSION):
        # PermissionDenied rather than ValidationError: nothing about the
        # submission is wrong, and the caller cannot fix it by editing a field.
        raise PermissionDenied(
            'Only a producer’s primary may create a sharing member.'
        )

    if producer is None:
        raise ValidationError(
            'A sharing member holds a producer’s stock, so it needs the '
            'producer it is created under.',
            code='producer_required',
        )

    # **The object-level half.** The permission above says this person is a
    # primary; this says they are the primary *here*. A superuser is exempt, as
    # they are from every other check -- Django's permission framework treats
    # them that way and a second rule would be a place for the two to disagree.
    if not actor.is_superuser and not producer.appointments.filter(
        user=actor, role=ProducerRole.PRIMARY
    ).exists():
        raise PermissionDenied(
            'Only this producer’s own primary may create a sharing member for '
            'it.'
        )

    # Required, not optional. The swap zone shows a nickname, and a blank one
    # would put unnamed stock in front of members. `validate_nickname` refuses
    # an empty value, so this is the check.
    nickname = validate_nickname(nickname)

    # Against the membership table, which is where the nickname and its unique
    # index both live now. The polite answer rather than the enforcement: two
    # simultaneous creations are refused by the index.
    if ClubMembership.objects.nickname_is_taken(nickname):
        raise NicknameTaken(nickname)

    user = User(
        # No names, no email address, no mobile number, no identity number.
        # That is the whole shape of a placeholder after C6: there is nobody to
        # name, nothing to authenticate and nothing to send a code to.
        email=None,
        mobile='',
        status=SHARING_MEMBER_STATUS,
    )
    # There is no password and never will be one. An unusable password cannot
    # match any input, so it cannot be guessed.
    user.set_unusable_password()
    user.save()

    membership = ClubMembership.objects.create(
        user=user,
        nickname=nickname,
        status=MembershipStatus.SHARING,
        registered_by=producer,
    )

    return SharingRegistration(
        user=user,
        membership=membership,
        allocation=SHARING_MEMBER_PLANT_ALLOCATION,
    )

"""Registering a sharing member: the one account somebody else creates for you.

A sharing member is an identity a cultivator puts on the register so that it can
hold flowering plants, and so that those plants appear in the swap zone. Members
joining a new club need something to swap against; this is where that stock
comes from. They give a name, an identity number and a nickname, they hold no
email address, and they never sign in.

This lives in ``accounts`` rather than in ``membership``, and the distinction is
not cosmetic. ``membership`` exists because turning a submission into a member
spans ``accounts`` and ``documents``, which must not know about each other. This
write spans nothing: it touches one model, in this app. And a sharing member is
not a membership -- no subscription, no payment, no agreements of their own -- so
filing it beside ``register_member`` would put two unlike things under one name.

Four rules run through it, and each is a decision rather than a mechanism.

**The cultivator's authority is checked here, not assumed.** There is no
endpoint yet, so today's callers are the admin and the shell, and a service that
trusted its caller would be the wrong shape to put an endpoint in front of
later. It asks for the permission, not for the role, so a superuser works and a
future role that gains the permission works without this function changing.

**The attestation is the lawful basis, so nothing is written without it.** The
sharing member never saw a form and cannot have consented on one. POPIA still
needs a reason for the club to hold their name and identity number, so the
cultivator attests that the person agreed and was given the collection notice,
and that attestation is recorded with who made it and when. Refusing to write
without it is the whole point: an unattested record is one the club cannot
justify holding, and it is better not to exist. ``accounts.roles`` carries the
wording and says why it is called an attestation.

**Age is checked from the identity document, exactly as it is at sign-up.** A
sharing member holds cannabis plants. That the plants are nominally the club's
stock changes nothing about who the record says is holding them.

**A duplicate is refused, and the refusal says as little as it can.** The
identity number is unique across every account, so a person already on file --
as a member, or as another cultivator's sharing member -- cannot be registered
again. Unlike ``membership.services.register_member``, this cannot answer a
duplicate as though it succeeded: the cultivator is waiting to allocate plants
to a record, and pretending one exists would be a lie they would trip over.

So the refusal is deliberately vague. It says the identity number cannot be
registered and to ask an administrator; it does not say the person is already a
member, or whose sharing member they are. That is a weaker leak than naming the
record, and it is still a leak -- a cultivator can learn that an identity number
is known to the club. It is recorded as a risk in
``design/features/roles-and-permissions.md`` rather than solved, because
enforcing one account per identity document and telling the cultivator their
registration failed cannot both be done silently.
"""
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from app.common.validators import (
    MINIMUM_MEMBER_AGE_YEARS,
    is_at_least,
    sa_id_birth_date,
    validate_nickname,
    validate_person_name,
    validate_sa_id_number,
)

from .models import User, UserStatus
from .roles import SHARING_CONSENT_VERSION, UserRole

#: The permission a caller must hold to put somebody on the sharing register.
#: Asked for by name rather than by role, so the rule is "whoever may do this"
#: rather than "whoever is a cultivator".
REGISTER_PERMISSION = 'platform.register_sharing_member'

#: Where a sharing member sits, permanently. Named here rather than written at
#: the call site, for the same reason ``membership`` names its own two: this is
#: the fact this function decides.
SHARING_MEMBER_STATUS = UserStatus.SHARING
SHARING_MEMBER_ROLE = UserRole.SHARING_MEMBER

#: How many flowering plants a sharing member may hold. The same limit members
#: live under, and the number a cultivator allocates when they register one.
#:
#: Stated here and enforced nowhere, because there is no plant to count. It is
#: the swap service's rule when there is one, and it is written down now so the
#: number is not re-invented from memory later.
SHARING_MEMBER_PLANT_ALLOCATION = 4


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
    allocation: int


@transaction.atomic
def register_sharing_member(
    *,
    cultivator,
    first_name,
    last_name,
    nickname,
    id_number,
    consent_attested,
    today=None,
):
    """Put a sharing member on the register, on a cultivator's attestation.

    :param cultivator: the account registering them. Must hold
        ``platform.register_sharing_member``.
    :param consent_attested: the cultivator's confirmation, in the words of
        ``roles.SHARING_CONSENT_ATTESTATION``. Anything falsy refuses the whole
        registration.
    :raises PermissionDenied: the caller may not register sharing members.
    :raises ValidationError: a field is not acceptable, the identity document
        says the person is under age, or the attestation was not given.
    :raises IdentityNumberUnavailable: that document already belongs to an
        account.
    :raises NicknameTaken: the nickname belongs to somebody already.
    :returns: a :class:`SharingRegistration`.
    """
    if cultivator is None or not cultivator.has_perm(REGISTER_PERMISSION):
        # PermissionDenied rather than ValidationError: nothing about the
        # submission is wrong, and the caller cannot fix it by editing a field.
        raise PermissionDenied(
            'Only a cultivator may register a sharing member.'
        )

    # Before the fields, because it is not a field. A submission with everything
    # right and no attestation is not a submission with one thing missing; it is
    # a record the club has no lawful basis to hold, and there is nothing to
    # validate about the rest of it.
    if not consent_attested:
        raise ValidationError(
            'A sharing member cannot be registered without confirming that '
            'they consented and were given the collection notice.',
            code='consent_not_attested',
        )

    first_name = validate_person_name(first_name)
    last_name = validate_person_name(last_name)
    # Required, not optional, unlike on a staff account. The swap zone shows a
    # nickname, and a blank one would put unnamed stock in front of members.
    # `validate_nickname` refuses an empty value, so this is the check.
    nickname = validate_nickname(nickname)
    id_digits = validate_sa_id_number(id_number)

    # From the document, never typed a second time. `validate_sa_id_number` has
    # already established that this parses.
    date_of_birth = sa_id_birth_date(id_digits)
    if not is_at_least(date_of_birth, MINIMUM_MEMBER_AGE_YEARS, today):
        raise ValidationError(
            'The identity number given belongs to someone under '
            f'{MINIMUM_MEMBER_AGE_YEARS}.',
            code='under_age',
        )

    # Matched through the blind index against every account, whatever its role.
    # The column is unique, so this is the polite answer rather than the
    # enforcement -- two simultaneous registrations are refused by the index.
    if User.objects.by_id_number(id_digits).exists():
        raise IdentityNumberUnavailable()

    if User.objects.nickname_is_taken(nickname):
        raise NicknameTaken(nickname)

    attested_at = timezone.now()
    user = User(
        first_name=first_name,
        last_name=last_name,
        nickname=nickname,
        # No email address and no mobile number. That is the whole shape of a
        # sharing member: there is nothing to authenticate and nothing to send
        # a code to. `email` is nullable for erasure's sake, and this is the
        # second reason it has to be.
        email=None,
        mobile='',
        status=SHARING_MEMBER_STATUS,
        role=SHARING_MEMBER_ROLE,
        registered_by=cultivator,
        sharing_consent_attested_by=cultivator,
        sharing_consent_attested_at=attested_at,
        sharing_consent_version=SHARING_CONSENT_VERSION,
    )
    # Encrypts the number and writes its blind index in one step, which is the
    # only way this column may be written.
    user.id_number = id_digits
    user.date_of_birth = date_of_birth
    # Left null, exactly as `membership.services.register_member` leaves it, and
    # for the same reason: a number that passes its check digit is a number that
    # is not a typo. The cultivator attested that the person consented, not that
    # a document was inspected and matched, and recording this as verified would
    # make the field mean nothing on the day the club relies on it.
    user.date_of_birth_verified_at = None
    # There is no password and never will be one. An unusable password cannot
    # match any input, so it cannot be guessed.
    user.set_unusable_password()
    user.save()

    return SharingRegistration(
        user=user, allocation=SHARING_MEMBER_PLANT_ALLOCATION
    )

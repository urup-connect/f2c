"""What a member may change about themselves, and what they may only look at.

The split is the whole design, and it is not arbitrary. Three fields are the
member's own to correct -- their two names and the handset the club reaches them
on -- and two are not: the date of birth and the identity number were taken from
a document, and a field a member can retype is a field that no longer means what
``date_of_birth_verified_at`` claims it does. Those two are readable here and
amendable only through the admin, by somebody who has seen a document.

Four things are decisions rather than mechanism.

**The mobile number is re-checked for uniqueness, and the refusal names the
problem.** One handset, one membership, is the club's rule -- see the constraint
on ``User.mobile``. Unlike registration, this cannot answer a collision as
though it had succeeded: the member is looking at a form and waiting to be told
whether it saved. So it says the number is held by another account, which does
disclose that a number is on file somewhere. That is a smaller leak than at
sign-up, because the caller is an authenticated member changing their own
record rather than an anonymous form, and it is the only answer that lets them
act.

**Nothing here is partial.** Every field the caller sends is validated before
any of them is written, so a form with a bad number does not silently save the
new surname alongside the old one. The member is told what to fix and the record
is exactly as it was.

**The email address is not editable, and its absence is deliberate.** It is the
sign-in identifier: changing it changes who the account is, and doing that
through a form with no proof of the new address is how an account gets handed to
a typo. It needs a verify-then-swap flow of its own, which is not this.

**The nickname is not editable either**, for a different reason: it is unique
across the club and other members know each other by it. Changing one is a
club-facing act rather than a personal detail, and it is left where the
uniqueness question is already answered -- the admin. It is *reported* here, and
it now comes from the membership rather than the account -- C27 -- so it is
blank for somebody who never joined the club.

**Who may use this is a permission, and that is now worth re-examining.** The
catalogue grants ``platform.manage_own_profile`` to members, producers and
administrators, which was everybody who could sign in. It is not everybody any
more: a produce-market customer holds no relationship at all and so holds no
permissions, and this refuses them their own name and photograph. That is the
wrong answer, and `roles.py` already says why -- *a permission that everybody
holds and nobody can be refused is not a permission.* Carried in `todo.md` as a
decision for the market vertical rather than changed here in passing, because
removing a codename from the catalogue is a contract change the frontend reads.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from app.core.common import crypto
from app.core.common.validators import validate_person_name, validate_sa_mobile_number

from . import avatars
from .models import User

#: The permission a caller must hold. Asked for by name rather than by role, so
#: the rule is "whoever may manage their own profile" -- which today is all
#: three signing-in roles, and tomorrow is whatever the catalogue says.
MANAGE_OWN_PROFILE = 'platform.manage_own_profile'

#: The fields this module will write, and the only ones.
#:
#: Declared rather than derived, and read by the tests rather than by the code:
#: it is the boundary this module promises, written where the promise is made so
#: a test can hold it there. A field added to ``update_profile`` without being
#: added here fails ``test_the_read_only_fields_are_untouched``.
EDITABLE_FIELDS = ('first_name', 'last_name', 'mobile')


class MobileUnavailable(Exception):
    """Another account already holds that handset.

    Its own exception rather than a ``ValidationError`` because the endpoint
    answers it differently -- 409 rather than 422. Nothing is wrong with the
    number the member typed; it is simply not theirs to take.
    """

    def __init__(self, message=None):
        super().__init__(message or 'Another account already holds that mobile number.')


def _validated_changes(*, first_name, last_name, mobile):
    """Every field, checked, as a dict ready to assign. Raises on the first
    field that is not acceptable.

    ``ValidationError`` messages are collected per field rather than joined,
    because the frontend refuses all of these itself and anything reaching here
    is a caller that bypassed the form -- one which is better served by being
    told which field than by a sentence it has to parse.

    A blank mobile number is accepted and stored blank. It is a contact detail
    rather than a credential, the column allows it, and a member who no longer
    has the handset they gave should be able to say so rather than leave a wrong
    number on file for the club to ring.
    """
    errors = {}

    try:
        first = validate_person_name(first_name)
    except ValidationError as error:
        errors['first_name'] = error.messages

    try:
        last = validate_person_name(last_name)
    except ValidationError as error:
        errors['last_name'] = error.messages

    number = ''
    if str(mobile or '').strip():
        try:
            number = validate_sa_mobile_number(mobile)
        except ValidationError as error:
            errors['mobile'] = error.messages

    if errors:
        raise ValidationError(errors)

    return {'first_name': first, 'last_name': last, 'mobile': number}


@transaction.atomic
def update_profile(user, *, first_name, last_name, mobile):
    """Write the three editable fields on this member's own record.

    Returns the same instance, saved. The caller is the account being changed;
    there is no path here for editing somebody else, which is why no permission
    beyond ``MANAGE_OWN_PROFILE`` is consulted and why ``user`` is not looked up
    from an identifier the request supplied.

    The uniqueness check and the write are one transaction. Two members claiming
    the same handset in the same instant is not a race this can lose -- the
    unique constraint refuses the second write regardless -- but the check
    reading a row the write then invalidates would report the wrong reason, and
    a member told nothing is wrong while nothing saved is worse than a refusal.
    """
    if not user.has_perm(MANAGE_OWN_PROFILE):
        # PermissionDenied rather than ValidationError, matching
        # `register_sharing_member`: nothing about the submission is wrong, the
        # caller simply may not do this. Reachable only for a suspended or
        # erased account, whose permissions are empty by `roles.permissions_for`
        # -- neither can hold a session, so this is a floor rather than a gate.
        raise PermissionDenied('This account may not change its own profile.')

    changes = _validated_changes(
        first_name=first_name, last_name=last_name, mobile=mobile
    )

    number = changes['mobile']
    if number:
        # `by_mobile` normalises before it looks, so the comparison is against
        # the stored form rather than against whatever punctuation was typed.
        held_by_another = (
            User.objects.by_mobile(number).exclude(pk=user.pk).exists()
        )
        if held_by_another:
            raise MobileUnavailable()

    for field, value in changes.items():
        setattr(user, field, value)

    # A full save rather than update_fields. `updated_at` is auto_now, and
    # Django skips auto_now columns a partial save does not name -- the same
    # reason `soft_delete` saves in full.
    user.save()
    return user


@transaction.atomic
def set_avatar(user, data):
    """Replace this member's photograph with the image in ``data``.

    ``data`` is bytes, not a file: ``accounts.avatars`` decodes and re-encodes
    every upload, so what is stored is a 512-pixel JPEG this application
    produced rather than the file that arrived. That is what strips the EXIF a
    phone photograph carries, and it is the reason an upload cannot be a
    polyglot -- only pixels survive a decode. See that module.

    Raises ``ValidationError`` for anything that is not a usable image, in words
    written for the member.

    The previous photograph is **deleted before the new one is written**, and
    that is a correction rather than a flourish. ``avatar_upload_to`` gives an
    account one path so that a replacement replaces, but the two backends
    disagree about what happens when something is already there:
    ``FileSystemStorage`` refuses to overwrite and quietly appends a random
    suffix, while the Azure backend is configured to overwrite. Left alone,
    replacing an avatar would accumulate every previous photograph on a
    developer's disk and on any deployment with no container configured, while
    doing the right thing in production -- the worst kind of difference, because
    the environment that keeps the files is the one nobody looks at.

    Deleting first makes both backends behave the same way, and it does it here
    rather than in a storage subclass so that the reason sits next to the rule
    it enforces.
    """
    if not user.has_perm(MANAGE_OWN_PROFILE):
        raise PermissionDenied('This account may not change its own profile.')

    # Raises before anything is written or deleted, so a refused upload leaves
    # the member's existing photograph where it was.
    image = avatars.avatar_file(data)

    if user.avatar:
        # `save=False`: the row is saved once, below. A blob already gone is not
        # a failure -- the point is that nothing of the old photograph is left,
        # and something else having got there first satisfies that.
        try:
            user.avatar.delete(save=False)
        except FileNotFoundError:
            user.avatar = ''

    # `save=False`, then one full save below. Saving inside `FileField.save`
    # would write the row twice and, on the failure path, leave `avatar`
    # pointing at a blob while `avatar_updated_at` still described the old one.
    user.avatar.save(image.name, image, save=False)
    user.avatar_updated_at = timezone.now()
    user.save()
    return user


@transaction.atomic
def clear_avatar(user):
    """Take this member's photograph down, and delete the stored image.

    Idempotent: an account with no photograph is left alone and reported as
    success, because "there is no picture of me on file" is the state the caller
    asked for and it is already true.
    """
    if not user.has_perm(MANAGE_OWN_PROFILE):
        raise PermissionDenied('This account may not change its own profile.')

    user.clear_avatar()
    user.save()
    return user


def profile_of(user):
    """The profile as the frontend reads it, as a plain dict.

    Assembled here rather than resolved field-by-field on the schema, because
    two of these values are neither columns nor free: the masked identity number
    decrypts, and the avatar address has to carry a version. Doing that in one
    named place means the endpoint is a translation and nothing more.

    ``id_number`` never appears, in any form other than masked. There is no
    parameter to this function that would produce the full number, which is the
    point: an endpoint cannot be talked into disclosing something the service
    has no way to return.
    """
    return {
        'first_name': user.first_name,
        'last_name': user.last_name,
        'nickname': user.club_nickname,
        'email': user.email,
        'mobile': user.mobile,
        'display_name': user.display_name,
        'date_of_birth': user.date_of_birth,
        'date_of_birth_verified_at': user.date_of_birth_verified_at,
        'has_id_number': user.has_id_number,
        'id_number_masked': _masked_id_number(user),
        'has_avatar': user.has_avatar,
        'avatar_url': avatar_url(user),
        'status': user.status,
    }


#: What a masked number reads as when the row will not decrypt. The admin says
#: the same thing for the same reason -- a key or integrity problem is somebody's
#: job, and hiding it behind "not on file" would have a member told the club
#: holds no document when it holds one it cannot read.
UNREADABLE_ID_NUMBER = 'UNREADABLE'


def _masked_id_number(user):
    try:
        return user.id_number_masked
    except crypto.DecryptionError:
        return UNREADABLE_ID_NUMBER


def avatar_url(user):
    """The address the frontend should request this member's photograph from.

    A path on the API rather than a storage URL, and that is the design: the
    avatars container is private and has no public address, so the only way to
    a photograph is through the endpoint that checks the session first. See
    ``accounts.storage``.

    The version is ``avatar_updated_at`` as a Unix timestamp. Every avatar is
    written to the same path, so without it a member who has just replaced their
    photograph is shown the cached previous one and concludes the upload failed.

    ``None`` when there is no photograph, so a caller renders initials rather
    than requesting an address that will 404.
    """
    if not user.has_avatar:
        return None

    stamp = user.avatar_updated_at
    version = int(stamp.timestamp()) if stamp else 0
    return f'/api/accounts/me/avatar?v={version}'

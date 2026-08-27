"""The club administrator's view of the membership, and the rules governing it.

``services`` in this app turns a sign-up submission into a member. This module
is the other end of the same record: what an administrator may read, correct and
suspend once that member exists. ``administration_api`` is a translation of the
exceptions raised here into status codes and nothing more, which is the shape
``strains.services`` and ``accounts.profile`` already have -- and the permission
check is here rather than in the router for the reason ``strains.services``
gives: a router that authorised its own callers would be the only thing between
a member and the register, and a second caller (a management command, a Block 11
support-ticket handler) would have nothing.

**Scope.** ``design/todo.md`` Block 9 lists five things under Members. This
module holds the first two -- view, edit, suspend, reinstate, and the recent
sign-ups the list already sorts for. Warnings and expulsions need a sanction
model that does not exist; revoking access and cancelling a membership are
separate permissions, and ``conflict.md`` C2 puts cancellation in the UC tier
that has not been built. Named here so the absence reads as a boundary rather
than an oversight.

Six rules live here, and each is here rather than on the model for a reason.

1. **One permission gates the whole module, and it is
   ``platform.disable_user``.** The catalogue in ``accounts.roles`` has a
   ``manage_cultivators`` and no ``manage_members``; the only administrative
   action over a member account is "disable or remove any account". So reads are
   gated on it too, the same way ``strains.services`` gates catalogue reads on
   ``manage_strain_catalogue``. The gap is real -- a club administrator who may
   correct a typo should not need the authority to suspend -- and closing it
   means a new codename, a catalogue test and a navigation entry, which belongs
   with the two-tier split in C2 rather than ahead of it.

2. **An erased account is read-only.** ``User.soft_delete`` is the POPIA erasure
   route: it clears the personal data and keeps the row so the club's operating
   history survives. Writing a name back onto one would undo an erasure the
   member asked for, quietly, from a screen that looks like an ordinary edit
   form. ``activate`` already refuses to resurrect one; every write here refuses
   too.

3. **A sharing member is not editable from this screen.** They hold stock and
   never sign in, their record belongs to the cultivator who registered them
   through ``platform.manage_sharing_members``, and ``conflict.md`` C14 has not
   decided whether an administrator may touch one at all. Refusing is the
   answer that does not pre-empt that decision.

4. **Nobody suspends themselves.** An administrator who suspends their own
   account is signed out by ``flush_sessions`` on the way and cannot sign back
   in to undo it. The database has no opinion about this and no screen should
   have to remember it.

5. **Reinstating means Active, and only from Suspended.** There is no column
   recording where an account sat before it was suspended, so reinstatement
   cannot restore it -- and inventing a rule that guesses would be worse than
   refusing. An account at Pending payment is not suspended and has a payment
   route of its own; ``payments`` owns that, not this.

6. **Reading an identity number in full writes a row first.** See
   ``accounts.IdentityNumberDisclosure``. The write happens before the decrypt,
   so a read that happened is a read that is recorded even if the response never
   reaches the caller.
"""
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from app.accounts.models import (
    IdentityNumberDisclosure,
    User,
    UserRole,
    UserStatus,
)
from app.common.validators import (
    normalise_id_number,
    validate_email_address,
    validate_nickname,
    validate_person_name,
    validate_sa_mobile_number,
)
from app.payments.models import Subscription

#: The single action this module answers to. See rule 1 in the module docstring
#: on why a read is gated on it as well as a write, and on the codename that
#: does not exist yet.
MANAGE_MEMBERS = 'platform.disable_user'

#: Every column an administrator may write from the register. The API schema is
#: the outer allow-list and this is the inner one, deliberately duplicated:
#: a field added to the schema by accident cannot reach ``setattr`` without also
#: being added here.
#:
#: Absent on purpose, each for its own reason. ``status`` is moved by
#: ``suspend_member`` and ``reinstate_member``, which have rules a field
#: assignment does not. ``role`` is appointed in the Django admin and nowhere
#: else -- ``design/backend.md`` section 10 -- because handing out authority over
#: other members' records is not a form field. ``id_number`` is write-only by the
#: same section. ``is_active`` is derived. ``date_of_birth`` comes from the
#: identity document and typing it a second time is how the two disagree.
WRITABLE_FIELDS = frozenset({
    'first_name',
    'last_name',
    'nickname',
    'email',
    'mobile',
})

#: How far back the register's *joined within* filter offers to look. Days, and
#: the list is newest-first regardless -- so the recent sign-ups view is this
#: filter over the ordinary register rather than a screen of its own.
RECENT_WINDOWS = (7, 30, 90)

#: What the register defaults to when the screen asks for recent sign-ups
#: without naming a window.
DEFAULT_RECENT_WINDOW = 30

#: The shortest reason that counts as one. A disclosure whose reason is "x" is a
#: disclosure nobody can review, which defeats the row -- see rule 6.
MINIMUM_DISCLOSURE_REASON = 10

#: How long a search term has to be before it is tried against the identity
#: number's blind index. The same floor ``accounts.admin.get_search_results``
#: uses: the index is exact-match only, so this cannot be used to browse, and
#: shorter terms are names rather than documents.
ID_SEARCH_MINIMUM_DIGITS = 6


def _authorise(user):
    """Refuse a caller who does not hold the register's permission.

    ``PermissionDenied`` rather than ``ValidationError``, matching
    ``strains.services._authorise`` and ``accounts.profile.update_profile``:
    nothing about the submission is wrong, the caller simply may not do this.
    """
    if user is None or not user.has_perm(MANAGE_MEMBERS):
        raise PermissionDenied('This account may not manage the membership.')


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------

def _live_subscriptions():
    """The arrangement in force against a member, prefetched onto the row.

    ``Subscription.objects.live()`` is at most one row per member -- a partial
    unique index says so -- so this attaches a list of nought or one and the
    schema reads the first of it. A prefetch rather than an annotation because
    the standing needs three columns off that row (status, ``paid_until``,
    ``cancelled_at``) and three subqueries would be three scans of the same
    table.
    """
    return models.Prefetch(
        'subscriptions',
        queryset=Subscription.objects.live().order_by('-created_at'),
        to_attr='live_subscriptions',
    )


def _register_queryset():
    """The register as both the list and the detail screen read it."""
    return (
        User.objects
        .select_related('registered_by')
        .prefetch_related(_live_subscriptions())
    )


def register(
    user,
    *,
    status=None,
    role=None,
    search=None,
    joined_within=None,
):
    """The membership register, narrowed by whatever the list screen is filtering on.

    Every filter is optional and absent means unfiltered, matching
    ``strains.services.catalogue``: a ``select`` reset to "any" submits an empty
    string, so blank and absent have to mean the same thing on both sides.

    ``joined_within`` is a number of days, and it is what makes the *recent
    sign-ups* view a filter rather than a second screen. The list is newest-first
    either way -- ``User.Meta.ordering`` is ``('-created_at',)`` -- so the
    recent view is this register with a window on it.

    ``search`` covers the four columns an administrator would recognise a member
    by, plus one they would not expect: a term of six or more digits is also
    tried against the identity number's blind index, which is exact-match only
    and so cannot be used to browse. That is the same reach
    ``accounts.admin.get_search_results`` has, and it is here for the same
    reason -- somebody holding a document is the one search a club actually
    performs.

    Unpaginated, and that is a decision with a shelf life. It is the same
    decision ``strains.services.catalogue`` took and it will expire sooner: a
    strain catalogue is tens of rows and a membership is not. When the club
    outgrows a scannable list this needs ``ninja.pagination`` and the screen
    needs a pager; the note is here so that is a change rather than a discovery.
    """
    _authorise(user)

    members = _register_queryset()

    if status:
        members = members.filter(status=status)
    if role:
        members = members.filter(role=role)
    if joined_within:
        members = members.filter(
            created_at__gte=timezone.now() - timedelta(days=int(joined_within))
        )

    if search and (term := search.strip()):
        matches = (
            models.Q(first_name__icontains=term)
            | models.Q(last_name__icontains=term)
            | models.Q(nickname__icontains=term)
            | models.Q(email__icontains=term)
        )

        # The identity document, by exact digest. `normalise_id_number` strips
        # the spaces a person types, and the length floor keeps a three-digit
        # search off the index -- see `ID_SEARCH_MINIMUM_DIGITS`.
        digits = normalise_id_number(term)
        if len(digits) >= ID_SEARCH_MINIMUM_DIGITS:
            matches |= models.Q(
                pk__in=User.objects.by_id_number(digits).values('pk')
            )

        members = members.filter(matches)

    # Stated rather than inherited. `User.Meta.ordering` already says this, and
    # restating it here means a later annotation cannot silently drop it --
    # Django stops applying a model's default ordering once a query carries an
    # aggregate, which is exactly the trap `strains.services.catalogue` records.
    return members.order_by('-created_at')


def member_detail(user, member_id):
    """One member in full, as the record screen reads it.

    Raises ``User.DoesNotExist``, which the endpoint turns into a 404. The
    disclosure history comes down with the member rather than from an endpoint
    of its own: it is short, it is only ever read beside the record it belongs
    to, and a second round trip would buy nothing.
    """
    _authorise(user)

    return (
        _register_queryset()
        .prefetch_related(
            models.Prefetch(
                'identity_disclosures',
                queryset=(
                    IdentityNumberDisclosure.objects
                    .select_related('read_by')
                    .order_by('-created_at')
                ),
            )
        )
        .get(pk=member_id)
    )


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def _editable(member):
    """Refuse a record this screen may not write to at all.

    Two refusals, both raised as a non-field ``ValidationError`` so the endpoint
    answers 422 with a sentence rather than a 403 -- the caller holds the
    permission, and it is this particular record that is out of bounds. See
    rules 2 and 3 in the module docstring.
    """
    if member.deleted_at is not None:
        raise ValidationError(
            'This account was erased at the member’s request. Its details are '
            'gone and cannot be written back.',
            code='erased',
        )
    if member.role == UserRole.SHARING_MEMBER:
        raise ValidationError(
            'A sharing member’s record belongs to the cultivator who '
            'registered them. Change it there.',
            code='sharing_member',
        )


def _validated_email(value, *, exclude_pk):
    """A well-formed address no other live account holds.

    ``validate_email_address`` lower-cases and checks the shape;
    ``User.save`` lower-cases again, so the uniqueness query below and the write
    agree about what they are comparing.

    Unlike sign-up, a duplicate **is** disclosed here. Sign-up hides it because
    the form is unauthenticated and telling a stranger that an address is on file
    turns it into a membership oracle. An administrator already holds the whole
    register; withholding it from them would only produce a save that fails with
    no reason given.
    """
    address = validate_email_address(value)

    taken = User.objects.filter(email=address).exclude(pk=exclude_pk)
    if taken.exists():
        raise ValidationError(
            'Another account already uses that email address.',
            code='duplicate',
        )

    return address


def _validated_nickname(value, *, exclude_pk):
    """A nickname free for this member to wear, or blank.

    Blank is allowed and is not the same as taken: an administrator clearing a
    nickname leaves the member without one, which ``User.display_name`` already
    falls back from. ``nickname_key`` is null for a blank one, which is what lets
    any number of accounts hold none under an unconditional unique index.

    A *reserved* nickname is refused with the wording ``validate_nickname``
    raised, not folded into "already taken" -- the two are different facts and an
    administrator is the one person who can act on the difference.
    """
    if not (value or '').strip():
        return ''

    nickname = validate_nickname(value)

    if User.objects.nickname_is_taken(nickname, exclude_pk=exclude_pk):
        raise ValidationError(
            'Another member already wears that nickname.', code='duplicate'
        )

    return nickname


def _validated_mobile(value, *, exclude_pk):
    """A South African mobile number no other account holds.

    Normalised to the stored ``+27`` form before the uniqueness query, because
    ``mobile_key`` is that form and a number typed as ``082 …`` would otherwise
    miss a row holding ``+2782…``.
    """
    mobile = validate_sa_mobile_number(value)

    taken = User.objects.filter(mobile_key=mobile).exclude(pk=exclude_pk)
    if taken.exists():
        raise ValidationError(
            'Another account already uses that mobile number.', code='duplicate'
        )

    return mobile


def _apply(member, fields):
    """Validate a whole submission against ``member``, then write it.

    Everything is validated before anything is assigned, and every refusal is
    collected rather than raised at the first one -- so an administrator who
    mistyped an address *and* a mobile number is told both, rather than told the
    first and then the second on the next attempt. The same shape, and the same
    reasoning, as ``strains.services._apply``.
    """
    if unknown := set(fields) - WRITABLE_FIELDS:
        # Not a refusal: the caller is this project's own API, and a field
        # reaching here that is not writable is a schema that has drifted from
        # the allow-list. Loud, and never in a response body.
        raise ValueError(f'Not writable on a member: {", ".join(sorted(unknown))}.')

    errors = {}
    values = dict(fields)

    def resolve(field, resolver):
        """Replace ``values[field]`` with its checked form, or drop it."""
        if field not in values:
            return
        try:
            values[field] = resolver(values[field])
        except ValidationError as error:
            errors[field] = error.messages
            del values[field]

    resolve('first_name', validate_person_name)
    resolve('last_name', validate_person_name)
    resolve('email', lambda value: _validated_email(value, exclude_pk=member.pk))
    resolve(
        'nickname', lambda value: _validated_nickname(value, exclude_pk=member.pk)
    )
    resolve('mobile', lambda value: _validated_mobile(value, exclude_pk=member.pk))

    if errors:
        raise ValidationError(errors)

    for field, value in values.items():
        setattr(member, field, value)

    # A full save rather than `update_fields`. `updated_at` is `auto_now`, and
    # Django skips an `auto_now` column a partial save does not name -- the same
    # reason `accounts.profile.update_profile` saves in full. An edit that did
    # not move `updated_at` would be invisible on the register, which sorts and
    # reports on it.
    member.save()

    return member


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------

@transaction.atomic
def update_member(user, member, **fields):
    """Replace every editable field on ``member``, and return it.

    A replace rather than a patch, matching ``accounts.profile.update_profile``
    and ``strains.services.update_strain``: the screen holds every field and
    sends every field, so behaviour does not depend on what a browser chose to
    omit.

    Deliberately narrow. Five columns, none of which carries authority or
    money -- see ``WRITABLE_FIELDS`` on what is missing and why.
    """
    _authorise(user)
    _editable(member)

    return _apply(member, fields)


@transaction.atomic
def suspend_member(user, member):
    """Block this account from signing in, reversibly, and return it.

    ``User.deactivate`` moves the status and ends every live session the account
    holds -- without which an already signed-in browser keeps working until its
    cookie expires.

    No session count comes back, and the omission is deliberate. ``deactivate``
    cuts the sessions itself and returns the member rather than the number, so
    reporting one would mean either counting them again afterwards -- always
    zero, and a lie -- or restating ``flush_sessions``' decode loop here, which
    is a second copy of a rule that has to stay in step with the session
    backend. The screen says the account has been signed out, which is true
    without a number.

    Refuses three things: an erased account and a sharing member, per
    ``_editable``; and the caller's own account, per rule 4 -- an administrator
    who suspends themselves is signed out on the way out and cannot sign back in
    to undo it.

    Idempotent. Suspending an already-suspended account is a no-op that answers
    200, because a caller that got what it asked for should not be told it
    failed.
    """
    _authorise(user)
    _editable(member)

    if member.pk == getattr(user, 'pk', None):
        raise ValidationError(
            'You cannot suspend your own account. Suspending it would sign you '
            'out and leave nobody able to undo it.',
            code='self_suspension',
        )

    if member.status == UserStatus.SUSPENDED:
        return member

    member.deactivate(UserStatus.SUSPENDED)
    return member


@transaction.atomic
def reinstate_member(user, member):
    """Let a suspended account sign in again, and return it.

    Only from Suspended, and only to Active. See rule 5 -- there is no column
    recording where the account sat beforehand, so this cannot restore it, and a
    rule that guessed would be worse than refusing.

    ``User.activate`` raises ``ValueError`` for an erased account and for a
    sharing member. Both are refused earlier here, as a ``ValidationError`` the
    endpoint can answer 422 with, so a screen gets a sentence rather than a 500.
    """
    _authorise(user)
    _editable(member)

    if member.status == UserStatus.ACTIVE:
        return member

    if member.status != UserStatus.SUSPENDED:
        raise ValidationError(
            'Only a suspended account can be reinstated. This one is '
            f'{member.get_status_display().lower()}, which is not a block the '
            'club placed on it.',
            code='not_suspended',
        )

    member.activate()
    return member


@transaction.atomic
def disclose_id_number(user, member, *, reason):
    """Read a member's identity number in full, recording that it happened.

    Returns ``(number, disclosure)``. The row is written **before** the column is
    decrypted, and inside a transaction that the decrypt is part of -- so the
    only ways to read the number without leaving a record are to fail the write,
    which rolls the read back, or to bypass this function entirely. See rule 6
    and ``accounts.IdentityNumberDisclosure``.

    ``reason`` is required and is required to say something. A reason nobody can
    review afterwards is the same as no reason at all, which is what the masked
    default already gives you for free.

    Raises ``ValidationError`` when there is no number on file. That is not an
    error in the submission, but it is the only answer the screen can act on --
    and writing a disclosure for a read that returned nothing would put a row in
    an evidence table describing something that did not happen.
    """
    _authorise(user)

    stated = (reason or '').strip()
    if len(stated) < MINIMUM_DISCLOSURE_REASON:
        raise ValidationError(
            {'reason': [
                'Say why the number has to be read -- at least '
                f'{MINIMUM_DISCLOSURE_REASON} characters. It is recorded '
                'against this member.'
            ]},
        )

    if not member.has_id_number:
        raise ValidationError(
            'There is no identity number on file for this member.',
            code='absent',
        )

    disclosure = IdentityNumberDisclosure.objects.create(
        member=member, read_by=user, reason=stated
    )

    # After the row, deliberately. `id_number` raises `crypto.DecryptionError`
    # for a row that will not decrypt, and that exception is not swallowed here
    # either -- it rolls the transaction back, so an unreadable column does not
    # leave a disclosure claiming somebody read it.
    return member.id_number, disclosure

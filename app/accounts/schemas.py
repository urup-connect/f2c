"""The member as the frontend sees them.

Written out by hand rather than generated from the model, so a model change
cannot silently alter the payload the frontend depends on. That is the same
reason ``documents.schemas`` and ``authn.schemas`` are explicit.
"""
from datetime import date, datetime
from uuid import UUID

from ninja import Schema

from .roles import permissions_for


class UserOut(Schema):
    """The signed-in member, as the frontend sees them.

    ``email`` is nullable and the names may be blank because an erased account
    keeps its row -- see ``User.soft_delete``. Such an account can never sign
    in, so the frontend will not meet one here, but the contract has to admit
    the shape. ``id_number`` is absent on purpose: it is encrypted at rest and
    has no business crossing the wire to a browser.

    ``permissions`` is sent alongside ``role`` rather than left for the frontend
    to derive from it. Two reasons. A frontend that maps roles to abilities
    itself is a second copy of ``accounts.roles`` that will drift from the one
    the API enforces, and the drift shows up as navigation offering a member
    something the API then refuses. And an endpoint of its own for the same
    answer would be a second round trip on every page that renders a menu.

    It is for rendering, never for deciding. Every endpoint checks the
    permission itself; a list in a browser is a hint about what to draw.
    """

    id: UUID
    email: str | None
    first_name: str
    last_name: str
    nickname: str
    # `+27` and nine digits, or blank. A contact detail rather than a
    # credential -- members sign in with an emailed code or a passkey.
    mobile: str
    # Whatever should appear on screen: nickname, then full name, then email.
    display_name: str
    date_of_birth: date | None
    # Null until someone has checked the date against a document.
    date_of_birth_verified_at: datetime | None
    status: str
    # What the account is: admin, cultivator, member or sharing member.
    # Independent of `is_staff`, which opens the Django admin and nothing else.
    #
    # A sharing member cannot reach this schema -- they hold no email address
    # and a constraint keeps the role out of Active, so no session can belong to
    # one -- but the field reports the column rather than a subset of it.
    role: str
    # Every `platform.*` action this account holds, sorted. Empty for an
    # inactive account, and the whole catalogue for a superuser.
    permissions: list[str]
    is_staff: bool

    @staticmethod
    def resolve_permissions(obj):
        """Sorted, so the payload is stable between requests.

        ``permissions_for`` is pure dictionary lookup and issues no query, which
        is what lets this resolver run inside the async views in ``authn.api``
        -- a synchronous ORM call there raises ``SynchronousOnlyOperation``.
        """
        return sorted(permissions_for(obj))


class ProfileOut(Schema):
    """A member's own record, as the profile screen reads it.

    Separate from ``UserOut`` rather than an extension of it, and the reason is
    the two fields at the bottom. ``UserOut`` is what every signed-in page
    receives on every request through ``/api/auth/me``; this is what one screen
    asks for when a member opens it. Folding these in would put a decryption and
    an avatar lookup on the path of every page render, to serve a field almost
    none of them draws.

    ``permissions`` is absent for the same reason in reverse: this screen renders
    no menu, and the session it belongs to already carries the list.

    ``id_number_masked`` is the only form the identity number takes here, and
    ``accounts.profile`` has no way to produce any other -- see ``profile_of``.
    All but the last four digits are replaced, which is enough for the owner to
    recognise their document and useless to anybody who intercepts the response.
    An RSA number's last four are the citizenship digit, a legacy digit and the
    Luhn check digit, so they disclose neither the date of birth nor the
    gender-ordered sequence the leading ten carry.

    ``avatar_url`` is a path on this API, never a storage address. The avatars
    container is private and has no public URL; the only way to a photograph is
    the endpoint that checks the session first. It carries a version so that a
    replaced photograph is fetched rather than served from the browser's cache,
    every avatar being written to the same path.
    """

    first_name: str
    last_name: str
    # Shown but not editable here: it is unique across the club and other
    # members know each other by it, so changing one is a club-facing act.
    nickname: str
    # Shown but not editable here: it is the sign-in identifier, and swapping it
    # needs proof that the new address receives mail.
    email: str | None
    # `+27` and nine digits, or blank.
    mobile: str
    display_name: str
    # Read-only, both of them. Taken from an identity document at sign-up, so a
    # field the member could retype is a field `date_of_birth_verified_at` would
    # no longer be telling the truth about.
    date_of_birth: date | None
    date_of_birth_verified_at: datetime | None
    has_id_number: bool
    # All but the last four digits replaced with `*`. Blank when none is on
    # file, and the literal 'UNREADABLE' for a row that will not decrypt --
    # surfaced rather than reported as absent, because a member told the club
    # holds no document when it holds one it cannot read would go and send it
    # again. See `accounts.profile.UNREADABLE_ID_NUMBER`.
    id_number_masked: str
    has_avatar: bool
    # Null when there is no photograph, so the screen draws initials rather than
    # requesting an address that would 404.
    avatar_url: str | None
    role: str
    status: str


class ProfileIn(Schema):
    """The three fields a member may change about themselves.

    Every field is required, and none is optional-with-a-default. This is a
    replace rather than a patch: a form that sends two of three fields and has
    the third left alone is a form whose behaviour depends on what the browser
    chose to omit, and the failure mode is a member's surname quietly surviving
    a rename. The screen holds all three, so it sends all three.

    A blank ``mobile`` is accepted and clears the column. A member who no longer
    has the handset they gave should be able to say so, rather than leave a
    number on file for the club to ring.

    Not here, deliberately: ``nickname``, ``email``, ``date_of_birth`` and the
    identity number. ``accounts.profile`` says why for each.
    """

    first_name: str
    last_name: str
    mobile: str = ''


class ProfileRefusedOut(Schema):
    """Why a profile write was refused.

    ``detail`` is a sentence for whoever is calling the endpoint directly.
    ``fields`` is the same refusal per field, which is what the form renders
    against each input -- the frontend validates all three itself, so a member
    only meets this if the two rule sets have drifted, and naming the field is
    what makes that drift findable rather than mysterious.

    ``mobile_unavailable`` marks the one refusal that is not about the value: the
    number is well formed and belongs to another account.
    """

    detail: str
    fields: dict[str, list[str]] = {}
    mobile_unavailable: bool = False

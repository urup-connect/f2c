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

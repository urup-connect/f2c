"""The member as the frontend sees them.

Written out by hand rather than generated from the model, so a model change
cannot silently alter the payload the frontend depends on. That is the same
reason ``documents.schemas`` and ``authn.schemas`` are explicit.
"""
from datetime import date, datetime
from uuid import UUID

from ninja import Schema


class UserOut(Schema):
    """The signed-in member, as the frontend sees them.

    ``email`` is nullable and the names may be blank because an erased account
    keeps its row -- see ``User.soft_delete``. Such an account can never sign
    in, so the frontend will not meet one here, but the contract has to admit
    the shape. ``id_number`` is absent on purpose: it is encrypted at rest and
    has no business crossing the wire to a browser.
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
    is_staff: bool

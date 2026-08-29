"""Response shapes that are not specific to any one feature.

Only the acknowledgement envelope lives here. Everything else belongs to the
feature that returns it -- ``accounts.schemas`` for the member, and
``authn.schemas`` for the sign-in ceremonies -- so a change to one feature's
contract cannot reach across into another's.
"""
from ninja import Schema


class MessageOut(Schema):
    """An endpoint that has nothing to return but confirmation that it ran."""

    detail: str

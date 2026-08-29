"""Request and response shapes for the club-document endpoints.

Explicit rather than derived from the models, for the same reason as
``accounts.schemas``: a model change must not silently alter the payload the
frontend depends on.

The field names match what the frontend already calls them -- ``document`` for
the slug and ``version`` for the label -- so the consent shape crossing the
wire is the same shape the sign-up form has always built.
"""
from datetime import datetime

from ninja import Schema


class DocumentOut(Schema):
    """One document, at the revision currently in force."""

    # The stable slug: 'club-rules', 'annexures', 'constitution'.
    document: str
    title: str
    # The version label, as a string. Not an integer: a revision may be
    # numbered '2.1' or '2026-08', and a frontend that parses it as a number
    # would round-trip those to something else.
    version: str
    url: str
    # The exact sentence to render beside the checkbox. Sent rather than held
    # in frontend copy, so the wording a member ticks and the wording recorded
    # against their agreement cannot drift apart.
    consent_text: str
    # Published so a caller can verify the file it fetched is the file this
    # revision describes.
    sha256: str
    requires_reacceptance: bool
    effective_from: datetime


class DocumentsOut(Schema):
    documents: list[DocumentOut]


class ConsentIn(Schema):
    """One agreement, as the sign-up form posts it."""

    document: str
    version: str


class AcceptConsentsIn(Schema):
    consents: list[ConsentIn]


class ConsentOut(Schema):
    """One agreement as recorded, for confirmation back to the caller."""

    document: str
    version: str
    accepted_at: datetime


class AcceptConsentsOut(Schema):
    recorded: list[ConsentOut]
    # Revisions the member still owes after this write. Normally empty; not
    # empty if a revision was published between the form rendering and this
    # request, in which case the member is asked again.
    outstanding: list[DocumentOut]

"""The registration request and the three answers it can get.

Written out by hand rather than generated from the model, so a model change
cannot silently alter the contract the frontend depends on -- the same reason
``accounts.schemas``, ``documents.schemas`` and ``authn.schemas`` are explicit.

Two decisions are worth recording.

**The success response says nothing about the member.** No id, no email
address, no name, nothing that came in. A registration is answered from a
Next.js server action which then redirects, and a redirect carries only a URL;
returning a member record would put a value in reach of a query string. The
status is the whole answer, and it is the same answer whether a row was written
or the submission named somebody already on file.

**The refusal response is machine-readable and typed, not a message to parse.**
The frontend has to turn a refusal back into an error against a specific
checkbox or field, and matching on prose is how that silently stops working.
So the two refusals a member can act on are named fields.
"""
from ninja import Schema


class ConsentIn(Schema):
    """One agreement: the document, and the revision the form was rendered with.

    The version is a string, not a number. A revision may be labelled ``2.1``
    or ``2026-08``, and it is compared for equality with what is in force
    rather than ordered.
    """

    document: str
    version: str


class RegisterIn(Schema):
    """Exactly what sign-up collects.

    Every value arrives as typed and is normalised server-side; nothing here
    assumes the caller has done it. ``id_number`` is the only field that is
    never echoed back, logged, or put in a response of any kind.
    """

    first_name: str
    last_name: str
    nickname: str
    email: str
    mobile: str
    id_number: str
    consents: list[ConsentIn]


class RegistrationOut(Schema):
    """A registration that was accepted.

    ``status`` is where the account now sits -- ``pending_payment``. The
    frontend reads it rather than assuming it, so the day a gateway makes
    registration complete in one step, the confirmation screen follows without
    a second change.
    """

    status: str
    detail: str


class RegistrationRefusedOut(Schema):
    """A registration the member can do something about.

    ``detail`` is for a human. The other two fields are what the frontend maps
    back onto the form: ``nickname_unavailable`` marks the nickname field, and
    each slug in ``superseded_documents`` marks that document's checkbox. Both
    default to "not this one", so a refusal that adds a third reason later does
    not make an older frontend misread the two it knows.
    """

    detail: str
    nickname_unavailable: bool = False
    superseded_documents: list[str] = []

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
from datetime import date, datetime
from uuid import UUID

from ninja import Schema

from app.common import crypto


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

    ``checkout_token`` is how the member reaches Payfast, and **it is null on a
    submission that named an address already on file.** That is the one place
    where this response is not identical for a new member and a duplicate, and
    it is a decision taken with its cost understood: whoever submitted the form
    can tell the two apart by whether they were sent to a payment page. What
    they learn is bounded to "this address may already be on file" -- the
    duplicate path says nothing else, writes nothing, and the link to finish an
    outstanding payment is emailed rather than returned. See
    ``design/features/payments.md`` section 4 and its risk table, and
    ``design/features/sign-up.md`` on the rule this partially reverses.

    The token is a bearer credential: 32 bytes of entropy, valid for a day, and
    spent the moment the subscription is paid. It names a subscription and
    nothing about who holds it, which is what makes it safe to put in a URL at
    all.
    """

    status: str
    detail: str
    checkout_token: str | None = None


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


class NicknameAvailabilityIn(Schema):
    """The nickname a visitor has just finished typing.

    A body rather than a query parameter, and the endpoint is a POST for the
    same reason: a nickname in a URL is a nickname in every access log, proxy
    log and browser history between here and the member. It is the mildest
    value this form collects and it is still not ours to scatter.
    """

    nickname: str


class NicknameAvailabilityOut(Schema):
    """Whether the nickname is free, and nothing else.

    One boolean, deliberately. It does not say who holds a taken nickname, when
    it was taken, or what it is close to -- and it does not echo the nickname
    back, so a proxy caching the answer caches nothing about the person who
    asked.

    A *reserved* nickname is answered ``False`` like any other taken one. It is
    well formed and belongs to nobody, and there is nothing for a member to do
    about it but choose again.
    """

    available: bool


class NicknameRejectedOut(Schema):
    """A nickname that is not well formed.

    ``detail`` is for a human and for a log. The frontend refuses every one of
    these itself before asking, so a member who reaches this has bypassed the
    form -- or the two rule sets have drifted, which is worth a loud log line at
    whoever is calling.
    """

    detail: str


# ----------------------------------------------------------------------
# The administrator's register
# ----------------------------------------------------------------------
# Everything below is read and written by `administration_api`, behind
# `platform.disable_user`. It is the one part of this project's API where a
# member's own details cross the wire, and that needs saying out loud.
#
# Section 6.6 of `roles-and-permissions.md` makes `display_name` the only name
# any payload carries, and `strains.schemas.CultivatorOut` is the model citizen:
# an id and a display name, no address, no status. These schemas are the stated
# exception, not a lapse. An administrator correcting a mistyped address has to
# see the address; a register that showed only nicknames would send them to the
# Django admin for every task, which is precisely what `conflict.md` C5 says the
# club cannot keep doing.
#
# The exception is bounded in three ways, and each is a decision:
#
# * **The list carries no identity number at all** -- not even the masked form.
#   `id_number_masked` decrypts, so a masked column on a list of six hundred
#   members is six hundred decryptions per page load, and the fact the list
#   needs is only whether one is on file. `MemberRowOut.has_id_number` reads the
#   ciphertext column's emptiness and never decrypts.
# * **The record carries the masked form and never the number.** Reading it in
#   full is `POST /{id}/identity-number`, which writes an
#   `accounts.IdentityNumberDisclosure` before it decrypts. See
#   `administration.disclose_id_number`.
# * **`read_by` on a disclosure is a `display_name`.** The rule holds where it
#   costs nothing: who read a number is a question about a colleague, and a
#   nickname answers it.


class MembershipStandingOut(Schema):
    """Where a member's subscription stands, or nulls when there is none.

    Three fields off `payments.Subscription`, and deliberately not the amount or
    the gateway token. What this screen answers is "may this person be here" --
    the money is `platform.refund_transaction` and `platform.cancel_membership`,
    which C2 puts in the UC tier and this router does not hold.

    Null throughout for a member with no live arrangement: an erased account, a
    sharing member, or one whose subscription has lapsed or been cancelled.
    ``Subscription.objects.live()`` is at most one row, so there is no
    ambiguity about which one this is.
    """

    status: str | None = None
    status_label: str | None = None
    #: How far the membership is paid up. The one column that decides whether an
    #: account keeps its access, and the only input to ``lapse_overdue``.
    paid_until: date | None = None


class MemberRowOut(Schema):
    """One member on the administrator's register.

    The facts a decision to open, correct or suspend a record turns on, and
    nothing else. No identity number, masked or otherwise -- see the section
    note above on why the list is the one place that would cost something.

    ``status`` and ``role`` come with their labels because the two vocabularies
    live in ``accounts`` and a second copy in the frontend would drift from the
    check constraint that enforces them. The raw value is what a filter submits;
    the label is what a column shows.
    """

    id: UUID
    display_name: str
    first_name: str
    last_name: str
    nickname: str
    #: Null on an erased account -- ``soft_delete`` clears the address and keeps
    #: the row. The screen shows the account as erased rather than as nameless.
    email: str | None
    mobile: str

    status: str
    status_label: str
    role: str
    role_label: str

    membership: MembershipStandingOut

    #: Whether a document is on file, read from the ciphertext column being
    #: non-empty. Never decrypts. See the section note.
    has_id_number: bool
    #: Set when the member asked to be erased. A row that is present, read-only
    #: and says so, rather than one missing from the register with no
    #: explanation.
    erased: bool

    created_at: datetime

    @staticmethod
    def resolve_status_label(obj):
        return obj.get_status_display()

    @staticmethod
    def resolve_role_label(obj):
        return obj.get_role_display()

    @staticmethod
    def resolve_erased(obj):
        return obj.deleted_at is not None

    @staticmethod
    def resolve_membership(obj):
        """The live subscription ``administration._live_subscriptions`` attached.

        ``getattr`` rather than a plain attribute read: the prefetch names it
        ``live_subscriptions``, and a caller that serialised a member fetched
        some other way should get the empty standing rather than an
        ``AttributeError``.
        """
        live = getattr(obj, 'live_subscriptions', None) or []
        if not live:
            return MembershipStandingOut()

        subscription = live[0]
        return MembershipStandingOut(
            status=subscription.status,
            status_label=subscription.get_status_display(),
            paid_until=subscription.paid_until,
        )


class DisclosureOut(Schema):
    """One occasion on which staff read this member's identity number.

    ``read_by`` is a ``display_name`` and is null once that account has been
    deleted outright -- ``SET_NULL``, so the fact that a disclosure happened
    outlives whoever made it. See ``accounts.IdentityNumberDisclosure``.
    """

    id: UUID
    read_by: str | None
    reason: str
    created_at: datetime

    @staticmethod
    def resolve_read_by(obj):
        return obj.read_by.display_name if obj.read_by_id else None


class MemberOut(Schema):
    """One member in full, as the record screen reads it.

    Everything on the row, plus what only the record needs: the masked identity
    number, who registered a sharing member, the dates, and the disclosure
    history.

    ``editable`` is the answer to "may this screen write to this record", and it
    is sent rather than derived in the browser. The two reasons a record is
    read-only -- it was erased, or it belongs to a cultivator's sharing member --
    are rules in ``administration._editable``, and a second copy in the frontend
    would be a form that offers a save the API then refuses.
    """

    id: UUID
    display_name: str
    first_name: str
    last_name: str
    nickname: str
    email: str | None
    mobile: str

    status: str
    status_label: str
    role: str
    role_label: str

    membership: MembershipStandingOut

    has_id_number: bool
    #: All but the last four digits, or ``''`` when none is on file, or
    #: ``UNREADABLE`` for a row that will not decrypt. See the resolver.
    id_number_masked: str
    erased: bool
    editable: bool

    #: The cultivator who put a sharing member on the register, as a
    #: ``display_name``. Null for everybody else.
    registered_by: str | None

    date_of_birth: date | None
    date_of_birth_verified_at: datetime | None
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime

    disclosures: list[DisclosureOut] = []

    # The four resolvers `MemberRowOut` also has. Repeated rather than inherited:
    # the two schemas are not a base and a subclass, they are a list row and a
    # record, and the day the list drops a column this file should not have to
    # unpick an inheritance chain to do it. The same argument
    # `strains.schemas` makes by writing `StrainRowOut` and `StrainOut` out
    # separately.

    @staticmethod
    def resolve_status_label(obj):
        return obj.get_status_display()

    @staticmethod
    def resolve_role_label(obj):
        return obj.get_role_display()

    @staticmethod
    def resolve_erased(obj):
        return obj.deleted_at is not None

    @staticmethod
    def resolve_membership(obj):
        return MemberRowOut.resolve_membership(obj)

    @staticmethod
    def resolve_registered_by(obj):
        return obj.registered_by.display_name if obj.registered_by_id else None

    @staticmethod
    def resolve_disclosures(obj):
        """The reads recorded against this member, newest first.

        ``administration.member_detail`` prefetches these in order, so reading
        the relation here is one query for the whole screen rather than one per
        row. A member serialised without that prefetch still answers correctly,
        one query later -- which is what makes this safe to reuse as the
        response body of a suspension.
        """
        return list(obj.identity_disclosures.all())

    @staticmethod
    def resolve_editable(obj):
        """Mirrors ``administration._editable``, which is the rule.

        Restated here rather than imported, and the duplication is bounded: two
        conditions, both columns on the row being serialised. Importing the
        service into the schema module would make the schemas depend on the
        rules they describe, and this is the only place the answer is needed as
        a *value* rather than as a refusal.
        """
        from app.accounts.models import UserRole

        return obj.deleted_at is None and obj.role != UserRole.SHARING_MEMBER

    @staticmethod
    def resolve_id_number_masked(obj):
        """The last four digits behind asterisks, or ``UNREADABLE``.

        ``design/backend.md`` section 10: a row that will not decrypt shows
        ``UNREADABLE``, surfaced rather than hidden, because it is a key or
        integrity problem somebody has to look at. Swallowing it into a blank
        would present unrecoverable data as absent, which is the worst available
        outcome -- nobody would know to look.

        This is the one place in this app that catches ``DecryptionError``. The
        full read in ``administration.disclose_id_number`` deliberately does not:
        there, the exception rolls back the disclosure row.
        """
        try:
            return obj.id_number_masked
        except crypto.DecryptionError:
            return 'UNREADABLE'


class MemberIn(Schema):
    """The five details an administrator may correct.

    Every field present on every write. This is a replace, matching
    ``StrainIn`` and ``ProfileIn``: the screen holds the whole set and sends the
    whole set, so behaviour does not depend on what a browser chose to omit.

    Absent on purpose, and each absence is a decision recorded in
    ``administration.WRITABLE_FIELDS``: ``status`` moves through suspend and
    reinstate, which have rules a field assignment does not; ``role`` is
    appointed in the Django admin and nowhere else; the identity number is
    write-only; ``is_active`` is derived; and the date of birth comes off the
    identity document.

    ``nickname`` may be blank. Clearing one is a legitimate act -- the member
    simply has none, and ``display_name`` falls back -- and it is not the same
    as the nickname being taken.
    """

    first_name: str
    last_name: str
    nickname: str = ''
    email: str
    mobile: str


class IdentityDisclosureIn(Schema):
    """The reason a member's identity number has to be read in full.

    Required, and required to say something -- see
    ``administration.MINIMUM_DISCLOSURE_REASON``. It is written to
    ``accounts.IdentityNumberDisclosure`` before the column is decrypted, and it
    is the whole value of that row: a disclosure nobody can review afterwards is
    the same as no disclosure at all.
    """

    reason: str


class IdentityNumberOut(Schema):
    """A member's identity number, and the record that it was read.

    The disclosure comes back with the number rather than being fetched
    afterwards, so the screen can show who read it and when in the same paint --
    and so that a caller cannot receive the number without also receiving the
    evidence that the read was logged.
    """

    id_number: str
    disclosure: DisclosureOut


class RegisterFilters(Schema):
    """The four narrowings the register offers, all optional.

    Blank and absent mean the same thing -- unfiltered -- because a ``select``
    reset to "any" submits an empty string. The same contract
    ``strains.schemas.CatalogueFilters`` states.

    ``joined_within`` is a number of days and is what makes the *recent
    sign-ups* view a filter rather than a screen of its own. Zero means
    unfiltered, matching the blanks beside it.
    """

    status: str = ''
    role: str = ''
    #: Matched against the name, the nickname and the address -- and, at six
    #: digits or more, against the identity number's blind index, which is
    #: exact-match only and so cannot be used to browse. See
    #: ``administration.register``.
    search: str = ''
    joined_within: int = 0


class MemberRefusedOut(Schema):
    """Why a write against a member was refused, per field where it has one.

    The same shape as ``strains.schemas.RefusedOut`` and
    ``accounts.schemas.ProfileRefusedOut``, deliberately: the frontend already
    knows how to render that, and a third refusal shape would be a third
    renderer.

    ``detail`` carries the refusals that belong to no field -- an erased account,
    a sharing member, an administrator suspending themselves. Those are the
    common case here, unlike on the catalogue, so a screen that only rendered
    ``fields`` would show a blank error for the three most likely refusals.
    """

    detail: str
    fields: dict[str, list[str]] = {}

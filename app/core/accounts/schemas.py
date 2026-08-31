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

    **``status`` and ``membership_status`` are two different questions and the
    frontend needs both.** The first is whether this identity may sign in; the
    second is where their club membership stands, and it is ``None`` for someone
    who has no membership -- a produce-market customer. Before the split there
    was one column answering both, which is why an unpaid registrant could not
    sign in at all. See C27 and ``design/verticals.md`` section 5.

    **Serialising this requires ``User.objects.with_platform_roles()``.** Three
    resolvers below read relationships -- the nickname and the membership status
    from the one-to-one, and ``permissions`` from all three -- and an unloaded
    one means a synchronous query, which is fatal inside the async views in
    ``authn.api``. The narrower ``with_club_membership()`` is not enough.
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
    # Whether this identity may sign in, and nothing else.
    status: str
    # Where the club membership stands, or null for an account that holds none.
    # A member at `pending_payment` or `lapsed` signs in and is sent to the
    # payment screen; the club layout owns that redirect, because the session is
    # already carrying what it needs to decide.
    membership_status: str | None
    # A single word summarising which club destination this account belongs on,
    # derived from the relationships rather than stored. **For routing, never
    # for deciding** -- `permissions` below is the answer to what somebody may
    # do, and this is only the answer to where the front end should send them
    # first.
    #
    # Derived because the column it used to report is gone: one person may
    # administer the club, hold a membership and be appointed to a producer at
    # once (C28), so there is no single true value. Precedence picks the most
    # capable, and the frontend's `clubHomeFor` maps it to a landing page.
    role: str
    # Every `platform.*` action this account holds, sorted. Empty for an
    # inactive account, and the whole catalogue for a superuser.
    permissions: list[str]
    is_staff: bool

    @staticmethod
    def resolve_role(obj):
        """The club destination this account belongs on, most capable first.

        Not a column and not a permission: a routing hint. Somebody who
        administers the club and also holds a membership is sent to the
        administration home, because that is the more capable place and the
        member destinations are reachable from it.

        ``'member'`` is the fallback rather than an assertion -- an account with
        no club relationship at all is a produce-market customer, and the club
        gate turns them away before any of these destinations render.
        """
        for appointment in obj.storefront_appointments.all():
            if appointment.administers_club:
                return 'admin'
        if any(True for _ in obj.producer_appointments.all()):
            return 'cultivator'
        return 'member'

    @staticmethod
    def resolve_nickname(obj):
        """The club nickname, or blank for an account with no membership.

        Reads the relation `with_platform_roles()` loaded. See the class
        docstring on why this is not allowed to issue its own query.
        """
        return obj.club_nickname

    @staticmethod
    def resolve_membership_status(obj):
        """Where the club membership stands, or ``None`` when there is none.

        ``None`` is a real answer rather than a missing one: it is what a
        produce-market customer looks like, and the frontend distinguishes it
        from ``pending_payment`` because one belongs on the market and the other
        owes the club money.
        """
        membership = getattr(obj, 'club_membership', None)
        return membership.status if membership is not None else None

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
    # Whether this identity may sign in. **Not** a role: there is no role column
    # since C28, and this screen shows somebody their own details rather than
    # their authority — `UserOut.permissions` is where that lives, and this
    # payload deliberately carries neither it nor a derived role word.
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


# ----------------------------------------------------------------------
# Creating a store account
# ----------------------------------------------------------------------
# Read and written by `registration_api`, which is unauthenticated. Kept in this
# module rather than in one of its own because a customer *is* a `User` and
# nothing else -- `design/verticals.md` section 6 -- so the schemas that create
# one belong beside the schemas that read one back.


class CustomerRegisterIn(Schema):
    """Exactly what the store's sign-up form collects. Four fields.

    Every value arrives as typed and is normalised server-side; nothing here
    assumes the caller has done it.

    ``mobile`` defaults to the empty string rather than being required, and the
    default is the contract rather than a convenience: the store's form leaves
    the field optional because a wrong number is worse than none, so a
    submission that omits it is a complete submission and not a partial one.

    **What is absent is the schema.** No identity number, no nickname, no
    password, and no ``consents`` -- see ``accounts.registration`` for each, and
    ``registration.ConsentRequired`` for what happens the day the last of those
    has to arrive.
    """

    first_name: str
    last_name: str
    email: str
    mobile: str = ''


class CustomerRegistrationOut(Schema):
    """A registration that was accepted.

    **One field, and the thinness is the point.** No id, no email address, no
    name, nothing that came in. ``membership.schemas.RegistrationOut`` explains
    the reasoning and then has to break it for a checkout token; there is no
    payment here, so this response keeps the rule whole.

    It is byte-identical for an address already on file. What differs between
    the two is what arrives in a mailbox, which only the mailbox's owner sees --
    see ``registration.CustomerRegistration.sign_in_for``.
    """

    detail: str


class CustomerRegistrationRefusedOut(Schema):
    """Why a registration was refused, per field where it has one.

    The same shape as ``ProfileRefusedOut`` -- ``detail`` plus ``fields`` --
    because the store already knows how to render that and a second refusal
    shape would be a second renderer.

    **The values in ``fields`` are machine codes, not sentences, and that is the
    one place this differs from every other refusal on this API.** The store's
    form renders its own wording under each input, keyed on the code, and it
    drops any code it does not recognise -- see ``readSignUpRefusals`` in
    ``frontend/market/lib/sign-up.ts``. Sending prose would put a Django
    message beside the store's own voice on a screen the store designed, and
    matching on prose is how that silently stops working. The codes are mapped
    from the validators' ``code`` in ``registration_api``, which is the only
    module that knows the wire vocabulary.

    ``detail`` stays prose, for a human reading the response directly and for a
    log.
    """

    detail: str
    fields: dict[str, list[str]] = {}

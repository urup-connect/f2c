"""Factories for the relationships that grant, shared by every app's tests.

**This exists because of C28.** Building a test account used to be one call:
``create_user(email=..., nickname=..., role=UserRole.CULTIVATOR)``. One column
said who somebody was, so every app's ``tests/support.py`` could construct one
without knowing about any other app.

There is no column now. A member is a `User` plus an active `ClubMembership`; an
administrator is a `User` plus a `StorefrontStaff` row; a cultivator is a `User`
plus a `ProducerMembership` against a `Producer`. That is three apps' models for
one fixture, and five support modules were about to grow five slightly different
copies of it — which is how two of them end up differing in a way nobody
intended, in exactly the suites that exist to catch that.

It lives in ``f2c`` for the same reason ``f2c.api`` does: this is the one package
that is allowed to know about all of them. An app's ``tests/support.py``
importing from here does not bend the dependency direction the way importing
from a sibling app would.

**Nothing here is a shortcut past the rules.** Each factory writes the rows the
services would write, so a fixture cannot grant something the application
cannot: an inactive account still resolves to no permissions, an unpaid
membership still grants nothing, and a limited appointment still cannot appoint.
"""
from django.contrib.auth import get_user_model

from app.club.membership.models import ClubMembership, MembershipStatus
from app.commerce.producers.models import Producer, ProducerMembership, ProducerRole
from app.core.accounts.models import UserStatus
from app.core.storefronts.models import Storefront, StorefrontStaff

User = get_user_model()

__all__ = [
    'make_account',
    'make_administrator',
    'make_cultivator',
    'make_member',
    'make_producer',
    'make_sharing_placeholder',
]


def make_account(email='person@example.com', *, status=UserStatus.ACTIVE, **extra):
    """A bare identity: somebody who can sign in and belongs to nothing.

    This is a **produce-market customer** — an account and nothing else is what
    buying produce requires. It is also the right starting point for every
    factory below, and the right fixture for asserting that somebody with no
    relationships holds no permissions.

    Active by default. ``permissions_for`` empties the set for an account that
    cannot sign in, so a suspended fixture would be refused for the wrong reason
    and a test asserting a 403 would pass without testing anything.
    """
    return User.objects.create_user(email=email, status=status, **extra)


def make_member(
    email='member@example.com',
    nickname='Thabo',
    *,
    status=MembershipStatus.ACTIVE,
    account=None,
    **extra,
):
    """An identity with a club membership. Returns the ``User``.

    The membership is reachable as ``user.club_membership``.

    ``status`` is the **membership's**, not the account's, and that separation is
    the point of C27. Pass ``MembershipStatus.PENDING_PAYMENT`` for somebody who
    can sign in and owes the club money — a state that could not be constructed
    at all before the split, because it was the account that was blocked.
    """
    user = account or make_account(email, **extra)
    ClubMembership.objects.create(user=user, nickname=nickname, status=status)
    return user


def make_producer(trading_name='Kloof Farm', **extra):
    """A farm, with nobody appointed to it yet.

    A legitimate intermediate state — ``Producer.primary`` returns ``None`` —
    and the right fixture for asserting that an unowned producer cannot be acted
    on.
    """
    return Producer.objects.create(trading_name=trading_name, **extra)


def make_cultivator(
    email='grower@example.com',
    *,
    producer=None,
    role=ProducerRole.PRIMARY,
    account=None,
    trading_name='Kloof Farm',
    **extra,
):
    """Somebody appointed to a producer. Returns ``(user, producer)``.

    Primary by default, because most tests want the appointment that can do
    things. Pass ``ProducerRole.LIMITED`` for the fixture that asserts what an
    appointed hand *cannot* do — appoint staff, set pricing, create a
    placeholder.

    Deliberately **not** given a club membership. A cultivator is not thereby a
    member, and a fixture that quietly made them one would hide the case where
    an endpoint requires the wrong relationship.
    """
    producer = producer or make_producer(trading_name)
    user = account or make_account(email, **extra)
    ProducerMembership.objects.create(producer=producer, user=user, role=role)
    return user, producer


def make_administrator(
    email='admin@example.com',
    *,
    storefront=Storefront.CLUB,
    account=None,
    **extra,
):
    """An administrator of one storefront. Returns the ``User``.

    No club membership, deliberately: an administrator runs the club without
    joining it and pays no subscription. Compose with ``make_member`` — passing
    ``account=`` — for somebody who is both, which is the case a single role
    column could not express.
    """
    user = account or make_account(email, **extra)
    StorefrontStaff.objects.create(user=user, storefront=storefront)
    return user


def make_sharing_placeholder(nickname='Placeholder', *, producer=None):
    """A sharing-member placeholder. Returns the ``User``.

    Not a person — **C6** — so it has no email address, no name and no identity
    number, and its account sits at ``NON_AUTHENTICATING`` so nothing can sign in
    as it. What it has is a nickname the swap zone can show and the producer
    whose stock it holds.
    """
    producer = producer or make_producer('Placeholder Farm')
    # Built through the model rather than `create_user`, which requires an
    # address: a placeholder has none, and that is the whole point of it.
    user = User(email=None, status=UserStatus.NON_AUTHENTICATING)
    user.set_unusable_password()
    user.save()
    ClubMembership.objects.create(
        user=user,
        nickname=nickname,
        status=MembershipStatus.SHARING,
        registered_by=producer,
    )
    return user

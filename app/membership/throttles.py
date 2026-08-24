"""The rate limit on registration, and the reason it is the control that matters.

``POST /api/members/register`` is unauthenticated, because a member has no
account until it succeeds. It is also called server-to-server, by a Next.js
server action rather than by a browser, so there is no session cookie in the
request and no CSRF token to check -- a token would be a value this application
issues to itself, which protects nothing.

What is actually at risk is bulk creation of member rows, and a per-IP limit is
what bounds it. It is deliberately tighter than ``auth_start``: a person joins
a club once, and nothing legitimate registers twice in a minute.
"""
from ninja.throttling import AnonRateThrottle


class RegisterThrottle(AnonRateThrottle):
    scope = 'register'


class NicknameAvailabilityThrottle(AnonRateThrottle):
    """The limit on ``POST /api/members/nickname/availability``.

    Looser than ``register`` because it is called several times in one honest
    sitting -- once each time the nickname field loses focus with a new value in
    it -- and tighter than nothing because the endpoint answers a question about
    another member's record. What it bounds is harvesting the nickname list, not
    a member trying three names before settling on one.

    It is per IP, like every other anonymous limit here, and that is its
    weakness: a determined harvester has more than one address. The disclosure
    is bounded by what the answer contains rather than by this -- one boolean
    about a name the caller already had to type.
    """

    scope = 'nickname_availability'

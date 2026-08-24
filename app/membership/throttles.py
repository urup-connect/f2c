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

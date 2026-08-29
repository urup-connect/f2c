"""How a member proves who they are: passkeys, emailed codes, and sessions.

Members sign in with a passkey and fall back to a code emailed to them. Both
are first-class credentials -- the emailed code is the only route into a new
account, since enrolling a passkey requires an existing session. Password
sign-in is retained for staff, who need it for Django admin.

The layers, outermost first:

``api``
    The HTTP surface, mounted at ``/api/auth/``. Owns all persistence.
``otp``, ``webauthn``
    The two credential services. Neither touches the database except through
    ``models``; ``webauthn`` does not touch it at all.
``throttles``
    Per-IP rate limits on the endpoints that run before a session exists.
``models``
    The credential state, and nothing more -- see the note there on why.

This app depends on ``accounts`` for the member it authenticates, and
``accounts`` does not depend on it.
"""

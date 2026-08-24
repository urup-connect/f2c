"""The member record: who someone is, and the state of their membership.

This app owns ``AUTH_USER_MODEL`` and nothing else. It knows a member's name,
their identity document and where they sit in the membership lifecycle; it does
not know how they prove who they are. Passkeys, emailed codes and the sign-in
endpoints live in ``authn``, which depends on this app and not the other way
round.

The one place that direction is bent is :meth:`accounts.models.User.soft_delete`,
which has to revoke credentials it does not own. It does so through the reverse
relations ``authn`` declares, so there is no import across the boundary -- see
the comment there.
"""

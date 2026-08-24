"""The permission backend that answers for platform actions.

Django's ``has_perm`` asks every backend in ``AUTHENTICATION_BACKENDS`` in turn
and takes the first yes. ``ModelBackend`` answers for ``auth.Permission`` rows;
this answers for the catalogue in ``accounts.roles``, so one call --
``user.has_perm('platform.purchase_plants')`` -- covers both without any caller
having to know which kind of permission it named.

That is the entire reason this exists. The alternative was a bespoke
``user.can(...)`` helper beside ``has_perm``, which would mean two permission
mechanisms, two things for a view decorator to check, and eventually one of them
being forgotten.

It authenticates nobody. ``BaseBackend.authenticate`` returns ``None``, and
nothing here overrides it, so ``ModelBackend`` remains the only backend that can
open a session and the only one a session is ever attributed to. Ordering in
settings puts this second for that reason: credentials above, authority below.
"""
from django.contrib.auth.backends import BaseBackend

from . import roles


class RoleBackend(BaseBackend):
    """Resolves ``platform.*`` permissions from the role catalogue.

    ``BaseBackend`` and deliberately not ``ModelBackend``: the base class is
    only the shape of a backend -- it authenticates nobody and grants nothing --
    while ``ModelBackend`` brings password checking and ``auth.Permission``
    lookups, which are exactly the two things this class exists not to
    duplicate. Inheriting the base rather than reimplementing it also brings the
    ``a``-prefixed async variants Django's async auth stack calls, and those are
    not optional here: every endpoint in ``authn.api`` is ``async def``.

    Only two methods are overridden. Everything else about a backend --
    ``has_perm`` composing the permission set, the async mirrors, the empty
    answer for group permissions -- is already correct in the base class, and
    restating it would only be somewhere for the two to diverge.
    """

    def get_user_permissions(self, user_obj, obj=None):
        """Every platform action this account holds.

        Object-level questions get nothing back rather than falling through to
        the role. A role is a fact about an account, not about that account's
        relationship to one record, so answering an object-level question from
        it would be wrong in the dangerous direction: "may this cultivator edit
        *this* listing" would come back yes for every listing on the platform.
        The rules that genuinely are object-level -- a cultivator's own
        listings, a primary cultivator appointing staff -- arrive with the
        models they are scoped to.

        ``BaseBackend.has_perm`` and ``get_all_permissions`` both route through
        here, so the refusal covers every way the question can be asked.
        """
        if obj is not None:
            return set()
        return set(roles.permissions_for(user_obj))

    def get_group_permissions(self, user_obj, obj=None):
        """Nothing, which is the base class's answer and worth keeping explicit.

        ``User.save`` mirrors the role into a Django group, but the catalogue is
        resolved from the ``role`` column and never from group membership. That
        is deliberate: a group edited by hand, or left behind by a queryset
        ``.update()`` that skipped ``save()``, cannot grant or deny a platform
        action. ``accounts.roles`` says why the group exists at all.
        """
        return set()

    def has_module_perms(self, user_obj, app_label):
        """Only ever true for the pseudo namespace, never for a real app.

        Django uses this to decide whether an app appears in the admin sidebar.
        ``platform`` is not an installed app and has no admin, so a true answer
        here reaches nothing -- but answering for a real app label would put a
        role in charge of admin navigation, which ``is_staff`` owns.
        """
        if app_label != roles.PERMISSION_NAMESPACE:
            return False
        return bool(self.get_user_permissions(user_obj))

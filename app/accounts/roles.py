"""The three roles, and the catalogue of what each one may do.

The role itself lives on ``User.role`` -- one column, one value, enforced by a
check constraint. The catalogue of actions each role carries lives here, in a
dictionary, and that split is the whole design of this module.

**Why the role is a column and not a Django group.** A group is runtime data. A
member of staff can delete one, an account can belong to none or to all three,
and no database constraint can say "exactly one". Roles are not runtime data:
they are a fact about the membership, they change only when this file changes,
and the club's rule is one role per account. A column with choices and a check
constraint says that; a group cannot.

**Why the groups exist anyway.** ``User.save`` mirrors the role into a Django
group of the same name -- see ``User.sync_role_group``. Nothing here reads that
group, and no platform action is granted by it. It exists so that when the
strain, plant and order models arrive, their ordinary Django model permissions
can be attached to a role in one place instead of to every account holding it.
The column is the source of truth; the group is where future model permissions
will hang.

**Why the catalogue is a dictionary and not ``auth.Permission`` rows.** Almost
every action below is against a model that does not exist yet -- there are no
plants, no strains, no batches, no transactions, no swap zone. A
``Permission`` row needs a ``ContentType``, which needs a model, so the
alternative is a fake unmanaged model whose only purpose is to hold permission
rows for tables nobody has written. That buys nothing: these codenames are read
by ``accounts.backends.RoleBackend``, which resolves them from this dictionary
without touching the database, so ``user.has_perm('platform.purchase_plants')``
works today and keeps working when the real models land beside it.

The dictionary being in code rather than in rows has a second benefit worth
naming: the catalogue is the design record. It is reviewed in a diff, it cannot
drift from what a data migration once seeded, and
``design/features/roles-and-permissions.md`` is a prose reading of this file
rather than a second source of truth.

**No database query, ever.** ``permissions_for`` is pure dictionary lookup, and
that is a requirement rather than an optimisation: ``UserOut`` serialises it
inside ``authn.api``'s async views, where a synchronous ORM call raises
``SynchronousOnlyOperation``.

**Actions, not rules.** Two things in the design document are deliberately not
here. "Members are concealed behind a nickname" and "no member may hold more
than four flowering plants" are rules about what the platform does, not
permissions anybody holds or lacks; they belong to the swap and profile
services when those are built. A permission that everybody holds and nobody
can be refused is not a permission.
"""
from django.db import models

#: The pseudo app label every platform action is namespaced under. Django's
#: ``has_perm`` splits a permission on its first dot into an app label and a
#: codename, so these need a namespace of their own. No Django app is called
#: ``platform`` and none should be: the prefix is what tells a reader that the
#: action is resolved from the catalogue below rather than from an
#: ``auth.Permission`` row, and it keeps these clear of the model permissions
#: the real apps will bring with them.
PERMISSION_NAMESPACE = 'platform'


class UserRole(models.TextChoices):
    """What an account is, in the collective's own terms.

    Exactly one per account. ``MEMBER`` is where a completed registration
    leaves everybody -- see ``membership.services.REGISTERED_ROLE`` -- and the
    other two are granted by hand.

    ``ADMIN`` is the club administrator, and it is deliberately **not**
    ``is_staff``. Neither derives from the other: ``is_staff`` opens the Django
    admin, this opens the administrative actions the API exposes, and an
    account can hold either without the other. A back-office login and
    authority over the club's own records are different grants, and the cost of
    keeping them apart is recorded in
    ``design/features/roles-and-permissions.md`` -- there are two places to
    grant privilege, and they can disagree.
    """

    ADMIN = 'admin', 'Admin'
    CULTIVATOR = 'cultivator', 'Cultivator'
    MEMBER = 'member', 'Member'


#: The Django group mirroring each role. Written out rather than derived from
#: the labels above, because a group name is data in a table: migration 0004
#: created these three rows and renaming a label must not orphan them.
ROLE_GROUP_NAMES = {
    UserRole.ADMIN: 'Admins',
    UserRole.CULTIVATOR: 'Cultivators',
    UserRole.MEMBER: 'Members',
}


# ----------------------------------------------------------------------
# The catalogue
# ----------------------------------------------------------------------
# Every action the platform recognises, with the sentence from the design
# document that put it here. Nothing is granted by appearing in this dictionary
# -- ROLE_PERMISSIONS below is what grants -- so an action may be listed and
# held by nobody while the feature it names is being built.

#: Club administration. The collective's own records, and authority over
#: everybody else's.
ADMIN_ACTIONS = {
    'platform.manage_cultivators':
        'Create, read, update and delete cultivators.',
    'platform.manage_strain_catalogue':
        'Create, read, update and delete strain listings platform-wide.',
    'platform.manage_product_types':
        'Create, read, update and delete finished product types and their '
        'prices.',
    'platform.manage_club_rules':
        'Publish and withdraw the club and platform rules.',
    'platform.disable_user':
        'Disable or remove any account.',
    'platform.disable_plant':
        'Disable or remove any plant.',
    'platform.disable_batch':
        'Disable or remove any batch.',
    'platform.refund_transaction':
        'Reverse or refund a transaction in whole or in part, withholding '
        'transaction and platform fees.',
    'platform.hide_cultivator':
        'Hide a cultivator and everything it offers.',
    'platform.revoke_access':
        "Revoke an account's access to the platform.",
    'platform.cancel_membership':
        'Cancel a membership.',
}

#: Cultivation. Everything scoped to the cultivator the account belongs to,
#: never to somebody else's.
CULTIVATOR_ACTIONS = {
    'platform.manage_own_cultivator_profile':
        "Manage the cultivator's own profile.",
    'platform.appoint_cultivator_staff':
        'Appoint other cultivator members, with full or limited rights. Held '
        'by the primary cultivator only, which is an object-level rule this '
        'catalogue cannot express -- see the design document.',
    'platform.manage_plant_stock':
        'Upload plant stock and adjust how many plants are available.',
    'platform.manage_own_pricing':
        'Set pricing, including promotional pricing for a given strain, '
        'period, batch or quantity.',
    'platform.manage_own_strain_listings':
        "Create, read, update and delete the cultivator's own strain "
        'listings: image, description, available finished product types and '
        'price.',
    'platform.manage_sharing_members':
        'Create, read, update and delete sharing members, and manage their '
        'stock.',
    'platform.change_plant_status':
        'Move a plant between preflowering, in bloom, harvested, processed '
        'and shipped.',
    'platform.view_fulfilment_documents':
        'View and print ownership certificates, packing labels and shipping '
        'documents for the courier.',
    'platform.respond_to_reviews':
        'View and respond to reviews and ratings.',
    'platform.request_catalogue_addition':
        'Ask an administrator to list a new strain or finished product type.',
    'platform.record_notes':
        'Record notes against members, strains, plants and subscriptions.',
}

#: Membership. What a member does with their own account and their own plants.
MEMBER_ACTIONS = {
    'platform.manage_own_profile':
        'View and update their own profile details and image.',
    'platform.browse_catalogue':
        'Browse available strains and cultivators, including ratings and '
        'reviews.',
    'platform.purchase_plants':
        'Choose and purchase plants with grow services.',
    'platform.view_own_inventory':
        'View their own plant inventory.',
    'platform.use_swap_zone':
        'Enter and browse the swap zone, and make swaps.',
    'platform.offer_inventory_for_swap':
        'Offer their own plants in the swap zone, and withdraw them again.',
    'platform.submit_reviews':
        'Rate and review the cultivators and plants they have received.',
    'platform.track_orders':
        'Track and trace their orders.',
    'platform.query_orders':
        'Query an order.',
    'platform.submit_support_request':
        'Raise a support request.',
}

#: Every action the platform recognises, in one mapping. Built from the three
#: groups above rather than written a fourth time, so an action cannot be
#: granted below without being described here.
PLATFORM_ACTIONS = {**ADMIN_ACTIONS, **CULTIVATOR_ACTIONS, **MEMBER_ACTIONS}


#: What each role may do. One role per account, so anything a cultivator or an
#: administrator also does as an ordinary person is repeated into their set
#: rather than inherited -- there is no role hierarchy here, and there is
#: deliberately no "everybody" set: an action nobody can be refused is not a
#: permission.
#:
#: The overlaps are the ones the design document states outright. A cultivator
#: browses the catalogue, keeps a profile and raises support requests because
#: the document says cultivators do those things. Neither a cultivator nor an
#: administrator may purchase plants or use the swap zone: the document gives
#: those to members, and one role per account means somebody who does both
#: needs a second account. That cost is recorded as an accepted limitation in
#: ``design/features/roles-and-permissions.md``.
ROLE_PERMISSIONS = {
    UserRole.ADMIN: frozenset(ADMIN_ACTIONS) | frozenset({
        'platform.manage_own_profile',
        'platform.browse_catalogue',
        'platform.record_notes',
        'platform.respond_to_reviews',
    }),
    UserRole.CULTIVATOR: frozenset(CULTIVATOR_ACTIONS) | frozenset({
        'platform.manage_own_profile',
        'platform.browse_catalogue',
        'platform.submit_support_request',
    }),
    UserRole.MEMBER: frozenset(MEMBER_ACTIONS),
}


def permissions_for(user):
    """Every platform action this user holds, as a frozenset of codenames.

    Three refusals come before the role is consulted, and each is the same
    answer Django's own ``ModelBackend`` gives:

    * an anonymous visitor holds nothing;
    * an inactive account holds nothing, which is what makes a suspended or
      erased member powerless without any code having to remember to check
      ``status`` -- ``is_active`` is derived from it and a check constraint
      holds the two together;
    * an active superuser holds everything, because Django's permission
      framework treats a superuser that way and a second rule here would only
      be a place for the two to disagree.

    An unrecognised role resolves to nothing rather than raising. The check
    constraint on ``User.role`` should make that unreachable, and the same
    belt-and-braces argument applies as to ``is_active``: a write that bypasses
    the model should leave an account powerless, never crash the request that
    reads it.

    No query. See the module docstring -- this runs inside async views.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return frozenset()
    if not user.is_active:
        return frozenset()
    if user.is_superuser:
        return frozenset(PLATFORM_ACTIONS)
    return ROLE_PERMISSIONS.get(getattr(user, 'role', ''), frozenset())


def describe(codename):
    """The catalogue's sentence for one action, or ``''`` if it holds none.

    For the admin and for error messages. The dictionary is the design record,
    so anything explaining a refusal should quote it rather than restate it.
    """
    return PLATFORM_ACTIONS.get(codename, '')

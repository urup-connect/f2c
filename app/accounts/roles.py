"""The four roles, the catalogue of what each may do, and what it takes to hold one.

The role itself lives on ``User.role`` -- one column, one value, enforced by a
check constraint. The catalogue of actions each role carries lives here, in a
dictionary, and that split is the whole design of this module.

**Why the role is a column and not a Django group.** A group is runtime data. A
member of staff can delete one, an account can belong to none or to all four,
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

**One role holds nothing, on purpose.** A sharing member is an identity that
holds stock, not somebody who signs in, so ``ROLE_PERMISSIONS`` gives them an
empty set. That is a real entry rather than a missing one, and the catalogue
tests name it as the single permitted exception -- otherwise the next role that
accidentally holds nothing would look like this one.

The last section holds the sharing-member consent wording. It is here rather
than beside the service that records it because ``User`` needs the version label
as a field default, and this module is the one ``models`` already imports.
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
    other three are granted by hand or by a cultivator.

    ``ADMIN`` is the club administrator, and it is deliberately **not**
    ``is_staff``. Neither derives from the other: ``is_staff`` opens the Django
    admin, this opens the administrative actions the API exposes, and an
    account can hold either without the other. A back-office login and
    authority over the club's own records are different grants, and the cost of
    keeping them apart is recorded in
    ``design/features/roles-and-permissions.md`` -- there are two places to
    grant privilege, and they can disagree.

    ``SHARING_MEMBER`` is the odd one, and worth reading twice. It is an
    identity that **holds stock and never signs in**: registered by a
    cultivator with a name, an identity number and a nickname, given flowering
    plants, and present in the swap zone so that members joining a new club
    have something to swap against. It has no email address, so there is
    nothing to authenticate; it sits at ``UserStatus.SHARING``, which a
    constraint keeps out of Active; and it holds no permissions at all.

    It is a ``User`` row all the same, and that is the load-bearing decision. A
    separate model would have meant a second nickname namespace (two people
    could wear one name in the swap zone, which is impersonation), a second
    encrypted identity-number column, a second erasure route for POPIA, and two
    kinds of owner for every plant, swap and ownership certificate. Being a row
    here instead means the club's "one account per identity document" rule
    reaches sharing members for free -- with a cost recorded as a risk in the
    design document, because a refused registration tells the cultivator that
    the identity number is already on file.
    """

    ADMIN = 'admin', 'Admin'
    CULTIVATOR = 'cultivator', 'Cultivator'
    MEMBER = 'member', 'Member'
    SHARING_MEMBER = 'sharing_member', 'Sharing member'


#: The Django group mirroring each role. Written out rather than derived from
#: the labels above, because a group name is data in a table: migrations 0004
#: and 0005 created these rows and renaming a label must not orphan them.
ROLE_GROUP_NAMES = {
    UserRole.ADMIN: 'Admins',
    UserRole.CULTIVATOR: 'Cultivators',
    UserRole.MEMBER: 'Members',
    UserRole.SHARING_MEMBER: 'Sharing members',
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
    'platform.register_sharing_member':
        'Register a sharing member from a name, an identity number and a '
        'nickname, attesting that they consented and were given the '
        'collection notice.',
    'platform.manage_sharing_members':
        'Read, update and withdraw the sharing members this cultivator '
        'registered.',
    'platform.allocate_sharing_member_stock':
        'Allocate flowering plants to a sharing member, up to the '
        'four-plant holding limit, putting them in the swap zone.',
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

#: A sharing member holds nothing, so there is no fourth group of actions. The
#: name exists so that the symmetry of the catalogue is not a lie: three groups
#: and four roles reads like an omission, and this says it is not one.
#:
#: They never sign in -- no email address, and a constraint keeps the role out
#: of Active -- so any action granted here would be unreachable. What happens to
#: their plants is the swap zone's business, and their record is managed by the
#: cultivator who registered them, through ``platform.manage_sharing_members``
#: above.
SHARING_MEMBER_ACTIONS = {}

#: Every action the platform recognises, in one mapping. Built from the groups
#: above rather than written again, so an action cannot be granted below without
#: being described here.
PLATFORM_ACTIONS = {
    **ADMIN_ACTIONS,
    **CULTIVATOR_ACTIONS,
    **MEMBER_ACTIONS,
    **SHARING_MEMBER_ACTIONS,
}


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
    # Deliberately empty, and deliberately present. See
    # `SHARING_MEMBER_ACTIONS`: this role is an identity, not an actor.
    UserRole.SHARING_MEMBER: frozenset(),
}

#: The one role allowed to hold nothing. Named so that the catalogue test can
#: assert every *other* role is non-empty: without it, the next role that
#: accidentally ended up empty would look deliberate.
ROLES_WITHOUT_PERMISSIONS = frozenset({UserRole.SHARING_MEMBER})


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


# ----------------------------------------------------------------------
# The sharing-member attestation
# ----------------------------------------------------------------------
# A sharing member does not register themselves. A cultivator captures their
# name and their identity number, and POPIA needs a lawful basis for holding
# both -- which a person who never saw a form cannot have given by ticking a
# box.
#
# So the cultivator attests, and the attestation is recorded on the record:
# `sharing_consent_attested_by`, `sharing_consent_attested_at` and
# `sharing_consent_version` on `User`, required by a check constraint. That is
# deliberately weaker evidence than a member's own tick in `documents`, and
# calling it an attestation rather than a consent is the point -- it says who
# swore what, and when, rather than pretending the sharing member agreed here.

#: The label recorded against an attestation, so a later revision of the
#: wording below does not silently reinterpret the ones already made. Bumped
#: whenever `SHARING_CONSENT_ATTESTATION` changes in substance; existing records
#: keep the version they were made under.
SHARING_CONSENT_VERSION = '1'

#: What a cultivator is confirming. Written out here so that the form, the
#: admin and the service all quote one wording rather than three paraphrases of
#: it -- and so that a change to it is a reviewable diff against a version
#: number.
SHARING_CONSENT_ATTESTATION = (
    'I confirm that this person has agreed to be registered as a sharing '
    'member of the club, that they were told what personal information is '
    'being collected and why, and that they consented to the club holding '
    'their name and identity number for that purpose.'
)


def describe(codename):
    """The catalogue's sentence for one action, or ``''`` if it holds none.

    For the admin and for error messages. The dictionary is the design record,
    so anything explaining a refusal should quote it rather than restate it.
    """
    return PLATFORM_ACTIONS.get(codename, '')

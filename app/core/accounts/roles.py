"""The catalogue of platform actions, and which relationships grant them.

**There is no role column any more.** There was: one value per account, with a
check constraint saying exactly one. That worked while the club was the whole
platform and stopped working the moment one person could administer a
storefront, hold a club membership and be appointed to two producers at the same
time. C28 retired the column; the catalogue below survived it unchanged in
shape, and what changed is where ``permissions_for`` reads from.

Three relationships grant, and nothing else does:

============================================  ====================================
``membership.ClubMembership``, active only    :data:`MEMBER_PERMISSIONS`
``storefronts.StorefrontStaff``               :data:`CLUB_ADMINISTRATOR_PERMISSIONS`
``cultivators.ProducerMembership``            the three ``PRODUCER_*`` sets
============================================  ====================================

**``is_staff`` grants nothing here, and that is C29.** It opens the Django admin,
which is the platform operator's tier in its entirety and does not consult this
catalogue. Two actions that used to be listed -- refunding a transaction and
cancelling a membership -- went with that decision: an action in this dictionary
is one an API endpoint checks, and those are done by hand in the admin.

**The groups are gone too.** ``User.save`` used to mirror the role into a Django
group of the same name. Nothing read it, no platform action was granted by it,
and it existed so that future model permissions would have somewhere to hang.
With no column to mirror there is nothing to keep them in step with, and a group
that drifts is worse than no group -- ``design/migrations.md`` section 3.3 has
the decision.

**Why the catalogue is a dictionary and not ``auth.Permission`` rows.** Almost
every action below is against a model that does not exist yet -- no orders, no
swap zone, no reviews. A ``Permission`` row needs a ``ContentType``, which needs
a model, so the alternative is a fake unmanaged model whose only purpose is to
hold permission rows for tables nobody has written. These codenames are read by
``accounts.backends.RoleBackend`` instead, so
``user.has_perm('platform.purchase_plants')`` works today and keeps working when
the real models land beside it.

The dictionary being in code has a second benefit worth naming: the catalogue is
the design record. It is reviewed in a diff, it cannot drift from what a data
migration once seeded, and ``design/features/roles-and-permissions.md`` is a
prose reading of this file rather than a second source of truth.

**No database query, ever.** ``permissions_for`` reads relations that must
already be loaded -- ``User.objects.with_platform_roles()`` -- and that is a
requirement rather than an optimisation: ``UserOut`` serialises the result inside
``authn.api``'s async views, where a lazy relation raises
``SynchronousOnlyOperation``.

**Actions, not rules.** Two things in the design document are deliberately not
here. "Members are concealed behind a nickname" and "no member may hold more
than four flowering plants" are rules about what the platform does, not
permissions anybody holds or lacks; they belong to the swap and profile services
when those are built. A permission that everybody holds and nobody can be
refused is not a permission.

**Object-level rules are now expressible, and are still not expressed here.**
"May this person set pricing" is answered below. "May they set pricing on *this*
listing" is answered by the same ``ProducerMembership`` rows, in the service that
owns the record -- which is the half C13 and roles risk 9 said had nothing to
point at. It has something to point at now.
"""
#: The pseudo app label every platform action is namespaced under. Django's
#: ``has_perm`` splits a permission on its first dot into an app label and a
#: codename, so these need a namespace of their own. No Django app is called
#: ``platform`` and none should be: the prefix is what tells a reader that the
#: action is resolved from the catalogue below rather than from an
#: ``auth.Permission`` row, and it keeps these clear of the model permissions
#: the real apps will bring with them.
PERMISSION_NAMESPACE = 'platform'


# ----------------------------------------------------------------------
# The catalogue
# ----------------------------------------------------------------------
# Every action the platform recognises, with the sentence from the design
# document that put it here. Nothing is granted by appearing in this dictionary
# -- ROLE_PERMISSIONS below is what grants -- so an action may be listed and
# held by nobody while the feature it names is being built.

#: Club administration. The collective's own records, and authority over
#: everybody else's. Held through a ``storefronts.StorefrontStaff`` row for the
#: club, never as a property of an account.
#:
#: **Two actions that used to be here are not, and their absence is C29.**
#: ``platform.refund_transaction`` and ``platform.cancel_membership`` belong to
#: the UC tier, which has no Next.js surface and no endpoint: the platform
#: operator does both in the Django admin, gated by ``is_staff``. An action in
#: this catalogue is one an API endpoint checks, and neither of those is.
ADMINISTRATOR_ACTIONS = {
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
    'platform.hide_cultivator':
        'Hide a cultivator and everything it offers.',
    'platform.revoke_access':
        "Revoke an account's access to the platform.",
}

#: Production. Everything scoped to the producer the appointment belongs to,
#: never to somebody else's. Held through a ``cultivators.ProducerMembership``
#: row, which is also what finally makes the "their own" half enforceable --
#: see ``permissions_for`` and C13.
PRODUCER_ACTIONS = {
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
        'Create a sharing-member placeholder from a nickname, so flowering '
        'stock can be put into the swap zone. C6: a placeholder, not a '
        'person, so no identity number and no attestation.',
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

#: Every action the platform recognises, in one mapping. Built from the groups
#: above rather than written again, so an action cannot be granted below without
#: being described here.
PLATFORM_ACTIONS = {
    **ADMINISTRATOR_ACTIONS,
    **PRODUCER_ACTIONS,
    **MEMBER_ACTIONS,
}


#: What an administrator of the **club** holds. The overlaps with the member
#: set are the ones the design document states outright: an administrator
#: browses the catalogue and keeps a profile because the document says they do.
#:
#: There is no hierarchy. Somebody who administers the club and also holds a
#: membership gets both sets, which is the whole point of the split -- under the
#: old single-column model that person needed two accounts, and the cost was
#: recorded as an accepted limitation in the design document. It is no longer a
#: limitation and the note has gone with it.
CLUB_ADMINISTRATOR_PERMISSIONS = frozenset(ADMINISTRATOR_ACTIONS) | frozenset({
    'platform.manage_own_profile',
    'platform.browse_catalogue',
    'platform.record_notes',
    'platform.respond_to_reviews',
})

#: What administering the **market** holds. Empty, and deliberately present: the
#: market's own actions arrive with the market vertical, and a missing key here
#: would read as an oversight rather than as a feature that does not exist yet.
MARKET_ADMINISTRATOR_PERMISSIONS = frozenset()

#: What an active club membership holds.
MEMBER_PERMISSIONS = frozenset(MEMBER_ACTIONS)

#: What any appointment to a producer holds, whatever its rights.
PRODUCER_BASE_PERMISSIONS = frozenset({
    'platform.manage_plant_stock',
    'platform.change_plant_status',
    'platform.view_fulfilment_documents',
    'platform.manage_own_profile',
    'platform.browse_catalogue',
    'platform.submit_support_request',
    'platform.record_notes',
})

#: What full rights add: the commercial decisions, as against moving stock.
PRODUCER_FULL_PERMISSIONS = frozenset({
    'platform.manage_own_cultivator_profile',
    'platform.manage_own_pricing',
    'platform.manage_own_strain_listings',
    'platform.respond_to_reviews',
    'platform.request_catalogue_addition',
    'platform.allocate_sharing_member_stock',
})

#: What only the primary may do. ``member-roles`` is explicit: only the primary
#: appoints staff and registers sharing members. That used to be an object-level
#: rule this catalogue could not express -- C13 and roles risk 9 -- and it is now
#: a column on the appointment being read a few lines below.
PRODUCER_PRIMARY_PERMISSIONS = frozenset({
    'platform.appoint_cultivator_staff',
    'platform.register_sharing_member',
    'platform.manage_sharing_members',
})


def permissions_for(user):
    """Every platform action this user holds, as a frozenset of codenames.

    **This used to read one column and now reads three relationships**, which is
    the whole of C28. One person may administer a storefront, hold a club
    membership and be appointed to two producers at once; a column could say
    only one of those, and the design document carried the resulting limitation
    -- "somebody who does both needs a second account" -- as accepted. It is
    accepted no longer.

    Three refusals come first, and each is the same answer Django's own
    ``ModelBackend`` gives:

    * an anonymous visitor holds nothing;
    * an inactive account holds nothing, which is what makes a suspended or
      erased person powerless without any code having to remember to check
      ``status`` -- ``is_active`` is derived from it and a check constraint holds
      the two together;
    * an active superuser holds everything, because Django's permission
      framework treats a superuser that way and a second rule here would only be
      a place for the two to disagree.

    Note what grants nothing: ``is_staff``. It opens the Django admin and is the
    UC tier in its entirety -- C29 -- and the Django admin does not consult this
    catalogue.

    **No query, and that is a requirement rather than an optimisation.** This
    runs inside the async views in ``authn.api``, where a lazy relation is not
    slow but fatal: ``SynchronousOnlyOperation``. Every relation read below has
    to have been loaded by ``User.objects.with_platform_roles()`` first. The
    failure is loud on purpose; the alternative was a resolver that quietly
    returns an empty set when the relations are absent, which would sign a
    member out of their own permissions with nothing to explain why.
    """
    if user is None or not getattr(user, 'is_authenticated', False):
        return frozenset()
    if not user.is_active:
        return frozenset()
    if user.is_superuser:
        return frozenset(PLATFORM_ACTIONS)

    granted = set()

    # The club membership. Only an active one grants anything: a member who has
    # not paid signs in -- C27 -- and reaches the payment screen, not the club.
    membership = getattr(user, 'club_membership', None)
    if membership is not None and membership.may_use_the_club:
        granted |= MEMBER_PERMISSIONS

    # Administering a storefront. Asked of the appointment rather than compared
    # against a string here, so this module needs no import from `storefronts`
    # and the dependency stays one-directional.
    for appointment in user.storefront_appointments.all():
        granted |= (
            CLUB_ADMINISTRATOR_PERMISSIONS
            if appointment.administers_club
            else MARKET_ADMINISTRATOR_PERMISSIONS
        )

    # Appointments to producers. The sets accumulate: somebody appointed to two
    # farms, once with full rights and once limited, holds full rights -- at the
    # farm that granted them. **Which farm is not decided here.** This answers
    # "may this person set pricing at all"; "may they set pricing on *this*
    # listing" is the object-level question, and it is answered by the same
    # appointment rows, in the services that own the record. C13.
    for appointment in user.producer_appointments.all():
        granted |= PRODUCER_BASE_PERMISSIONS
        if appointment.has_full_rights:
            granted |= PRODUCER_FULL_PERMISSIONS
        if appointment.is_primary:
            granted |= PRODUCER_PRIMARY_PERMISSIONS

    return frozenset(granted)


def describe(codename):
    """The catalogue's sentence for one action, or ``''`` if it holds none.

    For the admin and for error messages. The dictionary is the design record,
    so anything explaining a refusal should quote it rather than restate it.
    """
    return PLATFORM_ACTIONS.get(codename, '')

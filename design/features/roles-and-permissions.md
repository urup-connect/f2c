# Roles and permissions

What an account is allowed to do, where that comes from, and where each part of it is enforced.

## 1. Executive summary

**There is no role column.** There was: one value per account — Admin, Cultivator, Member, Sharing
member — with a check constraint saying exactly one. It worked while the club was the whole platform
and stopped working the moment one person could administer a storefront, hold a club membership and
be appointed to two producers at the same time. **C28** retired it.

What an account may do is now resolved from **three relationships**:

| Relationship | Grants |
| --- | --- |
| `membership.ClubMembership`, active only | The member set |
| `storefronts.StorefrontStaff` for the club | The administrator set |
| `cultivators.ProducerMembership` | A base set, plus full rights, plus the primary's |

The catalogue of what each of those means is still a **dictionary in code**
(`app/core/accounts/roles.py`), still resolved through a Django authentication backend, so
`user.has_perm('platform.purchase_plants')` works today — before most of the models those actions
operate on exist. That much survived the change unaltered.

Almost every action below is against a plant, a strain, a batch, an order or a swap, and none of
those are built. So what is delivered is the foundation and the design record: the catalogue, the
enforcement path, and the API payload the frontend renders navigation from. Section 13 is explicit
about what that leaves out.

Four things are worth reading before the tables:

- **Authority is not identity.** `User.status` says whether this identity may sign in. Nothing on
  the account says what it may do. An inactive account holds no permissions at all, so suspension
  and erasure need no knowledge of the catalogue to remain safe.
- **Authority is not membership.** A member who has not paid signs in perfectly well and holds
  nothing — the membership is `pending_payment`, and only an active one grants. **C27**.
- **`is_staff` is the platform operator's tier, entire.** It opens the Django admin and grants
  nothing in this catalogue. There is no `uc_admin`, no fifth role, and no third administrative
  front end — **C29**, section 9.
- **A relationship need not be an actor.** A sharing member is a placeholder holding stock so the
  swap zone is not empty. It holds nothing and signs in nobody, and section 3 is about that alone.

## 2. The three relationships that grant

| Relationship | Who it is | How it is granted |
| --- | --- | --- |
| `ClubMembership` | Somebody who buys, owns and swaps plants | Every completed registration, active once paid |
| `StorefrontStaff` (club) | A club administrator: authority over the collective's own records | By hand in the Django admin |
| `StorefrontStaff` (market) | A produce-market administrator | By hand in the Django admin |
| `ProducerMembership` | A grower or farmer, primary or appointed staff | By an administrator, or by the producer's primary |
| `ClubMembership` at `sharing` | A placeholder holding flowering plants. Signs in nobody | Created by a cultivator |

**One person may hold several at once, and that is the point of the change.** An administrator who
also buys plants holds the union of both sets. Under the column that person needed two accounts, and
the cost was carried in this document as an accepted limitation — see section 5, where the
limitation and its removal are both recorded.

`createsuperuser` grants none of them. It creates an `is_staff` account, which is the platform
operator's tier in full; administering the club is a `StorefrontStaff` row somebody grants
deliberately.

## 3. The sharing member

A new club has a swap zone with nothing in it, and a swap zone with nothing in it is not a feature.
So cultivators create **sharing members**: a nickname, and flowering plants held against it, so the
zone has stock for members to choose against.

**C6 decided what one is: a placeholder, not a person.** The build had committed to the other
reading — a real individual with a name, an identity number and a POPIA attestation — and most of
this section used to describe that machinery. It is gone. What follows records both the decision and
what it removed, because the removed half is the more instructive one.

### 3.1 They are a `User` row, and two of the four reasons no longer apply

A sharing member has no email address, no password, no subscription and no permissions. Every
instinct says put them in their own table. The instinct was rejected on four arguments, and honesty
requires noting that C6 knocked out two of them:

- **One nickname namespace.** *Still holds.* The swap zone shows nicknames and nothing else. A
  separate table means a placeholder and a member could wear the same name in the same list, which
  is impersonation rather than a collision.
- **One kind of owner.** *Still holds, and is now the strongest of the four.* Plants, swaps,
  ownership certificates and packing labels all point at whoever holds the plant. Two owner types
  means every one of those grows a nullable pair of foreign keys and a "which is it" check at every
  call site.
- **One encrypted identity column.** *Gone.* A placeholder has no identity number, so there is no
  second AES column and no second blind index to get wrong.
- **One erasure route.** *Gone.* A placeholder holds no personal data, so there is nothing to erase.

Two arguments are enough, and the decision stands. It is recorded this way rather than quietly
rewritten because the two that fell away were doing real work in the original reasoning, and a
reader who finds only the surviving two will wonder why the question was ever close.

### 3.2 They sign in nobody, and the database still says so

A placeholder's account sits at `UserStatus.NON_AUTHENTICATING`. The value is named for the fact the
authentication stack needs — this row authenticates nobody — rather than for the club concept on top
of it, so that whatever the swap zone eventually makes of a placeholder, the column does not need
renaming.

Two mechanisms, not one:

- It holds no email address, so there is nothing for `authenticate` to match.
- `is_active` is derived from `status` under the `user_is_active_matches_status` check constraint,
  and `NON_AUTHENTICATING` is not `ACTIVE`. So the row cannot be active, in SQL, whatever anybody
  types into a form.

The second exists because the first is a property of the *data*: somebody typing an address into the
admin, or a fixture supplying one, would otherwise turn stock into a sign-in-capable account.

This is simpler than what it replaces. There used to be a dedicated
`sharing_member_never_signs_in` constraint over the role and the status together; with the role
column gone, the general `is_active`-follows-`status` rule already says it. `User.activate()` also
refuses `NON_AUTHENTICATING` outright, so a bulk admin action reports something useful instead of
failing on an index name.

### 3.3 What C6 removed, and why it was removed now

Three columns and a rule went out of the schema:

| Removed | Why |
| --- | --- |
| `sharing_consent_attested_by` / `_at` / `_version` | A placeholder consents to nothing and is given no collection notice. An attestation over one recorded a ceremony around a fiction |
| The identity number | Not collected. Holding one for a person who is not being registered as a person is personal data gathered for no lawful purpose |
| The age rule read off the document | There is no document and nobody to be under age |
| `sharing_member_is_complete` | Required the attestation and a nickname. Now `sharing_member_has_a_cultivator`, requiring only the cultivator whose stock it holds |

**The timing was the decision, not just the content.** C6's own recommendation warned that unwinding
"real people" later means a migration that deletes stored identity numbers. Block 0.5 dropped the
development database and cleared every migration, so the deletion was free exactly once — and would
have cost that migration the moment the columns were written into the new initial schema. Adding
columns back to a defined feature is ordinary work; deleting columns that have held encrypted
identity numbers is not.

What survives is `registered_by`, naming the cultivator whose stock the placeholder holds, and the
nickname the swap zone displays. Both are on `ClubMembership`.

**C7 is changed by this and not resolved.** The legal question was whether allocating four flowering
plants to a named adult who never consented is lawful. With nobody being allocated anything, the
question becomes whether the club may hold that stock itself, above whatever ceiling applies to it.
Still a legal opinion, still gating the swap zone, different brief.

### 3.4 The refusal that leaked — closed

This section used to describe an unavoidable disclosure: one account per identity document is
enforced on a unique blind index, so a cultivator registering somebody already on file was refused,
and the refusal told them that identity number was known to the club. The wording was made
deliberately vague and the leak was carried as risk 4.

**It is gone, because no identity number is collected.** There is nothing to collide with and
nothing to disclose. Risk 4 is closed, and the disappearance is worth noticing: it was not solved,
it was dissolved by a decision taken for unrelated reasons.

One nickname collision remains possible and is disclosed on purpose, exactly as it is at sign-up: a
nickname is a claim against other people in the swap zone, so a taken one has to be replaced, and
knowing it is spoken for reveals nothing about who holds it.

### 3.5 The four plants

`services.SHARING_MEMBER_PLANT_ALLOCATION` is `4` — the same limit members live under, which is why
it is one number and not two. `register_sharing_member` returns it so a caller does not hard-code it.

It is **enforced nowhere**, because there is no plant to count, and under C6 it is no longer even
obviously the right number: the limit exists per person, and a placeholder is not one. What a
placeholder may hold is the swap zone's to define, and is deliberately not guessed at here.

### 3.6 Who may create one

`platform.register_sharing_member` and `platform.manage_sharing_members` belong to the **primary
producer appointment alone** — not to appointed staff, and not to the club administrator.

That is a change, and it is C13 being closed rather than a new rule. `member-roles` always said only
the primary appoints staff and registers sharing members; under the role column that was an
object-level rule the catalogue could not express, so the actions went to every cultivator and the
gap was carried as risk 9. `ProducerMembership.is_primary` is now a column, read in
`permissions_for`, and the rule is enforced.

Not granting it to administrators is deliberate and unchanged: creating accounts for other people is
the one thing on this platform that should have exactly one route. An administrator who has to fix a
placeholder does it in the Django admin.

The service asks for the **permission**, never for a relationship. So a superuser works, and any
future grant works, without `register_sharing_member` changing. Authority is gated on status for
free: `permissions_for` refuses an inactive account before it looks at anything.

## 4. Why not a column, and where the groups went

The column was the right answer to the question as it stood, and this section keeps both halves.

**What the column was for.** A Django group is runtime data: a member of staff can delete one, an
account can belong to none or to all of them, and no database constraint can express "exactly one".
A role, as the club then understood it, was not runtime data — it changed only when
`accounts/roles.py` changed, and the rule was one per account. A column with `choices` and a check
constraint said that; a group could not.

**What broke it.** The rule was wrong, not the mechanism. With a produce market, a producer
organisation and administrators who are not members, one person is routinely three things at once. A
column cannot say that, and neither can a group — what says it is a row per relationship, with a
unique constraint on the pair. Each of the three tables has one.

**The groups are gone.** `User.save` used to mirror the role into a Django group of the same name,
and migrations 0004 and 0005 seeded the rows. Nothing read them and no platform action was granted
by one; they existed so that when the strain, plant and order models arrived their ordinary Django
model permissions could be attached in one place. With no column to mirror there is nothing to keep
them in step with, and a group that drifts is worse than no group. `design/migrations.md` section
3.3 records the decision, taken while the migrations were being regenerated. **Risk 3 is closed with
them.**

Model permissions, when they arrive, hang off the relationship tables the same way platform actions
now do.

## 5. Many relationships, and what that fixed

This section used to be headed *Exactly one role, and what that costs*, and the cost was:

> **A cultivator is not also a buyer.** Neither the Cultivator nor the Admin role carries
> `platform.purchase_plants`, `platform.use_swap_zone` or `platform.offer_inventory_for_swap`.
> Somebody who both grows and buys needs a second account.

There was a test asserting it, which read oddly until the reason was clear: the tempting fix was to
quietly widen the cultivator set, and that would have changed the club's rule without anybody
deciding to.

**The limitation is gone, and it was not removed by widening any set.** The sets are unchanged. What
changed is that a person may hold more than one relationship, so somebody who administers the club
and also holds a membership resolves to exactly the union of the two — verified rather than assumed.
Nobody decided that cultivators may buy; it became possible for one human being to be both a
cultivator and a member, which is what the club meant all along. **Risk 2 is closed.**

One thing the old rule did that nothing now does: a person could not be a member and a sharing
member at once, because one identity document meant one account. Under C6 a placeholder is not a
person and holds no identity document, so the question no longer arises. Converting a placeholder
into a member is not a conversion at all — a joining member is a new account, and the placeholder is
a record the club made.

## 6. The permission catalogue

Every action lives in `app/core/accounts/roles.py` as a codename and the sentence that put it there. The
codenames are namespaced `platform.*`: Django splits a permission on its first dot to find an app
label, and no installed app is called `platform`, which is what marks these as catalogue actions
rather than `auth.Permission` rows.

### 6.1 Why a dictionary rather than permission rows

Almost every action is against a model that does not exist — no orders, no swap zone, no reviews. A
`Permission` row needs a `ContentType`, which needs a model, so the alternative is a fake unmanaged
model whose only purpose is to hold permission rows for tables nobody has written. That buys
nothing: `RoleBackend` resolves these from the dictionary, so `has_perm` works today and keeps
working when the real models land beside it.

The dictionary being in code has a second benefit worth naming: the catalogue is the design record.
It is reviewed in a diff, it cannot drift from what a data migration once seeded, and this document
is a prose reading of that file rather than a second source of truth.

### 6.2 Club administration

`ADMINISTRATOR_ACTIONS`, granted by a `StorefrontStaff` row for the club.

| Action | What it permits |
| --- | --- |
| `platform.manage_cultivators` | Create, read, update and delete cultivators |
| `platform.manage_strain_catalogue` | Create, read, update and delete strain listings platform-wide |
| `platform.manage_product_types` | Create, read, update and delete finished product types and their prices |
| `platform.manage_club_rules` | Publish and withdraw the club and platform rules |
| `platform.disable_user` | Disable or remove any account |
| `platform.disable_plant` | Disable or remove any plant |
| `platform.disable_batch` | Disable or remove any batch |
| `platform.hide_cultivator` | Hide a cultivator and everything it offers |
| `platform.revoke_access` | Revoke an account's access to the platform |

`CLUB_ADMINISTRATOR_PERMISSIONS` adds four member-facing actions the design document gives
administrators outright: `manage_own_profile`, `browse_catalogue`, `record_notes` and
`respond_to_reviews`.

**Two actions that used to be here are not, and their absence is C29.**
`platform.refund_transaction` and `platform.cancel_membership` are the platform operator's, done in
the Django admin under `is_staff`. An action in this catalogue is one an API endpoint checks, and
neither of those is one. Two navigation destinations pointed at them and have gone with them — the
frontend contract test in `club-navigation.test.ts` failed on both the moment the codenames left the
file, which is that test doing precisely its job.

`MARKET_ADMINISTRATOR_PERMISSIONS` is an empty frozenset, and deliberately present: the market's own
actions arrive with the market vertical, and a missing key would read as an oversight rather than as
a feature that does not exist yet.

### 6.3 Production

`PRODUCER_ACTIONS`, granted by a `ProducerMembership` row and split three ways by the rights on it.

`PRODUCER_BASE_PERMISSIONS` — any appointment, however limited:

| Action | What it permits |
| --- | --- |
| `platform.manage_plant_stock` | Upload plant stock and adjust how many plants are available |
| `platform.change_plant_status` | Move a plant between preflowering, in bloom, harvested, processed and shipped |
| `platform.view_fulfilment_documents` | View and print ownership certificates, packing labels and shipping documents |
| `platform.manage_own_profile` | View and update their own profile details and image |
| `platform.browse_catalogue` | Browse available strains and cultivators |
| `platform.submit_support_request` | Raise a support request |
| `platform.record_notes` | Record notes against members, strains, plants and subscriptions |

`PRODUCER_FULL_PERMISSIONS` — what full rights add. The commercial decisions, as against moving
stock:

| Action | What it permits |
| --- | --- |
| `platform.manage_own_cultivator_profile` | Manage the producer's own public profile |
| `platform.manage_own_pricing` | Set pricing, including promotional pricing |
| `platform.manage_own_strain_listings` | CRUD the producer's own strain listings |
| `platform.respond_to_reviews` | View and respond to reviews and ratings |
| `platform.request_catalogue_addition` | Ask an administrator to list a new strain or product type |
| `platform.allocate_sharing_member_stock` | Allocate flowering plants to a placeholder |

`PRODUCER_PRIMARY_PERMISSIONS` — the primary appointment alone:

| Action | What it permits |
| --- | --- |
| `platform.appoint_cultivator_staff` | Appoint other people to this producer, with full or limited rights |
| `platform.register_sharing_member` | Create a sharing-member placeholder |
| `platform.manage_sharing_members` | Read, update and withdraw this producer's placeholders |

The primary holds all three sets. Being the primary is *more than* full rights, not an alternative
to them.

### 6.4 Membership

`MEMBER_PERMISSIONS`, granted by an **active** `ClubMembership` and by nothing else.

| Action | What it permits |
| --- | --- |
| `platform.manage_own_profile` | View and update their own profile details and image |
| `platform.browse_catalogue` | Browse available strains and cultivators, including ratings and reviews |
| `platform.purchase_plants` | Choose and purchase plants with grow services |
| `platform.view_own_inventory` | View their own plant inventory |
| `platform.use_swap_zone` | Enter and browse the swap zone, and make swaps |
| `platform.offer_inventory_for_swap` | Offer their own plants in the swap zone, and withdraw them |
| `platform.submit_reviews` | Rate and review the cultivators and plants they have received |
| `platform.track_orders` | Track and trace their orders |
| `platform.query_orders` | Query an order |
| `platform.submit_support_request` | Raise a support request |

**Active only.** A membership at `pending_payment` or `lapsed` grants none of these, which is what
makes the pay-now redirect honest: the member signs in, reaches a screen asking them to pay, and
holds nothing until they do. Verified rather than assumed.

### 6.5 A placeholder holds nothing

There is no set for a sharing member and no key naming one. Under the role column there was an
empty `SHARING_MEMBER_ACTIONS` dictionary and a `ROLES_WITHOUT_PERMISSIONS` guard, so that an empty
role could not be confused with a mistake. Neither is needed now: a placeholder holds nothing
because it has no active membership and no appointment, which is the ordinary answer for any account
with no relationships rather than a special case.

### 6.6 Two rules that are deliberately not permissions

The brief contains two requirements that are **not** in the catalogue, because a permission that
everybody holds and nobody can be refused is not a permission. They are recorded here so they are
not lost:

**Members are concealed behind a nickname.** Other members see a nickname, never a legal name. This
is a property of the payloads the API returns, not a grant. `accounts.schemas.UserOut` is the
signed-in member's own record and so may carry their own name; any endpoint that returns *another*
member must expose `display_name` and nothing else. There is no such endpoint yet, which is exactly
why this is written down.

**Nobody may hold more than four flowering plants.** The system prompts a member to swap a flowering
plant for a pre-flowering one when they approach the limit, and refuses a swap that would breach it.
It is an invariant of the swap service, enforced on the write, and it belongs with the plant and
swap models when they are built.

## 7. How a permission is checked

`app/core/accounts/backends.py` registers `RoleBackend` second in `AUTHENTICATION_BACKENDS`, after
`ModelBackend`. Django asks each backend in turn and takes the first yes, so **one call covers both
kinds of permission**:

```python
user.has_perm('platform.purchase_plants')   # the catalogue, via RoleBackend
user.has_perm('accounts.change_user')       # an auth.Permission row, via ModelBackend
```

That is the entire reason it is a backend rather than a helper. A bespoke `user.can(...)` beside
`has_perm` would mean two permission mechanisms, two things for a view decorator to check, and
eventually one of them being forgotten.

Four properties of the resolution:

**It authenticates nobody.** `RoleBackend` subclasses `BaseBackend` and does not override
`authenticate`, so `ModelBackend` remains the only backend that can open a session and the only one
a session is attributed to. Ordering puts credentials above authority.

**It answers in async views too.** Every endpoint in `authn/api.py` is `async def`, and Django's
async auth stack calls `ahas_perm`. Subclassing `BaseBackend` rather than reimplementing the backend
protocol is what supplies those.

**It issues no query — and that is now a requirement on the caller.** `permissions_for` reads three
relationships. Loaded, it is pure attribute access; unloaded, it is three queries per account, and
inside those async views it is not slow but fatal: `SynchronousOnlyOperation`.
`User.objects.with_platform_roles()` — `select_related` on the membership, `prefetch_related` on both
appointment sets — is how, and every endpoint returning `UserOut` uses it.

The failure being loud is deliberate. The alternative was a resolver returning an empty set when the
relations are absent, which would sign a member out of their own permissions with nothing to explain
why.

**Object-level questions are still refused here, and are now answerable elsewhere.**
`has_perm(perm, obj)` returns `False` rather than falling through, because "may this cultivator edit
*this* listing" answered from a person-level set would come back yes for every listing on the
platform. What changed is that the question now has somewhere to go: `ProducerMembership` rows are a
join, and the services that own each record make it. Section 13 lists what is still to be written.

## 8. Status, membership and authority answer different questions

`permissions_for` refuses in this order:

1. An anonymous visitor holds nothing.
2. An **inactive** account holds nothing, whatever it is related to.
3. An active **superuser** holds everything, because Django's permission framework treats a
   superuser that way and a second rule here would only be a place for the two to disagree.
4. Otherwise, the union of what its relationships grant.

Step 2 is the load-bearing one. `is_active` is derived from `status` and held to it by a check
constraint (`design/backend.md` section 3.1), so suspension and erasure make an account powerless
without either of them having been taught about permissions.

**There is now a second gate below it, and the two are not the same.** `User.status` decides whether
somebody may sign in; `ClubMembership.status` decides whether the club is open to them. An unpaid
member passes the first and fails the second: they sign in, hold no member permissions, and the club
layout sends them to the payment screen. Before C27 those were one column, which is why a produce
customer could not sign in at all.

`soft_delete` leaves the relationships standing. They are facts about the collective's own structure
— that this cultivator grew what the batch records say it grew — rather than personal data about the
person, and they confer nothing on an account erasure has left Inactive.

Changing a relationship does **not** cut live sessions, unlike `deactivate`. A session carries no
cached permissions; every request resolves them afresh. What can lag is a page already rendered in a
browser, which is a refresh rather than a privilege.

## 9. `is_staff` is the platform operator, entire

`is_staff` opens `/admin/`. It grants nothing in this catalogue and never appears in a
`platform.*` check.

C2 decided the platform has two administrative tiers: the club administrator who runs the club day
to day, and the UC administrator who holds the money, the administrator accounts and the
escalations. C5 decided the administrative portal is Next.js "with the Django admin retained as the
operator's tool". Read together, those left one question unanswered: which tier gets which surface.

**C29 answers it.** Next.js carries one administration area per storefront and no third. Everything
the UC tier does is done in the Django admin: money, refunds, subscription cancellation,
administrator accounts, escalations, and anything reaching across both storefronts. A third
administrative front end would be a month of work reproducing what `django.contrib.admin` already
does, on the one surface whose entire audience is a handful of trusted staff.

What this changed in practice: `uc_admin` was never built, two actions left the catalogue, and
`createsuperuser` takes no role argument — it creates a staff account, which is the whole of what
the tier is.

**The old cost is smaller but not zero.** This document used to record, as risk 1, that privilege
was granted in two places — `role` and `is_staff` — and that they could disagree. There is no role
column to disagree with now. What remains is that `is_staff` and a `StorefrontStaff` row are
different grants made in the same admin, and somebody may hold either alone: a bookkeeper who needs
the admin but runs nothing, an administrator who works only through the member-facing application.
That is intended rather than accidental, and it is a much narrower statement than the one it
replaces.

## 10. Where each relationship comes from

| Relationship | Route | Written by |
| --- | --- | --- |
| `ClubMembership`, pending payment | Sign-up | `membership.services.register_member` |
| `ClubMembership`, active | A payment landing | `payments.services._activate_membership` |
| `ClubMembership`, sharing | A producer's primary | `accounts.services.register_sharing_member` |
| `ProducerMembership` | By hand, or by the producer's primary | The Django admin |
| `StorefrontStaff` | By hand | The Django admin |
| `is_staff` | By hand, or `createsuperuser` | The Django admin, `UserManager.create_superuser` |

`membership.services.REGISTERED_MEMBERSHIP_STATUS` is `pending_payment`. Registration writes the
account and the membership in one transaction, along with the document agreements and the
subscription: a membership at pending payment with no subscription has no way to leave that status,
and a subscription with no member is a mandate against nobody, so either all four exist or none do.

`register_sharing_member` lives in `accounts`, not in `membership`, and the distinction is not
cosmetic. `membership` exists because turning a submission into a member spans `accounts` and
`documents`, which must not know about each other; creating a placeholder spans nothing, and a
placeholder is not a membership in any sense but the table it is stored in.

A registered member holds a membership row and **no permissions at all** until a payment activates
it. Both halves are tested, because a row in the table and authority in the hand are different
things and only the second is gated.

## 11. In the Django admin

**There is no role field, because there is no role column.** What an account may do is administered
on three pages rather than one, and the accounts page shows the result read-only.

**What the account may do is shown beside the access panel**, resolved through
`accounts.roles.permissions_for` rather than restated, so the admin cannot describe authority the
application does not grant. A superuser is called out instead of listed, and an inactive account is
shown as holding nothing.

**The list no longer filters on role.** It filters on status, staff flags and groups. "Show me the
cultivators" is now a question about `ProducerMembership`, answered on that page.

**There are no bulk grants.** Activating, suspending and erasing are batch operations; appointing
somebody to a producer or to a storefront is not, and a bulk action that hands out authority over
other members' records is a mis-click with consequences.

**Activate skips placeholders and says so.** The bulk activate action already skipped erased
accounts; a `NON_AUTHENTICATING` row lands in the same bucket, and the message names both reasons
rather than reporting the wrong one.

**Two things are outstanding here**, and section 13 lists them: the accounts page lost its nickname
field with the split and has nowhere to put it until a `ClubMembership` admin exists, and none of the
three relationship tables is registered in the admin yet.

## 12. What the frontend receives

`GET /api/auth/me` and the sign-in endpoints return `UserOut`:

| Field | Contents |
| --- | --- |
| `status` | Whether this identity may sign in |
| `membership_status` | Where the club membership stands, or `null` for an account holding none |
| `role` | **Derived**: which club home to land on — `"admin"`, `"cultivator"` or `"member"` |
| `permissions` | Every `platform.*` action the account holds, sorted |

`role` is no longer a column and is no longer a fact. It is a routing hint, computed most-capable
first, kept because `clubHomeFor` needs one word and the alternative was teaching the frontend to
derive it from four relationship fields. **It can legitimately disagree with `permissions`** — an
administrator who is also a member reports `admin` and holds both sets — and the type in
`frontend/club/lib/api.ts` says so in as many words.

`permissions` is sent rather than left for the frontend to derive. A frontend that mapped
relationships to abilities itself would be a second copy of `accounts/roles.py`, and the drift would
show up as navigation offering a member something the API then refuses.

**It is for rendering, never for deciding.** Every endpoint checks the permission itself.

### What the frontend does with it

`frontend/club/lib/club-navigation.ts` is the whole of the frontend's use of this payload: a catalogue of
destinations, each carrying one `platform.*` codename, filtered by the set on the session and banded
into sections. `role` is not consulted anywhere in that module.

The bands are drawn around **who holds what** rather than around subject matter, which was a
correction rather than the first instinct. Filing "browse the catalogue" under plants and "reviews"
under growing reads perfectly well until you notice that everybody holds
`platform.browse_catalogue` and that administrators hold `platform.respond_to_reviews` too.

A contract test in `club-navigation.test.ts` reads `app/core/accounts/roles.py` as text and fails on any
codename this file does not grant. It earned its keep during C29: the two UC-tier destinations
failed the moment those codenames left the catalogue, and were removed rather than restored.

`frontend/club/lib/club-membership.ts` is the second consumer, and it reads `membership_status` alone.
`clubGateFor` decides whether the club is open, and — the case worth getting right — refuses to send
somebody to a payment screen when paying would not help them.

## 13. What is not built

The catalogue, the relationships and the enforcement path are built and tested. Most of what they
govern is not.

| Not built | Consequence |
| --- | --- |
| Plants, strains, batches, listings, pricing, orders, swaps, reviews, transactions, support tickets | Most of the catalogue names actions with nothing to perform them against |
| ~~The cultivator organisation~~ | **Partly built.** `ProducerMembership` exists with primary, full and limited rights, and `platform.appoint_cultivator_staff` is exercisable. `CultivatorProfile` is not yet generalised to `Producer` — that is the next section of Block 0.5 |
| Object-level rules | The person-level half is enforced. "A cultivator's own listings", "a member's own inventory" still need writing in the services that own each record — but they now have `ProducerMembership` rows to join against, which is what they never had |
| An admin for the three relationship tables | `ClubMembership`, `StorefrontStaff` and `ProducerMembership` are not registered. Until they are, the only routes are the shell and the services |
| The nickname in the Django admin | It moved to `ClubMembership` and the accounts page lost the field. It comes back with the membership admin above |
| Endpoints that check a platform permission | No API endpoint calls `has_perm` for a `platform.*` action yet. The mechanism is tested directly instead |
| What a placeholder holds in the swap zone | Deferred to the swap zone by decision — C6 settled what a placeholder *is*, not what it does |
| Any endpoint for creating a placeholder | `register_sharing_member` is reachable from the shell only. It authorises its own caller, so it is the right shape to put a router in front of |
| The market's administrator actions | `MARKET_ADMINISTRATOR_PERMISSIONS` is empty until the market vertical exists |

## 14. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | ~~`role` and `is_staff` are independent, so privilege is granted in two places and they can disagree.~~ | **Closed by C28 and C29.** There is no role column. `is_staff` and a `StorefrontStaff` row remain two grants, made in the same admin, which is intended — section 9 |
| 2 | ~~One role per account means a cultivator cannot buy or swap. Anyone who does both needs a second account.~~ | **Closed by C28.** Verified: an administrator who also holds a membership resolves to the exact union of both sets. No set was widened to achieve it |
| 3 | ~~The role-to-group mirror is best-effort and drifts.~~ | **Closed.** The groups are gone with the column — section 4, and `migrations.md` §3.3 |
| 4 | ~~A refused sharing-member registration tells the cultivator that the identity number is known to the club.~~ | **Closed by C6.** No identity number is collected, so there is nothing to collide with and nothing to disclose — section 3.4 |
| 5 | ~~The consent attestation is a cultivator's word, not the sharing member's own act, and would carry less weight with the Information Regulator.~~ | **Closed by C6.** There is no attestation, because there is nobody to consent |
| 6 | ~~Nothing re-attests when the attestation wording changes.~~ | **Closed by C6**, with risk 5 |
| 7 | A cultivator creates `User` rows. It is the only non-administrator route to an account on the platform. | **Narrowed, still accepted.** It no longer captures a third party's identity number — the row holds a nickname and nothing else. It remains why `register_sharing_member` authorises on a permission and records who created it |
| 8 | The catalogue names actions against models that do not exist. Codenames may not survive contact with the real models, and a renamed codename is a silent loss of authority rather than an error. | **Accepted, and partly mitigated in practice.** The frontend contract test caught two stale codenames the moment C29 removed them, which is the failure mode working as intended in the one direction it can |
| 9 | ~~`platform.appoint_cultivator_staff` is a role-level codename for an object-level rule, so it goes to every cultivator rather than the primary.~~ | **Closed by C28.** It is granted from `ProducerMembership.is_primary`. C13's remaining half is per-record scoping, which is work rather than a design question |
| 10 | `permissions` in `UserOut` is a rendering hint that looks like an authorisation decision. A future endpoint that trusts it instead of checking server-side would be an authorisation bypass that tests could pass. | Open — mitigated by documentation in three places; wants a lint or a review habit |
| 11 | `permissions_for` reads three relationships and must never be called on an unloaded account in an async view. `with_platform_roles()` is the discipline, and nothing enforces it. | Open — the failure is loud (`SynchronousOnlyOperation`) rather than silent, which is the mitigation. A check in `UserOut` that asserts the relations are cached would close it |
| 12 | `UserOut.role` is derived and can disagree with `permissions`. A frontend that starts deciding from it rather than routing by it would be reading a summary as an authority. | Open — documented at the resolver, in the TypeScript type and here. The same shape of risk as 10 |

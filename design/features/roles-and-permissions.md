# Roles and permissions

Who an account is, what that lets it do, and where each of those two facts is enforced.

## 1. Executive summary

There are three roles — **Admin**, **Cultivator**, **Member** — and every account holds exactly
one. A completed registration makes a Member. The other two are appointed by hand in the Django
admin, because both carry authority over records that are not the account's own and neither can be
claimed on a form.

The role is a **column** on `accounts.User`, defaulting to `member`, with a check constraint. What
each role may do is a **dictionary in code** (`app/accounts/roles.py`), resolved through a Django
authentication backend so that `user.has_perm('platform.purchase_plants')` works today — before any
of the models those actions operate on exist.

That last point is the shape of this whole feature. Almost every action below is against a plant, a
strain, a batch, an order or a swap, and none of those are built. So what is delivered is the
foundation and the design record: the roles, the catalogue, the enforcement path, and the API
payload the frontend will render navigation from. Section 12 is explicit about what that leaves out.

Two decisions are worth reading before the tables:

- **Role is not status.** `status` says whether an account may sign in; `role` says what it is. An
  inactive account holds no permissions at all, whatever its role, so suspension and erasure
  needed no knowledge of roles to remain safe.
- **Role is not staff status.** `is_staff` opens the Django admin. `role` opens the administrative
  actions the API exposes. Neither derives from the other, by decision — see section 8, which also
  records the cost.

## 2. The three roles

| Role | Who it is | How it is granted |
| --- | --- | --- |
| `admin` | A club administrator: authority over the collective's own records and over other accounts | By hand in the Django admin. `createsuperuser` defaults to it |
| `cultivator` | A grower with stock, listings and pricing of their own | By hand in the Django admin |
| `member` | Somebody who buys, owns and swaps plants | Every completed registration |

`member` is the column default as well as the outcome of registration. It is the safe default rather
than merely the convenient one: it grants nothing over anybody else's records, so a row created by a
fixture, a data migration or `createsuperuser` cannot arrive holding authority nobody granted it.

## 3. Why a column and not a Django group

Django's `PermissionsMixin` was already on `User`, so groups were available and unused. They were
rejected as the source of truth.

A group is **runtime data**. A member of staff can delete one, an account can belong to none or to
all three, and no database constraint can express "exactly one". A role is not runtime data: it is a
fact about the membership, it changes only when `accounts/roles.py` changes, and the club's rule is
one role per account. A column with `choices` and a check constraint says that. A group cannot.

**The groups exist anyway, mirrored from the column.** `User.save` puts the account in the Django
group matching its role — *Admins*, *Cultivators*, *Members* — and `accounts/migrations/0004`
created the three rows. Nothing reads them to decide a platform action. They exist so that when the
strain, plant and order models arrive, their ordinary Django model permissions can be attached to a
role in one place instead of to every account holding it.

Three properties of the mirror follow from that, and all three are tested:

- Only the three role groups are touched. A group a member of staff added for some other purpose is
  left standing, because that is somebody's deliberate act and this is bookkeeping.
- A missing group is recreated rather than failing the save.
- The mirror runs only when the role actually changed, and only on a write that carried the column.
  Every other save — a status change, a login timestamp, an erasure — pays nothing for it.

The mirror is deliberately **not** protected by a constraint, unlike `is_active`. It is allowed to
be best-effort because group membership grants no platform action, so drift there cannot escalate
anybody. Section 13 keeps that as a risk against the day model permissions are attached.

## 4. Exactly one role, and what that costs

One role per account was chosen over a many-to-many. It is enforceable in SQL, it makes "what may
this account do" a single lookup, and it matches how the collective talks about its people.

The cost is real and is accepted rather than worked around: **a cultivator is not also a buyer.**
Neither the Cultivator nor the Admin role carries `platform.purchase_plants`,
`platform.use_swap_zone` or `platform.offer_inventory_for_swap`, because the design gives those to
members. Somebody who both grows and buys needs a second account.

There is a test asserting exactly that, which reads oddly until the reason is clear: the tempting
fix is to quietly widen the cultivator set, and that would change the club's rule without anybody
deciding to. If the club wants growers to buy, that is a decision to make and this document to
change — see risk 2.

## 5. The permission catalogue

Every action lives in `app/accounts/roles.py` as a codename and the sentence that put it there. The
codenames are namespaced `platform.*`: Django splits a permission on its first dot to find an app
label, no installed app is called `platform`, and the prefix is what tells a reader that the action
is resolved from the catalogue rather than from an `auth.Permission` row.

### 5.1 Why a dictionary rather than permission rows

An `auth.Permission` row needs a `ContentType`, which needs a model. There are no plants, strains,
batches, transactions or swaps, so the alternative was a fake unmanaged model existing only to hold
permission rows for tables nobody has written. That buys nothing: the backend resolves these from
the dictionary without touching the database, so `has_perm` works today and keeps working when the
real models land beside it.

The dictionary has a second benefit worth naming. **The catalogue is the design record.** It is
reviewed in a diff, it cannot drift from what a data migration once seeded, and the tables below are
a prose reading of that file rather than a second source of truth.

### 5.2 Club administration

Held by `admin` only. Every one of these is authority over somebody else's records, and a regression
that leaked one would raise no error until it was used.

| Action | What it permits |
| --- | --- |
| `platform.manage_cultivators` | Create, read, update and delete cultivators |
| `platform.manage_strain_catalogue` | Create, read, update and delete strain listings platform-wide |
| `platform.manage_product_types` | Create, read, update and delete finished product types and their prices |
| `platform.manage_club_rules` | Publish and withdraw the club and platform rules |
| `platform.disable_user` | Disable or remove any account |
| `platform.disable_plant` | Disable or remove any plant |
| `platform.disable_batch` | Disable or remove any batch |
| `platform.refund_transaction` | Reverse or refund a transaction in whole or in part, withholding transaction and platform fees |
| `platform.hide_cultivator` | Hide a cultivator and everything it offers |
| `platform.revoke_access` | Revoke an account's access to the platform |
| `platform.cancel_membership` | Cancel a membership |

Club rules have no button of their own in the original brief, and that stays true: they are
published through the Django admin, where the document machinery already lives. See
`design/backend.md` section 9.

### 5.3 Cultivation

Held by `cultivator`.

| Action | What it permits |
| --- | --- |
| `platform.manage_own_cultivator_profile` | Manage the cultivator's own profile |
| `platform.appoint_cultivator_staff` | Appoint other cultivator members, with full or limited rights |
| `platform.manage_plant_stock` | Upload plant stock and adjust how many plants are available |
| `platform.manage_own_pricing` | Set pricing, including promotional pricing for a given strain, period, batch or quantity |
| `platform.manage_own_strain_listings` | CRUD the cultivator's own strain listings: image, description, available finished product types, price |
| `platform.manage_sharing_members` | CRUD sharing members, and manage their stock |
| `platform.change_plant_status` | Move a plant between preflowering, in bloom, harvested, processed and shipped |
| `platform.view_fulfilment_documents` | View and print ownership certificates, packing labels and shipping documents for the courier |
| `platform.respond_to_reviews` | View and respond to reviews and ratings |
| `platform.request_catalogue_addition` | Ask an administrator to list a new strain or finished product type |
| `platform.record_notes` | Record notes against members, strains, plants and subscriptions |

Plus `platform.manage_own_profile`, `platform.browse_catalogue` and
`platform.submit_support_request`, which the brief gives to cultivators as well as members. With one
role per account those are repeated into the cultivator set rather than inherited: there is no role
hierarchy here, deliberately, because a hierarchy makes every future grant to the base role a silent
grant to everyone above it.

**`platform.appoint_cultivator_staff` is the one entry the catalogue cannot express properly.** The
brief gives it to the *primary* cultivator, and "primary" is a relationship between an account and a
cultivator organisation, not a fact about the account. A role-level permission cannot say that. The
codename is listed so the requirement is on the record, and the object-level half arrives with the
cultivator organisation — section 12.

### 5.4 Membership

Held by `member`.

| Action | What it permits |
| --- | --- |
| `platform.manage_own_profile` | View and update their own profile details and image |
| `platform.browse_catalogue` | Browse available strains and cultivators, including ratings and reviews |
| `platform.purchase_plants` | Choose and purchase plants with grow services |
| `platform.view_own_inventory` | View their own plant inventory |
| `platform.use_swap_zone` | Enter and browse the swap zone, and make swaps |
| `platform.offer_inventory_for_swap` | Offer their own plants in the swap zone, and withdraw them again |
| `platform.submit_reviews` | Rate and review the cultivators and plants they have received |
| `platform.track_orders` | Track and trace their orders |
| `platform.query_orders` | Query an order |
| `platform.submit_support_request` | Raise a support request |

### 5.5 Two rules that are deliberately not permissions

The brief contains two requirements that are **not** in the catalogue, because a permission that
everybody holds and nobody can be refused is not a permission. They are recorded here so they are
not lost:

**Members are concealed behind a nickname.** Other members see a nickname, never a legal name. This
is a property of the payloads the API returns, not a grant. `accounts.schemas.UserOut` is the
signed-in member's own record and so may carry their own name; any endpoint that returns *another*
member must expose `display_name` and nothing else. There is no such endpoint yet, which is exactly
why this is written down.

**No member may hold more than four flowering plants.** The system prompts a member to swap a
flowering plant for a pre-flowering one when they approach the limit, and refuses a swap that would
breach it. That is an invariant of the swap service, enforced on the write, and it belongs with the
plant and swap models when they are built.

## 6. How a permission is checked

`app/accounts/backends.py` registers `RoleBackend` second in `AUTHENTICATION_BACKENDS`, after
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
protocol is what supplies those; the first version of this class omitted them and failed at request
time rather than in a test.

**It issues no query.** `roles.permissions_for` is pure dictionary lookup. That is a requirement
rather than an optimisation: `UserOut` serialises the permission list inside those async views,
where a synchronous ORM call raises `SynchronousOnlyOperation`.

**Object-level questions are refused outright.** `has_perm(perm, obj)` returns `False` rather than
falling through to the role. A role is a fact about an account, not about that account's
relationship to one record, so answering from it would be wrong in the dangerous direction: "may
this cultivator edit *this* listing" would come back yes for every listing on the platform.

## 7. Role and status answer different questions

`permissions_for` refuses in this order:

1. An anonymous visitor holds nothing.
2. An **inactive** account holds nothing, whatever its role.
3. An active **superuser** holds everything, because Django's permission framework treats a
   superuser that way and a second rule here would only be a place for the two to disagree.
4. Otherwise, the role's set.

Step 2 is the load-bearing one. `is_active` is derived from `status` and held to it by a check
constraint (`design/backend.md` section 3.1), so suspension and erasure make an account powerless
without either of them having been taught about permissions. A suspended cultivator keeps the
Cultivator role and holds none of its actions; reactivating restores both at once.

`soft_delete` therefore leaves `role` standing, and the group with it. A role is a fact about the
collective's own structure — that this cultivator grew what the batch records say it grew — rather
than personal data about the person, and it confers nothing on an account that erasure has left
Inactive.

`set_role` does **not** cut live sessions, unlike `deactivate`. A session carries no cached
permissions; every request resolves the role afresh. What can lag is a page already rendered in a
browser, which is a refresh rather than a privilege.

## 8. Role and staff status are independent

`is_staff` opens `/admin/`. `role` opens the administrative actions the API exposes. Setting either
does not set the other, and the model has no rule connecting them.

The alternative — deriving `is_staff` from the Admin role, the way `is_active` is derived from
`status` — was rejected because the two grants are genuinely different. A back-office login is
access to the database through a form; authority over the club's records is a position in the
collective. Someone may reasonably hold either alone: a bookkeeper who needs the admin but runs
nothing, an administrator who works only through the member-facing application.

**The cost is stated plainly: there are two places to grant privilege, and they can disagree.** The
admin makes that visible rather than hiding it — the Access panel says so in as many words, and
`is_club_admin` is named that way precisely so it cannot be misread as `is_staff` at a call site.
Risk 1 keeps it on the register.

One default bends the line without deriving anything: `createsuperuser` creates an account in the
Admin role. It is overridable, and it changes nothing functionally — a superuser bypasses every
permission check anyway — but leaving it at the column default would have the admin list describe
the founder of the club as an ordinary member.

## 9. What sign-up grants

`membership.services.REGISTERED_ROLE` is `member`, sitting beside `REGISTERED_STATUS`
(`pending_payment`). Registration is the only route to the Member role and the only role
registration can grant.

The value is written there as well as being the column default, and the repetition is deliberate:
the default protects rows the membership app never touches, while `REGISTERED_ROLE` states the
outcome of *registration*, which is a decision that app owns and could change. A reader asking "what
does a member get when they join?" should find the answer in the app that joins them.

A registered member holds the Member role and **no permissions at all** until a payment moves them
to Active. Both halves are tested, because a role on the row and authority in the hand are different
things and only the second is gated.

## 10. In the Django admin

`role` is an ordinary editable field on the member form, and the admin is the only place a
cultivator or an administrator is appointed. Four things around it are deliberate:

**What the role permits is shown beside it**, read from `accounts/roles.py` rather than restated, so
the admin cannot describe authority the application does not grant. It reflects the role *as saved*,
appearing after the save rather than before, because the catalogue is keyed on what is stored. A
superuser is called out instead of listed, and an inactive account is shown as holding nothing.

**Group membership is read-only.** It mirrors the role, and an editable field would let it drift —
the same argument as `is_active`. There is also a mechanical reason: the admin's `save_m2m()` runs
after the model save, so an editable groups widget would overwrite the mirror with whatever was
rendered before the role changed. Changing what a whole role may do is done on the group itself,
under *Authentication and Authorisation*.

**The list filters on role first.** "Show me the cultivators" is the question the member list gets
asked once there is more than one. The `groups` filter stays, because a group added by hand for some
other purpose is the one thing a role filter would not surface.

**There are no bulk role actions.** Activate, suspend and erase are batch operations; promoting
people to Cultivator is not, and a bulk action that hands out authority over other members' records
is a mis-click with consequences. It is one field on one form, per account, on purpose.

## 11. What the frontend receives

`GET /api/auth/me` and the sign-in endpoints return `UserOut`, which now carries two new fields:

| Field | Contents |
| --- | --- |
| `role` | `"admin"`, `"cultivator"` or `"member"` |
| `permissions` | Every `platform.*` action the account holds, sorted |

`permissions` is sent rather than left for the frontend to derive from `role`. A frontend that mapped
roles to abilities itself would be a second copy of `accounts/roles.py`, and the drift would show up
as navigation offering a member something the API then refuses. An endpoint of its own for the same
answer would be a round trip on every page that renders a menu.

**It is for rendering, never for deciding.** Every endpoint checks the permission itself. A list in a
browser is a hint about what to draw, and the type in `frontend/lib/api.ts` says so.

## 12. What is not built

The roles, the catalogue and the enforcement path are built and tested. Nothing they govern is.

| Not built | Consequence |
| --- | --- |
| Plants, strains, batches, listings, pricing, orders, swaps, reviews, transactions, support tickets | Most of the catalogue names actions with nothing to perform them against. The codenames are the requirement on the record, not working features |
| The cultivator organisation | There is no `CultivatorProfile`, no membership or appointment table, and no primary-versus-full-versus-limited rights. `platform.appoint_cultivator_staff` is listed and cannot yet be exercised. Deferred on purpose: built against features that do not exist, its shape would be a guess |
| Object-level rules | "A cultivator's own listings", "a member's own inventory", "the primary cultivator" — all of them need the model they are scoped to. `RoleBackend` refuses object-level questions rather than answering them wrongly |
| Any authenticated frontend page | The member portal is not routed (`design/frontend.md` section 9), so nothing renders from `permissions` yet |
| Endpoints that check a platform permission | No API endpoint calls `has_perm` for a `platform.*` action, because there is no endpoint whose action is in the catalogue. The mechanism is tested directly instead |
| Sharing members, and the four-flowering-plant cap | Both are in the catalogue or in section 5.5 as requirements. Neither has an implementation |

## 13. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | `role` and `is_staff` are independent, so privilege is granted in two places and they can disagree. An account can hold the Admin role without admin access, or admin access without the role. | Accepted by decision — see section 8. Made visible in the admin rather than hidden |
| 2 | One role per account means a cultivator cannot buy or swap, and an administrator cannot do either. Anyone who does both needs a second account. | Accepted. Revisit when cultivators are real users of the member-facing application |
| 3 | The role-to-group mirror is best-effort: a queryset `.update()` that skips `save()` leaves the group behind. Harmless today, because no platform action is granted by a group. It stops being harmless the day model permissions are attached to a role group. | Open — needs a resync command, or a constraint, before model permissions hang off the groups |
| 4 | The catalogue names actions against models that do not exist. Codenames may not survive contact with the real models, and a renamed codename is a silent loss of authority rather than an error. | Accepted at this stage. The catalogue test asserts internal consistency, which is all that can be asserted before the models exist |
| 5 | `platform.appoint_cultivator_staff` is a role-level codename for an object-level rule. Granting it to the Cultivator role gives it to every cultivator, not only the primary one. | Open — inert while nothing checks it. Must be resolved with the cultivator organisation, not after |
| 6 | `permissions` in `UserOut` is a rendering hint that looks like an authorisation decision. A future endpoint that trusts it instead of checking server-side would be an authorisation bypass that tests could pass. | Open — mitigated by documentation in three places; wants a lint or a review habit |

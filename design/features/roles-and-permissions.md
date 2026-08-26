# Roles and permissions

Who an account is, what that lets it do, and where each of those two facts is enforced.

## 1. Executive summary

There are four roles — **Admin**, **Cultivator**, **Member**, **Sharing member** — and every account
holds exactly one. A completed registration makes a Member. Admin and Cultivator are appointed by
hand in the Django admin, because both carry authority over records that are not the account's own
and neither can be claimed on a form. Sharing member is the exception to all of it: it is registered
*by a cultivator*, holds no permissions, and never signs in. Section 3 is about that role alone.

The role is a **column** on `accounts.User`, defaulting to `member`, with a check constraint. What
each role may do is a **dictionary in code** (`app/accounts/roles.py`), resolved through a Django
authentication backend so that `user.has_perm('platform.purchase_plants')` works today — before any
of the models those actions operate on exist.

That last point is the shape of this whole feature. Almost every action below is against a plant, a
strain, a batch, an order or a swap, and none of those are built. So what is delivered is the
foundation and the design record: the roles, the catalogue, the enforcement path, and the API
payload the frontend will render navigation from. Section 13 is explicit about what that leaves out.

Three decisions are worth reading before the tables:

- **Role is not status.** `status` says whether an account may sign in; `role` says what it is. An
  inactive account holds no permissions at all, whatever its role, so suspension and erasure
  needed no knowledge of roles to remain safe.
- **Role is not staff status.** `is_staff` opens the Django admin. `role` opens the administrative
  actions the API exposes. Neither derives from the other, by decision — see section 9, which also
  records the cost.
- **A role need not be an actor.** A sharing member is an identity that holds stock so the swap zone
  is not empty. It holds no permissions at all, and that empty set is a deliberate entry rather than
  an oversight.

## 2. The four roles

| Role | Who it is | How it is granted |
| --- | --- | --- |
| `admin` | A club administrator: authority over the collective's own records and over other accounts | By hand in the Django admin. `createsuperuser` defaults to it |
| `cultivator` | A grower with stock, listings and pricing of their own | By hand in the Django admin |
| `member` | Somebody who buys, owns and swaps plants | Every completed registration |
| `sharing_member` | An identity holding flowering plants in the swap zone. Never signs in | Registered by a cultivator, on their attestation |

`member` is the column default as well as the outcome of registration. It is the safe default rather
than merely the convenient one: it grants nothing over anybody else's records, so a row created by a
fixture, a data migration or `createsuperuser` cannot arrive holding authority nobody granted it.

## 3. The sharing member

A new club has a swap zone with nothing in it, and a swap zone with nothing in it is not a feature.
So cultivators put **sharing members** on the register: a name, an identity number and a nickname,
with four flowering plants allocated to each, and those plants appear in the swap zone for members to
choose against. It is how the zone is seeded.

### 3.1 They are a `User` row, and that is the load-bearing decision

A sharing member has no email address, no password, no subscription and no permissions. Every
instinct says put them in their own table. The instinct is wrong, and four things say so:

- **One nickname namespace.** The swap zone shows nicknames and nothing else. A separate table means
  a sharing member and a member could wear the same name in the same list, which is impersonation
  rather than a collision.
- **One encrypted identity column.** Their ID number is personal information under POPIA exactly as
  a member's is. A second table means a second AES column, a second blind index, and a second chance
  to get either wrong.
- **One erasure route.** `User.soft_delete` already clears names, nicknames and identity numbers and
  revokes credentials. A parallel model needs its own, and the second one is the one that rots.
- **One kind of owner.** Plants, swaps, ownership certificates and packing labels all point at
  whoever holds the plant. Two owner types means every one of those grows a nullable pair of foreign
  keys and a "which is it" check at every call site.

Being a `User` row also means the club's "one account per identity document" rule reaches sharing
members for free — a person cannot be a member and somebody's sharing member at once. That is the
rule the club wants and it has a cost, in section 3.4.

### 3.2 They never sign in, and the database says so

A sharing member sits at `UserStatus.SHARING`, a sixth status value added for them. `PENDING` would
have been free and would have read as a promise the record never keeps: "pending verification"
describes a state that resolves, and this one never does.

Two mechanisms, not one:

- They hold no email address, so there is nothing for `authenticate` to match.
- A check constraint, `sharing_member_never_signs_in`, refuses the Sharing member role in the
  `active` status at all.

The second exists because the first is a property of the *data*. Somebody typing an address into the
admin, or a fixture supplying one, would silently turn stock into a sign-in-capable account. The
constraint makes "never signs in" a fact about the database instead of a convention.

It refuses `active` specifically rather than pinning the status to `sharing`, and that is deliberate:
a sharing member registered in error has to be suspendable, and erasure has to be able to finish by
setting `inactive`. `User.activate()` also refuses the role outright, so a bulk admin action reports
something useful instead of failing on an index name.

### 3.3 The consent attestation, and why it is not a consent

This is the part with a real compliance decision in it.

A member ticks boxes at sign-up and `documents.DocumentConsent` records what they ticked and against
which revision. A sharing member ticks nothing — they never saw a form. POPIA still needs a lawful
basis for the club to hold their name and their identity number.

So **the cultivator attests**, and the attestation is on the record:

| Column | Holds |
| --- | --- |
| `sharing_consent_attested_by` | Who confirmed it |
| `sharing_consent_attested_at` | When |
| `sharing_consent_version` | Which wording, so a later revision cannot reinterpret older records |

The wording itself is `roles.SHARING_CONSENT_ATTESTATION`, in code so that the form, the admin and
the service quote one sentence rather than three paraphrases, and so that changing it is a reviewable
diff against a version number.

**It is called an attestation and not a consent on purpose.** It is weaker evidence than a member's
own tick: it says who swore what and when, rather than pretending the sharing member agreed here.
Naming it accurately is what stops it being mistaken for the stronger thing later. The alternative
considered was recording a proxy tick in the existing `DocumentConsent` ledger; it was rejected
because that ledger means "this person ticked this box", and putting somebody else's tick in it
devalues every row already there.

`register_sharing_member` refuses to write anything at all without it, and it checks the attestation
*before* validating any field. A submission with no lawful basis is not a submission with one thing
missing — it is a record the club cannot justify holding, and there is nothing to validate about the
rest of it. The check constraint `sharing_member_is_complete` is the backstop for a write that never
went near the service.

That constraint requires three things of a sharing member: the cultivator who registered them, the
attestation, and a nickname. Erased rows are exempt, because `soft_delete` blanks the nickname by
design — without the exemption, the POPIA erasure route would be refused by the database on exactly
the records most likely to need it.

Erasure keeps `registered_by` and all three attestation columns. They identify the *cultivator* and
their act, not the erased person, and they are what lets the club show it had a lawful basis for
holding the record at all. The same argument as `email_hash` surviving.

### 3.4 The refusal that leaks, and why it is not solvable

One account per identity document, enforced on a unique blind index. So a cultivator registering
somebody already on file — as a member, or as another cultivator's sharing member — is refused.

`membership.services.register_member` handles this by answering a duplicate exactly as it answers a
success, writing nothing. **This cannot.** The cultivator is waiting to allocate four plants to a
record; pretending one exists would be a lie they trip over immediately.

So the refusal is deliberately vague — it says the identity number cannot be registered and to ask an
administrator. It names no record, no role and no other cultivator, and a test asserts that it names
none of them. It is still a leak: a cultivator can learn that an identity number is known to the
club. Enforcing the rule and telling the cultivator their registration failed cannot both be done
silently, so this is recorded as risk 4 rather than solved.

### 3.5 The four plants

`services.SHARING_MEMBER_PLANT_ALLOCATION` is `4` — the same limit members live under, which is why
it is one number and not two. `register_sharing_member` returns it so a caller does not hard-code it.

It is **enforced nowhere**, because there is no plant to count. The allocation itself, the cap, and
the sharing member's stock appearing in the swap zone all arrive with the plant model. Section 13
lists that properly.

### 3.6 Who may register one

`platform.register_sharing_member`, `platform.manage_sharing_members` and
`platform.allocate_sharing_member_stock` belong to the **Cultivator role alone** — not to the club
administrator. An administrator who has to fix a sharing-member record does it in the Django admin,
which `is_staff` opens. Granting the actions to the Admin role as well would make the club's own
administrators a second route to creating accounts through the API, and creating accounts for other
people is the one thing on this platform that should have exactly one route.

The service asks for the **permission**, never for the role. So a superuser works, and a future role
that gains the permission works, without `register_sharing_member` changing. It also means authority
is gated on status for free: `permissions_for` refuses an inactive account before it looks at the
role, so a suspended cultivator cannot register anybody.

## 4. Why a column and not a Django group

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
anybody. Risk 3 keeps that on the register against the day model permissions are attached.

## 5. Exactly one role, and what that costs

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

The Sharing member role makes the same rule bite in a second place, and there it is the point rather
than the cost: a person cannot be a member and a sharing member at once, because one identity
document means one account. Somebody who joins the club properly after holding stock as a sharing
member is the *same row*, moved — not a second account. That conversion is not built (section 13),
and building it is a role change plus an email address plus the club document agreements, not a new
record.

## 6. The permission catalogue

Every action lives in `app/accounts/roles.py` as a codename and the sentence that put it there. The
codenames are namespaced `platform.*`: Django splits a permission on its first dot to find an app
label, no installed app is called `platform`, and the prefix is what tells a reader that the action
is resolved from the catalogue rather than from an `auth.Permission` row.

### 6.1 Why a dictionary rather than permission rows

An `auth.Permission` row needs a `ContentType`, which needs a model. There are no plants, strains,
batches, transactions or swaps, so the alternative was a fake unmanaged model existing only to hold
permission rows for tables nobody has written. That buys nothing: the backend resolves these from
the dictionary without touching the database, so `has_perm` works today and keeps working when the
real models land beside it.

The dictionary has a second benefit worth naming. **The catalogue is the design record.** It is
reviewed in a diff, it cannot drift from what a data migration once seeded, and the tables below are
a prose reading of that file rather than a second source of truth.

### 6.2 Club administration

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
`design/backend.md` section 10.

### 6.3 Cultivation

Held by `cultivator`.

| Action | What it permits |
| --- | --- |
| `platform.manage_own_cultivator_profile` | Manage the cultivator's own profile |
| `platform.appoint_cultivator_staff` | Appoint other cultivator members, with full or limited rights |
| `platform.manage_plant_stock` | Upload plant stock and adjust how many plants are available |
| `platform.manage_own_pricing` | Set pricing, including promotional pricing for a given strain, period, batch or quantity |
| `platform.manage_own_strain_listings` | CRUD the cultivator's own strain listings: image, description, available finished product types, price |
| `platform.register_sharing_member` | Register a sharing member from a name, an identity number and a nickname, attesting that they consented and were given the collection notice |
| `platform.manage_sharing_members` | Read, update and withdraw the sharing members this cultivator registered |
| `platform.allocate_sharing_member_stock` | Allocate flowering plants to a sharing member, up to the four-plant holding limit, putting them in the swap zone |
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
cultivator organisation — section 13.

### 6.4 Membership

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

### 6.5 The sharing member holds nothing

`ROLE_PERMISSIONS[SHARING_MEMBER]` is an empty frozenset, and `SHARING_MEMBER_ACTIONS` is an empty
dictionary that exists only so that three groups of actions beside four roles does not read as an
omission.

They never sign in, so any action granted to them would be unreachable. What happens to their plants
is the swap zone's business, and their record is managed by the cultivator who registered it, through
`platform.manage_sharing_members`. It is a role that is an **identity, not an actor**.

An empty role is normally a silent lockout — an account that stops being able to do anything, with
nothing to explain why — so `ROLES_WITHOUT_PERMISSIONS` names this one as the single permitted
exception, and the catalogue test asserts every *other* role is non-empty. Without that, the next
role that accidentally ended up empty would look deliberate.

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
The same number is what a cultivator allocates to each sharing member — one limit, named once, in
`services.SHARING_MEMBER_PLANT_ALLOCATION`. It is an invariant of the swap service, enforced on the
write, and it belongs with the plant and swap models when they are built.

## 7. How a permission is checked

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

## 8. Role and status answer different questions

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
Inactive. For a sharing member it leaves `registered_by` and the attestation columns too; section 3.3
says why.

The Sharing member role is the one place status and role are coupled, and only in one direction: a
check constraint keeps that role out of `active`. Suspended and Inactive stay reachable, because a
sharing member registered in error has to be stoppable and erasure has to be able to finish.

`set_role` does **not** cut live sessions, unlike `deactivate`. A session carries no cached
permissions; every request resolves the role afresh. What can lag is a page already rendered in a
browser, which is a refresh rather than a privilege.

## 9. Role and staff status are independent

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

## 10. Where an account gets its role

| Role | Route | Written by |
| --- | --- | --- |
| `member` | Sign-up | `membership.services.register_member` |
| `sharing_member` | A cultivator, on their attestation | `accounts.services.register_sharing_member` |
| `cultivator` | By hand | The Django admin |
| `admin` | By hand, or `createsuperuser` | The Django admin, `UserManager.create_superuser` |

`membership.services.REGISTERED_ROLE` is `member`, sitting beside `REGISTERED_STATUS`
(`pending_payment`). Registration is the only route to the Member role and the only role
registration can grant.

`register_sharing_member` lives in `accounts`, not in `membership`, and the distinction is not
cosmetic. `membership` exists because turning a submission into a member spans `accounts` and
`documents`, which must not know about each other; registering a sharing member spans nothing, and a
sharing member is not a membership — no subscription, no payment, no agreements of their own. Filing
the two together would put unlike things under one name.

The value is written there as well as being the column default, and the repetition is deliberate:
the default protects rows the membership app never touches, while `REGISTERED_ROLE` states the
outcome of *registration*, which is a decision that app owns and could change. A reader asking "what
does a member get when they join?" should find the answer in the app that joins them.

A registered member holds the Member role and **no permissions at all** until a payment moves them
to Active. Both halves are tested, because a role on the row and authority in the hand are different
things and only the second is gated.

## 11. In the Django admin

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

**The Sharing member panel is editable, and says why it should not be the route.** It holds
`registered_by` and the three attestation columns, and until there is an endpoint this admin is the
only interface staff have — so making it read-only would make sharing members uncreatable. But
`accounts.services.register_sharing_member` is the route that validates the identity number, applies
the age rule, requires the nickname and refuses a duplicate, and the panel's own description points at
it. The database refuses an incomplete sharing member either way.

**Activate skips sharing members and says so.** The bulk activate action already skipped erased
accounts; a sharing member now lands in the same bucket, and the message names both reasons rather
than reporting the wrong one.

## 12. What the frontend receives

`GET /api/auth/me` and the sign-in endpoints return `UserOut`, which now carries two new fields:

| Field | Contents |
| --- | --- |
| `role` | `"admin"`, `"cultivator"`, `"member"` or `"sharing_member"` |
| `permissions` | Every `platform.*` action the account holds, sorted |

`permissions` is sent rather than left for the frontend to derive from `role`. A frontend that mapped
roles to abilities itself would be a second copy of `accounts/roles.py`, and the drift would show up
as navigation offering a member something the API then refuses. An endpoint of its own for the same
answer would be a round trip on every page that renders a menu.

**It is for rendering, never for deciding.** Every endpoint checks the permission itself. A list in a
browser is a hint about what to draw, and the type in `frontend/lib/api.ts` says so.

### What the frontend does with it

`frontend/lib/club-navigation.ts` is the whole of the frontend's use of this payload: a catalogue of
destinations, each carrying one `platform.*` codename, filtered by the set on the session and banded
into sections. `role` is not consulted anywhere in that module. The three home pages differ by two
sentences of copy; everything below the greeting is this catalogue, so an administrator's screen is
the same component rendering a different subset.

The bands are drawn around **who holds what** rather than around subject matter, which was a
correction rather than the first instinct. Filing "browse the catalogue" under plants and "reviews"
under growing reads perfectly well until you notice that all three roles hold
`platform.browse_catalogue` and that administrators hold `platform.respond_to_reviews` too — at
which point a cultivator gets a band headed *Plants and orders* holding one browse link, and an
administrator gets one headed *Growing* holding nothing they grow.

A contract test in `club-navigation.test.ts` reads `app/accounts/roles.py` as text and fails on any
codename this file does not grant. A codename that Django does not recognise grants nothing, so the
destination would simply never appear for anybody — a defect no amount of rendering will surface.

`role` is used for exactly one thing: choosing which of the three homes an account lands on. That
lives in `frontend/lib/club-roles.ts` and maps `sharing_member` to no home at all.

A sharing member cannot reach this payload — no email address, and a constraint keeps the role out of
`active`, so no session can belong to one. The `role` and `status` unions in `frontend/lib/api.ts`
admit both values anyway, because the type describes the column rather than the subset a browser
happens to see. The same reason it already admits the shape of an erased account.

## 13. What is not built

The roles, the catalogue and the enforcement path are built and tested. Nothing they govern is.

| Not built                                                                                      | Consequence |
|------------------------------------------------------------------------------------------------| --- |
| Plants, strains, batches, listings, pricing, orders, swaps, reviews, transactions, support tickets | Most of the catalogue names actions with nothing to perform them against. The codenames are the requirement on the record, not working features |
| ~~The cultivator organisation~~                                                                | There is no `CultivatorProfile`, no membership or appointment table, and no primary-versus-full-versus-limited rights. `platform.appoint_cultivator_staff` is listed and cannot yet be exercised. Deferred on purpose: built against features that do not exist, its shape would be a guess |
| Object-level rules                                                                             | "A cultivator's own listings", "a member's own inventory", "the primary cultivator" — all of them need the model they are scoped to. `RoleBackend` refuses object-level questions rather than answering them wrongly |
| ~~Any authenticated frontend page~~                                                            | **Built.** `/member`, `/cultivator` and `/admin` render from `permissions`, never from `role` — `frontend/lib/club-navigation.ts` maps each `platform.*` codename to a destination, and a contract test reads this file as text so a renamed codename cannot quietly empty a menu. Almost every destination is marked *Not built yet*, which is the rest of this table |
| Endpoints that check a platform permission                                                     | No API endpoint calls `has_perm` for a `platform.*` action, because there is no endpoint whose action is in the catalogue. The mechanism is tested directly instead |
| The four-plant allocation, and the cap                                                         | `SHARING_MEMBER_PLANT_ALLOCATION` is `4` and is enforced nowhere, because there is no plant to count. `register_sharing_member` returns the number; it cannot create the stock |
| A sharing member's stock in the swap zone                                                      | The whole point of the role, and entirely unbuilt. There is no swap zone |
| Converting a sharing member into a member                                                      | One identity document means one account, so somebody joining properly after holding stock is the same row moved — a role change, an email address, and the club document agreements. Not built |
| Re-attestation                                                                                 | `sharing_consent_version` records which wording was attested. If the wording is revised, existing records keep their version and nothing asks for a fresh attestation |
| Any endpoint for registering a sharing member                                                  | `accounts.services.register_sharing_member` is reachable from the admin and the shell only. It already authorises its caller, so it is the right shape to put a router in front of |

## 14. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | `role` and `is_staff` are independent, so privilege is granted in two places and they can disagree. An account can hold the Admin role without admin access, or admin access without the role. | Accepted by decision — see section 9. Made visible in the admin rather than hidden |
| 2 | One role per account means a cultivator cannot buy or swap, and an administrator cannot do either. Anyone who does both needs a second account. | Accepted. Revisit when cultivators are real users of the member-facing application |
| 3 | The role-to-group mirror is best-effort: a queryset `.update()` that skips `save()` leaves the group behind. Harmless today, because no platform action is granted by a group. It stops being harmless the day model permissions are attached to a role group. | Open — needs a resync command, or a constraint, before model permissions hang off the groups |
| 4 | A refused sharing-member registration tells the cultivator that the identity number is known to the club. One account per identity document has to be enforced, and the cultivator has to be told the registration failed, so a leak is unavoidable; the refusal is worded to name no record, role or other cultivator. | Accepted — see section 3.4. Revisit if cultivators become numerous or less trusted |
| 5 | The consent attestation is a cultivator's word, not the sharing member's own act. It is weaker evidence than a `DocumentConsent` row and would carry less weight with the Information Regulator. | Open — wants legal review of the wording in `roles.SHARING_CONSENT_ATTESTATION`, and a decision on whether the club notifies sharing members directly |
| 6 | Nothing re-attests when the attestation wording changes. Records keep the version they were made under, so a substantive revision leaves older sharing members attested against superseded wording. | Open — the `documents` app already models re-acceptance; this could reuse it |
| 7 | A cultivator creates `User` rows. It is the only non-administrator route to an account on the platform, and it captures a third party's identity number. | Accepted — the reason `register_sharing_member` authorises on a permission and records who attested. A cultivator whose account is compromised can create records, not sign-ins |
| 8 | The catalogue names actions against models that do not exist. Codenames may not survive contact with the real models, and a renamed codename is a silent loss of authority rather than an error. | Accepted at this stage. The catalogue test asserts internal consistency, which is all that can be asserted before the models exist |
| 9 | `platform.appoint_cultivator_staff` is a role-level codename for an object-level rule. Granting it to the Cultivator role gives it to every cultivator, not only the primary one. The same applies to `manage_sharing_members`, which should be scoped to the sharing members that cultivator registered and today is not. | Open — inert while nothing checks either. Must be resolved with the cultivator organisation, not after |
| 10 | `permissions` in `UserOut` is a rendering hint that looks like an authorisation decision. A future endpoint that trusts it instead of checking server-side would be an authorisation bypass that tests could pass. | Open — mitigated by documentation in three places; wants a lint or a review habit |

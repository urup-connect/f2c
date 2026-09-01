# The cultivator organisation

The farm as a record, the people appointed to it, and who owns a plant at every moment of its life.

Written from the organisation structure the product owner supplied while closing **C13**, which is
the first statement of it in one place. `twp-tasks/member-roles.md` gives the same structure in
fragments — "cultivators have a primary account and then can give access to staff", "view their own
plant inventory" — and `features/roles-and-permissions.md` gives the permission catalogue that sits
on top of it. This document is the shape underneath both.

## 1. Executive summary

Four statements, and everything below is one of them made enforceable:

| The structure | What it is in the schema |
| --- | --- |
| **Cultivator** — the farm business. The front identity members see | `producers.Producer`: trading name, description, image, published state, collection address, bank details |
| **Cultivator member** — the owner of the farm. Appoints staff and sharing members; controls the farm's identity, profile and offering | `producers.ProducerMembership` at `role='primary'`, one per farm, enforced in SQL |
| **Cultivator staff** — appointed by the primary to act on admin functions: stock uploads, and transfers to sharing members as permitted by the primary | `ProducerMembership` at `role='full'` or `role='limited'` |
| **A member views their own inventory** — and every plant has a verifiable owner, with an audit trail of ownership from the farm through every purchase and swap to final ownership | `plant.Plant.owner` for the current holder, `plant.PlantOwnership` for the trail. Append-only |

**The farm is the record, not the person.** This is the single most consequential thing here and it
was not always true: `Producer` began as `CultivatorProfile`, a one-to-one hanging off a user
account. A farm with three appointed staff has no one owner whose profile it is, and a farm whose
primary leaves does not stop trading. **C28** made the organisation the record and the people rows
against it.

**Nothing here is cannabis-specific.** A farmer supplying the produce market is the same `Producer`
with a different `ProducerStorefront` row. `design/verticals.md` section 6 is why the app lives on
the commerce side rather than in the club vertical.

## 2. The farm

`app/commerce/producers/models.py`.

| Field | Why it is there |
| --- | --- |
| `trading_name`, `trading_name_key` | What members see. Unique case-insensitively, because two farms reading as the same name to everybody but the database is the impersonation problem the nickname rule exists for |
| `public_description`, `image` | The profile. Compliance-governed copy: no claim about what cannabis does |
| `is_published` | A profile is drafted before it is shown, so creating the row is never itself the act of publishing |
| `collection_address` | Where a courier collects. **Members never see it** |
| `bank_account_*` | Settlement. The account number is encrypted at rest and not blind-indexed — it is read back to the farm and to whoever runs the payout, never searched |
| `ProducerStorefront` | Which storefronts this farm sells into. A table rather than two booleans, because one farm may supply the club with cannabis and the market with vegetables |

**There is no pseudonym column.** `Producer.pseudonym` returns the trading name. A second namespace
for public names, free to hold a value identical to a member's nickname and impossible to constrain
across two tables, is the thing `backend.md` section 4.6 refused for sharing members and it is
refused here for the same reason.

**What settlement actually needs is still open — C10.** The fields above are the ones the drawio
cultivator story names ("My Farm — users, collection address, sharing members, bank details") and no
more. Whether the platform collects and remits or introduces and invoices is undecided, and that
answer may want a tax number, a mandate reference, or none of this.

## 3. The people

One `ProducerMembership` row per person per farm. `role` is a column on the **appointment**, not on
the person, which is what lets one account be primary at one farm and limited staff at another.

| Role | What the appointment carries |
| --- | --- |
| `primary` | The owner of the farm. Appoints staff, registers and manages sharing members, controls the farm's identity — plus everything full rights carry |
| `full` | The delegated commercial work: pricing, strain listings, allocation to sharing members, replies to reviews, catalogue requests — plus everything the base set carries |
| `limited` | Stock. Uploads, adjustments, status changes, fulfilment documents |

**One primary per farm, in SQL.** `producer_membership_one_primary` is a unique index over a derived
column that is null for everybody who is not the primary — the partial index it replaces is one
MySQL will not build, and Django omits what the backend cannot build without saying so
(`backend.md` section 8.2). A farm may have *no* primary for a while: a `Producer` created in the
admin before anybody is appointed is a legitimate intermediate state, and `Producer.primary` returns
`None` rather than raising at a call site that only wanted a name.

**One appointment per person per farm.** Somebody promoted from limited to full holds one
appointment that changed, not two.

### 3.1 "As permitted by the primary" is the tier — C13

The structure says staff act *as permitted by* the owner. **The permission being granted is
`role`.** Appointing somebody `full` is what permits them to transfer stock to a sharing member;
`limited` is what withholds it.

There is no per-appointment grant beside the tier, and that is a decision rather than an omission. A
set of tick-boxes on the appointment would be a second permission system standing next to
`accounts/roles.py`, which every screen would then have to ask twice — and no requirement anywhere
in `twp-tasks/` yet distinguishes a staff member who may allocate from one who may price. It is one
column on `ProducerMembership` the day one does.

### 3.2 What only the owner of the farm may do

| Action | Codename | Why it is not delegable |
| --- | --- | --- |
| Appoint and remove staff | `platform.appoint_cultivator_staff` | Staff appointing staff is a farm's access control leaving the farm owner's hands |
| Register and manage sharing members | `platform.register_sharing_member`, `platform.manage_sharing_members` | Creating records for other people is the one thing on this platform that has exactly one route — section 3.7 of `roles-and-permissions.md` |
| The farm's public identity | `platform.manage_own_cultivator_profile` | **Moved here from full rights by C13.** The name and image members buy under are the farm owner's, and a staff appointment that can rename the farm or take it off the storefront is a delegation nobody asked for |

**The offering deliberately stayed with full rights.** Pricing and strain listings are exactly the
commercial work "full rights" exists to delegate, and a farm whose primary is away still has to be
able to reprice a crop. So the split is: *identity* is the owner's, *offering* is delegable, *stock*
is every appointment's.

### 3.3 Where each rule is enforced

| Rule | Where |
| --- | --- |
| One primary per farm | Unique index, `producer_membership_one_primary` |
| The primary's actions are the primary's | `accounts.roles.permissions_for`, off `ProducerMembership.is_primary` |
| Full rights carry the commercial set | `permissions_for`, off `ProducerMembership.has_full_rights` |
| Staff may only touch **their own** farm's stock | `plant.stock._authorise`: asks `platform.manage_plant_stock`, then asks whether the caller is appointed to the farm named in the request |
| Staff may only touch their own farm's listings and pricing | **Not written yet.** The same shape as the row above — C13's open row |

## 4. The sharing member belongs to the farm

`membership.ClubMembership.registered_by` points at the **`Producer`**, not at the person who keyed
it in. A placeholder holds a farm's stock and must not be orphaned when the grower who created it
leaves.

A sharing member is a placeholder rather than a person — **C6** — so there is no identity number and
no consent attestation over it; and the cultivator acts as proxy for an owner who does not
transact — **C33**. What that means for ownership is section 5: an allocated plant is *owned* by the
placeholder, and the trail says so.

## 5. Every plant has a verifiable owner

`app/club/plant/models.py`. Two structures, doing two jobs:

- **`Plant.owner`** — the current holder, and null while the farm holds it. It answers *which
  member*, which is what every browse and inventory query asks, and keeps `available()` a
  one-column filter rather than a join. Written only by `Plant.transfer_to`.
- **`PlantOwnership`** — the append-only tenure log. One row per holding: who, from when, until
  when, and why. Nothing is ever edited, because this is what a certificate of ownership is evidence
  from and a row staff can retype is not evidence of anything.

### 5.1 The trail starts at the farm, and did not always — C13

The ledger used to open at the first sale, on the argument that "who has this belonged to" should
read as a list of members rather than one beginning with the grower. The requirement the structure
now states is stricter: *each plant must always have a verifiable owner, and there must be an audit
trail of all ownership until final ownership.* A trail that starts at the sale cannot say who held
the plant the day before it, and "the farm did, by implication, because the listing says so" is an
inference from another table rather than a record.

So the farm holds a tenure like anybody else:

| Reason | Held by | When it is written |
| --- | --- | --- |
| `cultivation` | The **producer** | By `Plant.save` on insert. Closed by the first transfer |
| `purchase` | A member | A member buys the plant |
| `swap` | A member | A swap zone match — Block 10 |
| `allocation` | A sharing member | `platform.allocate_sharing_member_stock` |
| `adjustment` | Either | A staff correction, and the only reason a plant may return to the farm — C9's substitution path |

A plant that was captured, sold and swapped once therefore reads: *Kloof → Sam → Alex*, three rows,
two of them closed, one open, no gap between them.

**The tenure is opened in `Plant.save`, not in the upload service.** The invariant is *every* plant,
and the service is only the bulk path — the admin's add form, a management command and a test
fixture all create rows too, and an invariant three of four creation paths keep is not an invariant.

### 5.2 What the database enforces, and what it cannot

| Rule | How |
| --- | --- |
| At most one open tenure per plant | `one_open_tenure_per_plant`, a unique index over `current_for_plant` — the derived-column device again, because the natural spelling is a partial index |
| A closed tenure cannot be reopened by hand | `current_for_plant_matches_released_at`, with an explicit null test because a CHECK passes when its condition is unknown |
| A tenure cannot end before it began | `tenure_ends_after_it_starts` |
| Exactly one holder: a member or a farm, never both and never neither | `tenure_has_one_holder` |
| A cultivation tenure is the farm's; a purchase, swap or allocation is a member's | `tenure_reason_matches_holder`. `adjustment` is free in both directions, on purpose |
| **`Plant.owner` equals the open tenure's holder** | **Nothing.** A cross-table equality is not something a check constraint can express |

That last row is the named gap. `transfer_to` writes both sides in one transaction and is the only
thing keeping them in step; a queryset `.update(owner=...)` walks past it, and a test asserts exactly
that so the gap is recorded rather than discovered. The mitigation is that the ledger — not the
column — is what a certificate is drawn from.

### 5.3 Two holder columns rather than a service account

`PlantOwnership` carries a nullable `owner` (a `User`) and a nullable `producer`, with a constraint
saying exactly one is set. The alternative was a user account standing in for each farm, which is
one foreign key instead of two — and an account nobody signs into, holding stock, that every
membership rule and every permission check would then have to exclude. Two nullable columns and one
constraint is the cheaper of the two.

### 5.4 A member views their own inventory

`Plant.objects.held_by(member)` is the read, and `platform.view_own_inventory` is the codename.
**The object-level rule is not written yet** — that is C13's remaining open row, along with a
cultivator's own listings and pricing. The ledger is what makes it answerable: "their own" is
`owner=request.user`, and "everything they have ever held" is `tenure_by_owner`.

## 6. What the audit trail is for

- **The certificate of ownership.** `plant-id-numbers.md` puts the platform serial, the farm's own
  plant ID, the cultivator pseudonym, the planting and harvest dates and the strain on a document
  handed to a member. The serial is short, sequential and readable precisely because it is quoted off
  paper and typed into a search box under pressure; the primary key is a UUIDv7 like everything else.
- **A trace.** The plant admin searches on both identifiers, and the ownership ledger is read-only
  throughout it — superusers included.
- **Whatever the swap zone turns out to need.** Block 10 is gated on a legal opinion (**C7**), and a
  chain of custody is the first thing anybody assessing it will ask to see.

The trail names members by nickname and farms by trading name — never a legal name and never an
email address. That is `roles-and-permissions.md` section 6.6 and **C19**, and it holds in the
admin, in `__str__`, and in the stock export, because an export is a file that leaves the platform.

## 7. What is not built

| Not built | Consequence |
| --- | --- |
| Endpoints for appointing staff, or a screen for it | `platform.appoint_cultivator_staff` is exercisable from the shell and the admin. The permission is enforced; the route is Block 2's |
| The object-level rule on listings and pricing | Full-rights staff hold the codenames; nothing yet asks *whose* listing. `plant.stock._authorise` is the pattern to copy — C13 |
| The object-level rule on a member's own inventory | Same shape, one table away — section 5.4 |
| The benchmark indicator on a cultivator's own listings | C12: a grower sees their own listings with an above / in line / below marker against comparable products site-wide, built as an aggregate by construction (cohort minimum, band not number, period average) |
| A return path to the farm | `transfer_to` takes a member. C9's substitution and refund path is undecided, and the ledger can already express the row it would write |
| Settlement | C10 |

## 8. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | `Plant.owner` and the open tenure can disagree, and no constraint can compare them. | Accepted and tested as a known gap — section 5.2. Closed the day every write goes through a service |
| 2 | `bulk_create` bypasses `Plant.save`, so a bulk insert would create plants with no cultivation tenure and no owner of record. | Mitigated by refusal: `services.write_plants` inserts one at a time and says why. Nothing else in the project bulk-creates plants |
| 3 | A farm with no primary holds no appointment that can appoint one, so recovery is an administrator's act in the Django admin. | Accepted. The alternative — letting full-rights staff promote themselves — is the delegation section 3.2 refuses |
| 4 | The trading-name uniqueness rule is a unique index over a derived column, and on MySQL the nickname's equivalent is a *partial* index that is silently omitted. | The producer's own key column is not nullable, so its index is unconditional and portable. The nickname hole is `accounts`' and is recorded there |
| 5 | An allocated plant is owned by a placeholder who cannot consent to anything, and the trail records that ownership as fact. | **C6, C7 and C33.** The legal exposure is theirs to carry; this document only records that the ledger states it plainly rather than obscuring it |

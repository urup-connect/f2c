# Conflict register

Where the brief in `twp-tasks/` disagrees with what is built, with itself, or with the older
planning documents — and what should be done about each one.

## How to read this

`twp-tasks/` is the statement of what the platform should do. The seven documents in `features/`
plus `backend.md` and `frontend.md` describe what exists today. `plan.md` and `todo.md` were older
than both and have now been rewritten against this register. Those sources did not agree, and this
file is where the disagreements are held so that neither side is quietly overwritten by the other.

The working rule for this pass, set by the product owner: **built functionality is presumed
correct.** A conflict between the brief and the build is therefore a question about the brief's
intent, not a defect report — unless it is marked otherwise below.

| Status | Meaning |
| --- | --- |
| **Decided** | Ruled on. The decision and its reason are recorded; `plan.md` and `todo.md` reflect it |
| **Open** | Needs a product decision before the work it touches can be specified. Blocks the item named |
| **Drift** | Not a real disagreement — a design document has fallen behind the code. Fixed by editing the document |
| **Legal** | Needs an opinion from outside this project before it can be built either way |

Conflicts are numbered and kept. A resolved one is marked resolved rather than deleted, because the
rejected reading is usually the more useful half.

---

## A. Decided in this pass

### C1 — The technology stack in `plan.md` is not the stack that was built

**Status: Decided.**

`plan.md` specified ASP.NET Core Web API, Entity Framework Core, Microsoft Entra ID B2C or Auth0,
and an Azure App Services deployment. The system is Django 5 with django-ninja, a Next.js App
Router frontend, passkeys with an emailed-code fallback written in-house, and Payfast.

**Decision.** `plan.md` has been rewritten around the stack that exists. The earlier stack is
recorded here rather than in the plan, because a roadmap naming a technology nobody is using sends
every future reader to the wrong place.

Two things stay open inside this decision and are carried as work rather than as conflict: SQLite is
the development database and no production database has been provisioned (`uuid7` primary keys were
chosen anticipating PostgreSQL), and no hosting target has been chosen. Azure remains plausible;
nothing in the code depends on it.

### C2 — One administrator role, or two

**Status: Decided — adopt two.**

`twp-tasks/member-roles.md` describes a single Admin. The drawio stories describe two distinct
administrators with different reach:

| | Club Administrator | UC Administrator |
| --- | --- | --- |
| Members, cultivators, sharing members | Manage | Manage |
| Inventory, pricing, strains, product types | Manage | Manage |
| Membership subscriptions and payments | Not listed | **Manage** |
| Administrator accounts | Not listed | **CRUD** |
| Escalation | **Escalates to** UC Administrator | **Receives** escalations from Club Administrator |

`app/accounts/roles.py` has one `admin` role holding the whole administrative catalogue.

**Decision.** Adopt the two-tier model. The Club Administrator runs the club day to day; the UC
Administrator is the platform operator, holds the money and the administrator accounts, and is where
a club administrator escalates.

What this changes:

- A fifth role. `accounts.User.role` gains `uc_admin`; the existing `admin` becomes the club
  administrator. The check constraint and the catalogue test move with it.
- The administrative catalogue in `roles.py` splits. `platform.refund_transaction`,
  `platform.cancel_membership` and a new `platform.manage_administrators` go to the UC tier alone.
- `createsuperuser` should default to `uc_admin`, not to the club tier.
- `club-navigation.ts` gains an escalation destination and a second administration band.
- An escalation queue is a new model, not a permission. It sits in `todo.md` Block 9.

**The migration risk is named here so it is not discovered later:** every account currently holding
`admin` is a club administrator under the new reading, and at least one has to be promoted by hand.
A data migration cannot guess which.

### C3 — Two domains, one application

**Status: Decided — split the domains, cannabis only.**

The member stories put a public marketing site at `f2c.co.za` carrying seven categories — Biltong,
Fruit, Vegetables, Nuts, Dried, Honey, Cannabis — and the member zone at `f2c-cannabis.co.za`. The
build is one Next.js application serving a landing page and the club behind it.

**Decision.** Treat the two domains as real: the public site and the member zone are separately
addressed, separately indexed and separately deployed. **Only the cannabis category is in scope.**
The other six are recorded here and planned for nothing.

What this changes: `SITE_URL` becomes two values, the `robots` and canonical rules in
`features/landing.md` section 5 apply per host rather than per environment, and the age gate and
sign-up flow sit on the cannabis host.

*In passing: `plan.md` listed a "Billing category page". That was Biltong.*

### C4 — "Leaf rating" means two different things

**Status: Decided — the swap-zone definition wins.**

`twp-tasks/swap-zone.md` defines the leaf rating as a **unit of swap value derived from grow price**:
`grow_price / 1000`, rounded to the nearest 0.5. It exists so the swap zone can show relative worth
without showing Rands.

The older `plan.md` and `todo.md` described a "Leaf Rating System" as a reputation feature — "User
ratings", "Cultivator ratings", "Rating calculation engine", "Update leaf ratings from swaps". That
is the reviews feature wearing the swap feature's name.

**Decision.** Leaf rating is swap value and nothing else. Reputation is **stars**, out of five, per
`twp-tasks/reviews-ratings.md`. The two are unrelated, and nothing about a leaf rating changes when
a review is left. `plan.md` and `todo.md` now separate them.

**One gap the definition leaves, carried into `todo.md` as a specification task:** the tie-break is
undefined. A grow price of R1,250 gives 1.25, equidistant between 1.0 and 1.5. The brief's five
worked examples all avoid the midpoint. Round half up is the conventional choice and favours the
member offering the plant.

### C5 — The administrative portal: Next.js or Django admin

**Status: Decided — Next.js, with the Django admin retained as the operator's tool.**

`twp-tasks/member-roles.md` heads its administrator section "**Admin (NextJs)**". The build has no
administrative API at all: `roles-and-permissions.md` section 13 records that no endpoint checks a
`platform.*` permission, and `frontend.md` section 9 records that the nine administrative
destinations have nothing behind them. Administration is done by hand in the Django admin.

**Decision.** Build the administrative screens in Next.js against a real API, as the brief asks. The
Django admin stays, but as the platform operator's back-office tool rather than as the club's
interface — the distinction `roles-and-permissions.md` section 9 already draws between `is_staff`
and `role`.

**Consequence, and it is the largest single piece of work in the plan:** every administrative action
in the catalogue needs an endpoint, and every one of those endpoints needs an object-level rule that
does not exist yet. See C13.

---

## B. Open — needs a product decision

### C6 — What a sharing member actually is

**Status: Open. Blocks the swap zone, and see C7.**

`twp-tasks/member-roles.md` says two things that do not sit together:

> Cultivators can register sharing-members — minimum info will be name, ID and nickname.

> Sharing member is actually not a role, no login. They are essentially **placeholders** to keep
> stock that is already in flower.

The build takes the first sentence literally: a sharing member is a real person, a `User` row with
an encrypted identity number, registered under a cultivator's POPIA attestation
(`features/roles-and-permissions.md` section 3.3), and covered by the one-account-per-identity-document
rule.

If they are placeholders, almost none of that is needed, and the attestation machinery is ceremony
around a fiction. If they are real people, the machinery is right and C7 is a live legal question.

| | Real people | Placeholders |
| --- | --- | --- |
| Identity number | Required, encrypted, POPIA-relevant | Not collected |
| Attestation | Necessary and load-bearing | Meaningless |
| One account per ID | Applies, and leaks (roles risk 4) | Does not apply |
| Four-plant allocation | Consumes that person's legal allowance | Consumes nobody's |
| Legal exposure | Real — see C7 | The club holds the stock itself, which is its own problem |

**Recommendation.** Decide before any swap-zone work starts. The build has already committed to
"real people", and unwinding it later means a migration that deletes identity numbers.

### C7 — Whether the sharing member scheme is lawful as described

**Status: Legal. Blocks the swap zone.**

`twp-tasks/stock-holding-limit.md` sets out the Cannabis for Private Purposes Act position: four
flowering plants per adult in a private place, strictly for personal use, and **selling cannabis
remains illegal**.

The sharing-member scheme has a cultivator allocate four flowering plants to a named adult so those
plants appear in the swap zone. Three questions follow, none of them a software question:

1. Does allocating four flowering plants to a person consume that person's own statutory allowance,
   such that they may hold nothing else?
2. Where are those plants physically? The Act's limit attaches to cultivation in a private place. If
   the plants are on the cultivator's premises, the sharing member is not cultivating them.
3. Does a member giving up a plant and receiving a flowering plant in return constitute a swap, or a
   sale in substance? The platform charges a grow price in Rands at purchase, and the swap zone
   deliberately hides Rands behind leaf ratings.

This is also risk 5 in `features/roles-and-permissions.md`, which asks for legal review of the
attestation wording. That review should be widened to cover the scheme itself, not only its wording.

**Recommendation.** Get an opinion before building the swap zone. It is the feature most exposed to
being unbuildable as specified, and it is scheduled late enough that an opinion can be obtained
without blocking anything else.

### C8 — Is anything payable at harvest

**Status: Open. Blocks order fulfilment.**

Two briefs disagree in one sentence each:

> `product-types.md`: Pre-rolls and loose will not have a cost to start with, so **nothing is due to
> be paid** when the member makes this choice.

> `harvest.md`: the owner should receive a notification to finalise their transaction: Final product
> type choice — **Courier booking and fee**.

The old `plan.md` Phase 4 said "Capture final payment", which assumes the second.

The question is whether the courier fee is a fee to the member. If it is, fulfilment needs a second
payment flow — and the payments app today handles a recurring membership subscription only, with no
order payments and no stored payment methods.

- **Courier fee charged to the member at harvest.** Fulfilment needs a checkout. Largest build.
- **Courier fee included in the grow price.** Fulfilment is a confirmation screen with no money in
  it, and a cultivator's grow price is understood as a delivered price. Simplest, and it keeps the
  "nothing is due" promise honest.
- **Charged only for non-default delivery.** Standard courier included, express or outlying-area
  surcharged. Middle path; needs a rate card the platform does not have.

**Recommendation.** Include it in the grow price for launch. It removes a payment integration from
the critical path and matches the sentence a member will actually read.

### C9 — When the grow price is paid, and what happens when a crop fails

**Status: Open. Blocks the ordering workflow.**

`member-plant-purchase.md` has the member add plants to a cart and the system allocate serials. It
does not say when money moves. The plant is then grown for months before the member receives
anything.

Three readings are consistent with the brief — payment in full at order; a deposit at order with the
balance at harvest; payment at harvest with the order as a commitment. Each implies a different
position when a plant dies, and **no document in `twp-tasks/` says what happens when a crop fails.**
A member has paid for a specific serialised plant that no longer exists. Substitution, refund and
credit are three different products.

**Recommendation.** Payment in full at order, with a defined substitution-or-refund rule for crop
failure. Anything else needs a receivables ledger the platform does not have.

### C10 — Cultivator settlement is entirely unspecified

**Status: Open. Not a conflict between documents — an absence in all of them.**

The drawio cultivator story asks for "My Farm — users, collection address, sharing members, **bank
details**" and a "**Statement of Account, payment due**". The club administrator story asks for
"Statement of Account, payments due, **record payments made**".

No document in `twp-tasks/` describes this, and nothing is built. It is a complete commercial
domain: the platform takes a member's money for a grow service performed by a third party and has to
remit it.

What has to be decided before it can be specified:

- Does the platform collect and remit, or introduce and invoice a commission?
- What is the platform's take, and is it visible to the cultivator?
- When does a cultivator earn — at order, at harvest, at delivery?
- Who carries a refund (C11) — the platform or the cultivator?
- Payfast is a collection gateway. Payouts need something else, or a manual EFT run.

**Recommendation.** Treat as its own discovery item with the finance owner. It is a launch blocker
for cultivators even though no member-facing screen depends on it.

### C11 — Refunds are required and are not built

**Status: Open.**

`member-roles.md` gives the administrator the power to "reverse/refund transactions or part of
transaction (transaction/platform fees can be withheld)", and `platform.refund_transaction` is in
the catalogue. `features/payments.md` section 9 states plainly: **no refunds, no proration, no plan
changes.**

Partial refunds with fee withholding are not a button on a gateway. They need a transaction ledger
that can express a partial reversal, and they interact with C10 — refunding a plant order takes
money back from a cultivator who may already have been paid.

**Recommendation.** Specify refunds together with settlement, not before.

### C12 — A cultivator cannot buy, and the drawio story says they browse

**Status: Open. Low urgency, cheap to resolve.**

`features/roles-and-permissions.md` section 5 records the decision that one account holds one role,
and its accepted cost: the Cultivator role does not hold `platform.purchase_plants`,
`platform.use_swap_zone` or `platform.offer_inventory_for_swap`. A test asserts this, so the set
cannot be widened without a decision.

The drawio cultivator story lists "View all plants available (**includes other cultivators' offers**)"
under The Plantation. Browsing is granted — cultivators hold `platform.browse_catalogue` — so the
story is satisfiable. But a grower shown a competitor's offers and unable to act on them is an odd
screen, and the story may intend more.

**Recommendation.** Confirm browsing is all that is meant. If cultivators should buy, that is roles
risk 2 and the answer is a second account, not a widened role.

### C13 — Object-level rules do not exist, and half the brief needs them

**Status: Open. Structural. Blocks most of Blocks 4 to 9 in `todo.md`.**

`RoleBackend` refuses object-level questions outright — `has_perm(perm, obj)` returns `False` rather
than answering from the role. That is correct, and it means these requirements have nothing to
enforce them:

| Requirement | Source | What it needs |
| --- | --- | --- |
| Only the **primary** cultivator appoints staff and registers sharing members | `member-roles.md` | A cultivator organisation with a primary flag |
| A cultivator manages **their own** listings, stock and pricing | `member-roles.md` | Ownership on every one of those models |
| A cultivator manages **the sharing members they registered** | `member-roles.md` | `registered_by` exists; nothing checks it |
| A member views **their own** inventory | `member-roles.md` | Ownership on the plant |
| Club administrator versus UC administrator reach | C2 | Tier comparison at every administrative endpoint |

This is risk 9 in `features/roles-and-permissions.md`, marked "must be resolved with the cultivator
organisation, not after". This register agrees, which is why `todo.md` puts the cultivator
organisation in Block 2.

### C14 — Whose sharing members an administrator may touch

**Status: Open. Small, but it contradicts a decision already taken with reasons.**

`features/roles-and-permissions.md` section 3.6 deliberately withholds
`platform.register_sharing_member`, `platform.manage_sharing_members` and
`platform.allocate_sharing_member_stock` from the Admin role, on the argument that creating accounts
for other people should have exactly one route.

Both drawio administrator stories list "Cultivators crud, users crud, **sharing members crud**".

**Recommendation.** Keep the decision and satisfy the story through the operator's back office —
which is what the section already prescribes. But if the club administrator is a Next.js user under
C5 and has no Django admin access, that route does not exist for them, and the decision has to be
revisited. Flagged because C5 moved the ground under it.

### C15 — Household limits and the dried-weight limit are not modelled

**Status: Open.**

`stock-holding-limit.md` states three limits. One is enforced in design; two are not mentioned again
anywhere:

| Limit | Status |
| --- | --- |
| Four flowering plants per adult | `SHARING_MEMBER_PLANT_ALLOCATION = 4`, enforced nowhere yet because there is no plant model |
| Eight plants per household where two or more adults live | Not modelled. The platform has no concept of a household |
| 600g dried per person, 1.2kg per household | Not modelled. The platform has no concept of weight held |

The household limit is *more* permissive than the per-adult one, so ignoring it is safe. The
dried-weight limit is a genuine gap: a member taking repeated delivery of harvested product could
exceed it and the platform would not know.

**Recommendation.** Enforce four flowering plants per member. Record the other two as accepted risks
with a stated reason — the platform cannot observe what a member holds off-platform, so any
enforcement would be theatre. Say so in the club rules rather than pretending to enforce it.

### C16 — Does a harvested plant count toward the four

**Status: Open. Blocks the swap-zone holding check.**

The Act's limit is on *flowering* plants. `harvest.md` allows a sharing member's harvested item to
sit in the swap zone and be swapped for, so a member can end up holding a harvested plant.

If harvested plants do not count, a member can hold four flowering plus any number of harvested, and
the holding check has to distinguish. If they do count, the swap `harvest.md` explicitly permits
could be refused by the holding rule — two briefs producing opposite answers on the same
transaction.

**Recommendation.** Harvested plants do not count toward the flowering limit; the holding check
counts only `preflowering` and `in_bloom`. This is also the reading the Act supports.

### C17 — Swapping for equal value defeats the reason to swap

**Status: Open. Worth resolving before the swap rules are written.**

`swap-zone.md` requires the offer and the request to have **equivalent leaf value**, with the option
for the member to accept a lower-valued request and forfeit the difference.

`member-roles.md` and `stock-holding-limit.md` describe the intended use: a member over the flowering
limit swaps a flowering plant for a pre-flowering one. And the reason a member enters the swap zone
at all, per C6's placeholder rationale, is to get product sooner — swapping a seedling for something
closer to harvest.

Leaf rating derives from grow price alone. **Maturity is not in it.** So a plant three weeks from
harvest and a seedling of the same strain and grow price carry the same leaf rating, and the swap
zone prices a real difference in value at zero. Every member wants the mature side of that trade,
and the rules as written cannot arbitrate.

- Accept it. First come, first served on a queue; sharing-member stock is consumed quickly.
- Add a maturity multiplier to the leaf rating. Changes a formula the brief states explicitly.
- Make swaps for mature stock require confirmation rather than being instant. The member story
  already distinguishes "instant swaps (sharing members' plants)" from "swaps requiring confirmation
  (regular members' plants)" — extending confirmation to mature sharing-member stock is a small
  change to a rule that already exists.

**Recommendation.** The third. It uses a distinction the brief already draws.

### C18 — Where the finished product types live

**Status: Open. Small, but it decides a schema.**

Three documents put the list of available finished product types in three places:

- `cultivator-stock-upload.md`: "Finished Product Types Available" is a field **on each plant** at upload.
- `member-roles.md`, cultivator section: "Manage their own strain listings — image, description,
  **available finished product type**, price" — so it is on the strain listing.
- `member-roles.md`, admin section: "Finished product types and prices" are CRUD'd **platform-wide**.

All three can be true — the platform defines the universe, the listing narrows it, the plant narrows
it again — but only if decided deliberately. Otherwise three screens edit the same list and the
narrowest one silently wins.

**Recommendation.** Platform defines the catalogue; the strain listing selects a subset; the plant
inherits from its listing and may narrow further only if a real case needs it. Default to no
per-plant override.

### C19 — Pseudonymity versus delivery

**Status: Open. POPIA-relevant.**

`member-roles.md`: "Members info should be concealed behind a nickname."
`features/roles-and-permissions.md` section 6.6 records this as a property of every API payload: any
endpoint returning another member must expose `display_name` and nothing else.

But fulfilment requires a delivery address, and `member-roles.md` gives the cultivator
`platform.view_fulfilment_documents` — "ownership certificates, packing labels and shipping
documents for the courier". A packing label carries a name and an address.

- Does the cultivator see the member's legal name and address, or only a courier waybill reference?
- Does the certificate of ownership (`plant-id-numbers.md`) name the member, or their nickname?
- Is there a collection-address model, so the club is shipper of record and the cultivator never
  sees a member address?

The drawio cultivator story lists "collection address" under My Farm, which suggests the third — the
courier collects from the cultivator, and the club or the courier holds the member's address.

**Recommendation.** The cultivator never sees a member address. Fulfilment documents carry the
nickname, the plant serials and a waybill number. This keeps section 6.6 true and is what the
collection address implies.

### C20 — Landing page copy rules forbid what the landing page brief requires

**Status: Open. Cheap to fix, but a real contradiction.**

`features/landing.md` section 3 applies copy-compliance patterns that refuse retail voice and
currency on the public page. `plan.md`, `todo.md` and the member story all require the landing page
to display membership fees and show "T's, C's, Rules, **Cost**".

`landing.md` section 6 already anticipates this: "Copy for one would need the `CURRENCY` and
`RETAIL_VOICE` exemptions noted in section 3, and neither the screen nor the backend behind it
exists."

**Recommendation.** Carve a named exemption for the membership fee specifically — one figure, one
place, on an allowlist — rather than relaxing the pattern. The pattern exists because a cannabis
club advertising a price is a different legal object from a club stating a subscription.

---

## C. Documentation drift — fix by editing, no decision needed

### C21 — Profile editing is built and two documents say it is not

`frontend.md` section 9 says "Nothing is editable. `platform.manage_own_profile` has no screen and
no endpoint". `roles-and-permissions.md` section 13 lists it among the unbuilt.

It is built: `frontend/app/(club)/profile/page.tsx`, `app/accounts/profile.py`,
`app/accounts/avatars.py`, and four endpoints — `GET`/`PUT /api/accounts/me/profile`,
`POST`/`DELETE /api/accounts/me/avatar`. `club-navigation.ts` already marks `own-profile` as the one
`ready` destination.

**Action:** correct `frontend.md` section 9 and `roles-and-permissions.md` section 13.

### C22 — `todo.md` said sign-up stores nothing

The old `todo.md` carried "Create signup/registration process — form built, nothing is stored yet".
`membership.services.register_member` writes the member, `POST /api/members/register` is live, and
`features/sign-up.md` risk 11 is marked closed. Corrected in the rewritten `todo.md`.

### C23 — `backend.md` risk 12 says the project is not under version control

It is. The repository exists, `.gitignore` covers the Python artefacts, and the work is committed on
`master`.

**Action:** close risk 12 in `backend.md`.

### C24 — 125 source comments cite documents that do not exist

Recorded in `design/README.md` with a mapping table, deliberately not fixed. Repeated here so it is
counted among the known drift rather than rediscovered.

**Action:** none. The mapping table is the fix.

### C25 — A test fails roughly one run in thirty

`frontend/app/api/nickname/availability/route.test.ts` asserts an eight-character random hex
reference does not contain `"500"`, `"503"`, `"429"` or `"422"`. All four are valid hex. Known,
one-line fix, not yet taken — `frontend.md` risk 6. Carried into `todo.md` Block 0 so it stops being
a note.

---

## D. Production blockers already recorded, restated so they are counted

Not conflicts. They are in `todo.md` Block 0 because nothing in the brief can be demonstrated to
anybody without them.

| # | Blocker | Recorded in |
| --- | --- | --- |
| P1 | No email provider. Sign-in codes and payment links print to a console. **No member can sign in on a deployed environment** | `authentication.md` risk 2, `backend.md` risk 3 |
| P2 | Nothing schedules `lapse_memberships`. An unpaid membership keeps access indefinitely | `payments.md` risk 2 |
| P3 | `LocMemCache` makes every rate limit per worker | `backend.md` risk 2, `authentication.md` risk 1 |
| P4 | No documented backup or rotation for `DJANGO_FIELD_ENCRYPTION_KEY`. Losing it destroys every stored identity number | `backend.md` risk 1 |
| P5 | Staff password sign-in at `POST /api/auth/login` is not restricted to staff | `authentication.md` risk 5 |
| P6 | `NEXT_PUBLIC_DJANGO_API_URL` is baked in at build time, so one artefact cannot serve two environments | `frontend.md` risk 2 |

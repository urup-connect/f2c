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
| **Legal** | Needs an opinion from outside this project before it can be built either way. **Nothing carries this status now** — C7 was the only one, and it is decided as residual risk |

Conflicts are numbered and kept. A resolved one is marked resolved rather than deleted, because the
rejected reading is usually the more useful half.

**A decision can be reversed, and one has been.** C6 was decided, acted on, and then reversed when
the product owner supplied information the register did not have. The superseded reading stays in
the entry alongside the new one — a decision that was wrong for a stated reason is worth more than a
clean entry, because the reason is usually still live somewhere else.

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

**Both of the things this entry left open have since been closed, and neither closed the way it was
written.** The database is MySQL 8.4, not PostgreSQL — `f2c/database.py`, `app/common/checks.py`
and the CI job were built against it, and `uuid7` keys turn out not to have needed PostgreSQL after
all. The hosting target is Azure, in West Europe, as three containers and a managed database. Both
are recorded in **C31**, which supersedes this paragraph.

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

`app/core/accounts/roles.py` has one `admin` role holding the whole administrative catalogue.

**Decision.** Adopt the two-tier model. The Club Administrator runs the club day to day; the UC
Administrator is the platform operator, holds the money and the administrator accounts, and is where
a club administrator escalates. (**"Holds the money" is no longer true of the platform**, and the
phrase is left standing only because the decision it belongs to is about reach rather than banking:
C10's money map puts member transactions in the *club's* account, with the platform taking a
commission out of them. The UC tier still holds the powers that move money — refunds and
cancellations — which is what this decision was about.)

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

**Amended by C29.** The two tiers stand. The mechanism does not: the UC tier is not a fifth value in
the role column and has no Next.js surface. It is `is_staff` in the Django admin. `platform.
manage_administrators`, `platform.refund_transaction` and `platform.cancel_membership` therefore
never enter the catalogue, and `createsuperuser` needs no role argument. The migration risk above
also disappears — see C27 on the database being rebuilt.
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

**Amended by C26.** The two hosts stand. What has changed is the other six categories: they are not
six future sites, they are the catalogue of a second storefront. See [`verticals.md`](verticals.md).

**Amended by C30.** The two hosts stand; their assignment does not. `f2c.co.za` is the **market**,
not a marketing shell, and `f2c-cannabis.co.za` is the **club** — landing page, age gate and member
zone together. The API answers on `backend.f2c.co.za` and `backend.f2c-cannabis.co.za`. See C30.

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

*An entry here marked **Decided** was resolved after this section was written. It stays in place
rather than moving, so the reasoning that made it open is still next to the answer.*

### C6 — What a sharing member actually is

**Status: Decided, reversed 31 August 2026. A sharing member is a real person who does not transact.
The identity machinery comes back. The login is specified now and built later.**

`twp-tasks/member-roles.md` says two things that do not sit together:

> Cultivators can register sharing-members — minimum info will be name, ID and nickname.

> Sharing member is actually not a role, no login. They are essentially **placeholders** to keep
> stock that is already in flower.

The first pass read the second sentence as the definition and decided the placeholder. That reading
is now withdrawn.

#### Why it was wrong

The product owner's position, given after the placeholder decision was taken and acted on:

- A sharing member **is a real person**. They simply do not transact on the platform.
- They should **probably have a login** to view their plants. The role was written as a placeholder
  because Glide charged per user; **that constraint no longer applies.**
- Legally they **have some form of access and control over what they own**.
- Their plants **consume that person's own statutory allowance**.

The load-bearing sentence is the second one. "No login" was never a statement about what a sharing
member *is* — it was a cost control against a per-user licence on a platform that has since been
replaced. The placeholder decision inferred a product intention from a pricing artefact, and once
the pricing went, the sentence stopped meaning what it appeared to mean. "Name, ID and nickname" —
the sentence that reads as an accident of drafting next to it — was the definition all along.

#### The decision, against the table that framed it

| | **Decided: real person** | Superseded: placeholder |
| --- | --- | --- |
| Identity number | Required, encrypted, POPIA-relevant | Not collected |
| Attestation | Necessary and load-bearing | Meaningless |
| One account per ID | Applies, and leaks — risk 4 reopens | Does not apply |
| Four-plant allocation | Consumes that person's legal allowance — **confirmed**, see C7 | Consumes nobody's |
| Sign-in | Read-only, deferred — see below | Never |
| Legal exposure | Real, and now assessed — C7 | The club holds the stock itself |

#### What comes back into the schema

Everything Block 0.5 removed on the strength of the superseded reading, in
`membership.ClubMembership` unless noted:

- `sharing_consent_attested_by`, `sharing_consent_attested_at`, `sharing_consent_version`. A
  cultivator captures a third party's identity number, so POPIA needs a lawful basis the person did
  not give on a form. It is an attestation rather than a consent because it is weaker evidence than
  the person's own act, and the naming is what stops the two being confused later.
- The age rule read off the identity document. Eighteen, the same rule as sign-up.
- The identity number, collected by `accounts.services.register_sharing_member` again. The column
  never left `User` — C27 — so this is a service change, not a schema one.
- The erasure route and the `erased_at` exemption. A real person has personal data and a right to
  have it erased, and the erasure route must never be the thing the database refuses.
- `sharing_member_is_complete`, requiring the registering cultivator, the attestation and a
  nickname, with erased rows exempt. It replaces `sharing_member_has_a_cultivator`, which required
  only the cultivator.

#### What is new, and was in neither column

**A login.** Read-only: the sharing member signs in, sees the plants they own and their status, and
does nothing else. No cart, no swap action, no subscription, no payment method. This is the "access
and control of what they own" point, and it is the half of the reversal that has no precedent in
either of the original readings.

**It is specified now and built later.** The two halves have very different costs and very different
deadlines:

- The identity and consent machinery is **cheap now and expensive later**. The argument that carried
  the placeholder decision — Block 0.5 dropped the database and cleared every migration, so the
  deletion was free exactly once — runs identically in reverse. Adding these columns to an empty
  schema is an edit to `0001_initial`. Adding them once real sharing members exist is a migration
  plus a backfill of data nobody collected at the time.
- The login is **the same cost whenever it is built**. It is an authentication path, a screen and a
  permission set, and none of that gets harder for waiting.

So: restore the person, keep the account non-authenticating for launch, and turn sign-in on as its
own piece of work. A sharing member registered in the interim is a complete record with an
attestation and an identity number — the person can be given access later without anyone having to
go back and ask them for anything.

`UserStatus.NON_AUTHENTICATING` survives the reversal unchanged, and the reason it does is the reason
it was named that way: it describes what the authentication stack needs to know — this row signs in
nobody — rather than the club concept sitting on top of it. When the login is built, a sharing member
moves to `ACTIVE` and the status column needs neither renaming nor a new value.

#### What the build says today, and now contradicts this decision

Changed under the superseded reading and not yet changed back. This pass is documents only; none of
it is touched.

| Where | What it says |
| --- | --- |
| `app/core/accounts/services.py` | Module docstring and `register_sharing_member` both state a sharing member is not a person. Takes `nickname` only — no names, no identity number, no age check, no attestation |
| `app/core/accounts/services.py` | `IdentityNumberUnavailable` is defined and unreachable — nothing collects an identity number to collide with |
| `app/club/membership/models.py` | `sharing_member_has_a_cultivator` constraint; the attestation columns are absent; `MembershipStatus.SHARING` is labelled "Sharing member (no sign-in)" |
| `app/core/accounts/tests/test_sharing_members.py` | `AbsenceTests` asserts the removals — it will fail on the restoration, which is what it is for |
| `design/features/roles-and-permissions.md` §3.1–3.5 | Records the placeholder decision as settled, and closes risks 4, 5 and 6 on the strength of it |
| `design/backend.md` §3.6 | Describes the *pre*-C6 build and is therefore closer to this decision than the code is — but names `UserStatus.SHARING` and `sharing_member_never_signs_in`, which no longer exist |

`SHARING_MEMBER_PLANT_ALLOCATION = 4` needs no change and is a stronger rule than it was: under the
placeholder it was a convention with no obvious owner, and it is now a statutory ceiling attaching to
a named adult. Enforcing it is C15.

#### What this does not decide

Who may move a sharing member's stock, and on whose authority — **C33**. Whether a sharing member may
also hold a full membership — **C34**. Both were raised by this reversal and neither is answered here.

### C7 — Whether the sharing member scheme is lawful as described

**Status: Decided — residual risk. No longer blocks the swap zone.**

`twp-tasks/stock-holding-limit.md` sets out the Cannabis for Private Purposes Act position: four
flowering plants per adult in a private place, strictly for personal use, and **selling cannabis
remains illegal**.

The product owner's position, on which this is decided:

> The whole principle is that people can grow, share and swap cannabis in private — growing by a
> cultivator is private and each specific plant has an owner when it becomes cannabis (flowering).
> The general opinion is that this could be argued as within the law. The consensus is that the swap
> model is legit and it's used already by other clubs, so swapzone should be defendable.

The three questions this entry opened, answered:

**1. Does allocating four flowering plants to a person consume that person's own statutory allowance?
— Yes.** Settled by the product owner. This is the answer that costs something: the four is no longer
a convention the platform may interpret, it is a ceiling attaching to a named adult, and a sharing
member holding four flowering plants may hold nothing else. It makes C15 (enforce four per member)
and C16 (whether a harvested plant still counts) prerequisites of the swap zone rather than
refinements of it.

**2. Where are the plants physically? — Unresolved, and the weakest leg.** The Act's limit attaches
to cultivation in a private place. The plants are on the cultivator's premises and the sharing member
is not cultivating them. The position is that the cultivator's grow is itself private, and that
ownership attaches at flowering rather than at cultivation. That is an argument, not a settled point,
and it is carried below rather than claimed as resolved.

**3. Is a swap a sale in substance? — Working position: a swap.** The model is in use by other clubs
and is treated as defendable. The residual exposure is of the platform's own making: it charges a
grow price in Rands at purchase, then hides Rands behind leaf ratings in the swap zone. Deliberate
obfuscation reads badly if the model is ever tested, and the mitigation is to keep the leaf rating
honest — a coarse rounding of a real, disclosed price, never a currency, and never a unit anything is
settled in. **No money moves in the swap zone.**

#### The residual risks, carried by name

| | Risk | Position |
| --- | --- | --- |
| **R-C7.1** | The proxy leg: a sharing member's plants are offered by the cultivator, who paid for them, to members who pay for them — the sharing member never transacts | The named grey area. Held as C33, with the role designed to be droppable |
| **R-C7.2** | The plants are on the cultivator's premises, and the owner is not the cultivator | Accepted. Argued on private cultivation plus ownership attaching at flowering. Worth an opinion; does not gate the build |
| **R-C7.3** | Leaf ratings obscure a Rand price the platform itself set | Mitigated by construction — the rating is a rounding of a disclosed price, and the swap zone moves no money |
| **R-C7.4** | The attestation is a cultivator's word, not the sharing member's own act | Reopened by C6, having been closed on the placeholder reading. Risk 5 in `roles-and-permissions.md` returns, and the login is what eventually closes it: a person who signs in can consent for themselves |

#### What changes in the plan

Block 10 / Block E is **no longer gated on a legal opinion**. It proceeds on the working position
above. An opinion is still worth obtaining and its brief is now narrow: the proxy leg (R-C7.1) and
the physical-location argument (R-C7.2), not the swap model as a whole.

This does not make the scheme safe by decision. It records that the risk has been assessed by the
person entitled to carry it, and that the build proceeds on that basis.

### C8 — Is anything payable at harvest

**Status: Decided — nothing is payable at harvest in the MVP. Courier is carried inside the price
the member pays at order and settled to Pargo out of that transaction.**

Two briefs disagreed in one sentence each:

> `product-types.md`: Pre-rolls and loose will not have a cost to start with, so **nothing is due to
> be paid** when the member makes this choice.

> `harvest.md`: the owner should receive a notification to finalise their transaction: Final product
> type choice — **Courier booking and fee**.

The old `plan.md` Phase 4 said "Capture final payment", which assumes the second.

Three readings were available:

- **Courier fee charged to the member at harvest.** Fulfilment needs a checkout. Largest build.
- **Courier fee included in the grow price.** Fulfilment is a confirmation screen with no money in
  it, and a cultivator's grow price is understood as a delivered price. Simplest, and it keeps the
  "nothing is due" promise honest.
- **Charged only for non-default delivery.** Standard courier included, express or outlying-area
  surcharged. Middle path; needs a rate card the platform does not have.

**Decision: the second, with one correction to where the money actually sits.**

*The launch catalogue has no manufacturing cost.* Loose flower and pre-rolls are the only finished
product types at launch, neither carries a charge, and `product-types.md`'s sentence is therefore
true as written — the member reaches the harvest screen and is asked for nothing. Oil, gummies and
anything else that has to be manufactured are planned, they do carry a cost, and they will want a
payment at exactly this point. That build is **C35** and it is not in the MVP.

*`harvest.md` is half right.* The courier **booking** is real and belongs here. The **fee** is not a
second charge to the member: it is inside the price paid at order, and it is separated out at
transaction settlement and remitted to **Pargo**, the courier service the platform will transact
through. This is not the same as a cultivator quietly absorbing delivery — settlement becomes a
three-way split rather than two, and **C10 carries the consequence**: what reaches a cultivator is
the listed price less the platform's commission *and* less the courier component. C10 has to say who
sets that component and who carries it when the actual Pargo charge exceeds it. **C10 now puts a
number on the commission — 15% — which makes the order of the two legs an amount rather than a
presentational question**: 15% of the delivered price and 15% of the price net of courier are
different sums, and nobody has said which is meant.

**The confirmation step survives with no money in it, and it is not ceremonial.** Months can pass
between purchase and harvest, and more between harvest and delivery. An address captured at order is
stale by the time anything ships, and a finished product type cannot sensibly be chosen against a
plant that does not exist yet. So the harvest notification stands exactly as `harvest.md` describes
it, minus the payment: when the plant is harvested and enters processing, the owner confirms the
**finished product type** and the **delivery address**, and that confirmation is what makes
ownership final.

**Ownership final means the swap window closes.** A plant may be swapped up to harvest. Once its
owner has confirmed product type and address it is locked to them and leaves the zone. A confirmed
address and a confirmed product type are facts about one specific person, and a swap after that
point invalidates both silently — which is the failure mode the rule exists to prevent.

**One case is not covered by that rule, and it is the one C16 is about.** The lock is triggered by
the owner's confirmation. Sharing-member stock sitting in the zone has no such event — a sharing
member does not transact (C33), so nobody confirms a product type or an address on their behalf, and
`harvest.md` deliberately lets that item stay in the zone and be swapped for after it harvests. That
is consistent with what is written here rather than in tension with it: the rule is that
**confirmation ends swapping**, and for a member-owned plant confirmation follows its own harvest,
which is why `harvest.md` says there is no swapping after harvest *for paying members*. For
sharing-member stock the swap comes first and the confirmation follows it — the member who swaps in
locks in, becomes the owner, and confirms product type and address as any other owner does.

**So C16 stays open and keeps its exact shape.** A member can still come to hold a harvested plant,
by swapping for one. Whether that plant counts toward the four flowering while it waits in
processing is still the holding check's question, and C8 does not answer it.

**What this does not decide: the member who never confirms.** The gap between harvest and delivery
is the longest silence in the journey, and no document says what happens when the notification goes
unanswered. Reminders and then a default to the no-cost product type, reminders and then escalation
to a club administrator, and an indefinite hold are three different products, and the plant is
physically somewhere the whole time. Nothing ships without an address, so this is not a data
question — it is a storage and liability question for the cultivator. Recorded as open, deliberately
not decided here, and it should be answered before Block 6 is specified rather than during it.

**One favourable coincidence, to be checked rather than assumed.** Pargo is a pickup-point network,
so a delivery may resolve to a collection point rather than a residential address. If that is how it
is integrated, C19's pseudonymity problem shrinks considerably — the fulfilment document carries a
pickup point and a waybill, not a member's home. Worth confirming against the actual Pargo
integration before C19 is decided on it.

### C9 — When the grow price is paid, and what happens when a crop fails

**Status: Decided — the member pays in full at order. The club holds the money until delivery is
confirmed and then releases it to the cultivator. A failed crop is substituted; it is refunded only
where no equivalent plant exists. One thing stays open: which event counts as delivery confirmed.**

`member-plant-purchase.md` has the member add plants to a cart and the system allocate serials. It
does not say when money moves. The plant is then grown for months before the member receives
anything.

Three readings were consistent with the brief — payment in full at order; a deposit at order with
the balance at harvest; payment at harvest with the order as a commitment. Each implied a different
position when a plant dies, and **no document in `twp-tasks/` says what happens when a crop fails.**
A member has paid for a specific serialised plant that no longer exists. Substitution, refund and
credit are three different products.

**Decision: payment in full at order.** The two alternatives are rejected on the same ground —
either one turns the platform into a lender. A deposit leaves a balance outstanding across a
months-long grow, and payment at harvest leaves the whole price outstanding; both need a receivables
ledger, a dunning path, and an answer to the member who simply does not pay when the plant is ready
and is already the legal owner of it. None of that exists and none of it is worth building for a
first release.

#### The guarantee is what makes payment at order fair, and the hold is what makes the guarantee real

The product owner's position, which the register did not have when this was written as open:

- **The cultivator guarantees delivery.** The member is not buying a chance at a plant; they are
  buying a delivered outcome, and the cultivator carries the growing risk.
- **The club holds the money.** Funds are held back after the member pays and are released to the
  cultivator once delivery is confirmed.

Those two together change the shape of the decision. Payment in full at order, on its own, asks a
member to carry a months-long risk on a living thing they cannot see. Payment in full at order
against a guarantee, with the money held until the guarantee is discharged, moves that risk to the
party who can actually manage it — the cultivator does not hold the member's money while growing the
member's plant, and the member's remedy for non-delivery is money that has not left yet rather than
a claim against a farm.

**This is a change to when a cultivator earns, not merely to where cash sits.** It is recorded here
and carried into C10.

#### Crop failure: substitution first, refund where there is no substitute

The rule:

1. **Substitute.** The cultivator offers an equivalent plant — same strain, a leaf rating no lower,
   the next available harvest date. The member's ownership moves to the substitute serial and the
   held funds follow it. **No money moves at all**, which is the reason this is the default: the
   common failure case never touches a refund path.
2. **Refund** where no equivalent plant exists, or where the member refuses the substitute offered.
   The money has not been released, so this is a return of funds still held rather than a clawback
   from a cultivator who has already been paid.
3. **Credit is not offered.** Holding a member's money against a future grow they have not chosen is
   the weakest of the three positions under the CPA, and it was not asked for.

**The cultivator carries crop failure.** That follows from the guarantee and from the hold, and it
answers one of C10's open questions for this case: nothing is recovered from a cultivator, because
nothing was paid to one.

**A substitute is assumed to come from the same cultivator.** A cross-cultivator substitution would
change who the held funds release to, which is a settlement question and not a fulfilment one. Not
decided here; it belongs with C10.

**What has still to be specified is the offer itself**, and that is a Block 5 and Block 6 item rather
than a decision: how a substitution is offered, how long the member has to answer, and what happens
in the silence. That silence is the same one C8 left open at the harvest notification, and the two
should be answered together with one rule about an unanswered member rather than two.

#### Open — C9.1: what event confirms delivery

The release trigger cannot be fixed until the Pargo integration is understood, so it is recorded as
open rather than assumed.

**The preference is the courier event** — Pargo's confirmed delivery or collection scan releases the
funds. It is objective, it needs no member action, and it does not add money to the longest silence
in the journey. Whether Pargo exposes such an event to the platform is exactly what is not yet
known.

The two fallbacks, in order:

- **Member confirms receipt.** Cleanest evidence of satisfaction, worst behaviour under silence — a
  member who never presses the button strands a cultivator's payment indefinitely, which is the C8
  failure mode with money attached.
- **Courier event where available, automatic release after a fixed window otherwise**, unless the
  member has raised a dispute inside that window. Needs the dispute path, which is C11.

Whichever is chosen, the platform has to hold one fact per order: whether the money is held or
released, and on what event. That is a ledger state, and it is a prerequisite of C10's statement of
account.

#### Where the money is actually held is outside the application

The product owner's position: the escrow arrangement itself — the account, the banking or trust
mechanism, and whose balance sheet it sits on — is a commercial and financial matter and is **not in
scope for the application**. This register records that as a stated boundary rather than as an
oversight.

What remains in scope is narrow, and is not optional:

- The order carries a **held or released** state, with the event and the timestamp that changed it.
- A cultivator's statement of account (C10) **must not present held funds as earnings**. Held,
  releasable and paid are three different lines, and a statement that shows them as one will be
  wrong for months at a time on every order in flight.
- Reconciliation between the platform's ledger and whatever account actually holds the cash is a
  finance process the application reports into and does not perform.

#### What has to be said to a member, and where

The hold and the guarantee are the strongest things this product can say to a member who is being
asked for the full price of something that does not exist yet, and neither of them is said anywhere
today. They belong in the **introductory copy and in the sign-up journey**, in plain terms: pay in
full when you order, the cultivator guarantees delivery, the club holds your money until the plant
is delivered, and if the crop fails you get an equivalent plant or your money back.

Two constraints on that, both already documented:

- **Landing-page copy is governed** — `features/landing.md` section 4 and the four compliance
  patterns. A payment and guarantee statement is a commercial term rather than a cannabis claim, so
  it is not the kind of copy those patterns exist to catch, but it goes through the same review, and
  C20 is the open item on that page.
- **A guarantee is a term of sale, not marketing.** If it is stated to members it belongs in the club
  documents agreed at sign-up — `features/sign-up.md` section 5, which already versions those
  documents and records what a member agreed to. Saying it only in a hero paragraph creates a promise
  with no versioned record of what was accepted.

**Not yet propagated.** This entry is the decision; `plan.md`, `todo.md`, `backend.md` and the feature
documents still describe C9 as open and still carry no copy for the guarantee. That edit is
deliberately deferred, not forgotten.

#### What this does not decide

- **C35 is untouched, but inherits the question.** A priced finished product type is a second
  payment, taken at harvest for something delivered later, so the same hold-until-delivery logic
  arguably applies to it. Decide that when C35 is specified rather than by silence now.
- **The membership subscription is unaffected.** That is a Payfast recurring payment for club
  membership, it is earned by the club itself, and it has nothing to do with this hold.
- **Nothing here settles partial refunds with fees withheld.** That is C11, and it is a different
  case: this rule returns funds on an order that was never delivered and whose money was never
  released.

### C10 — Cultivator settlement is entirely unspecified

**Status: Substantially answered by the product owner, and narrowed rather than closed. Two
collection accounts, two gateways, a 15% commission on member transactions and a 40/60 split on the
membership fee. What is left is smaller than what has been answered, and one part of it is a build
item rather than a question.**

The drawio cultivator story asks for "My Farm — users, collection address, sharing members, **bank
details**" and a "**Statement of Account, payment due**". The club administrator story asks for
"Statement of Account, payments due, **record payments made**".

No document in `twp-tasks/` describes this, and nothing is built. It is a complete commercial
domain: the platform takes a member's money for a grow service performed by a third party and has to
remit it.

#### The money map

The product owner's statement of the flows, which the register did not have. It corrects the sentence
immediately above: on everything except the membership fee, **the money never reaches the platform at
all**.

| What is paid | Collected by | Through | Split |
| --- | --- | --- | --- |
| The recurring membership fee | **F2C** | Payfast | 40% F2C, 60% Cultivators Collective |
| Everything else a member buys on the platform | **Cultivators Collective** | PayGate or Stitch | 15% platform commission to F2C |

Three things follow before any of the questions below are touched.

**The two obligations run in opposite directions.** On the membership fee F2C collects and owes the
club 60%. On a plant order the club collects and owes F2C 15%. Neither is expressible in the system
as it stands, and they are not one mechanism with a sign flipped — one is a share of a subscription
the platform bills, the other is a commission on a sale the platform did not make.

**The seller of record, for the club, is the Cultivators Collective.** C26 escalated that as a VAT
question as much as a commercial one. The member's money goes to the club's account, so the club
sells and F2C is the agent taking a commission. Settled for the club; **not** settled for the market,
which is where the platform now trades first — the last section of this entry carries that.

**C9's hold is unaffected and is confirmed by this.** The member pays the club, the club holds until
delivery and releases to the cultivator. F2C never touches that money and takes its commission out
of the club's leg, so C9's ruling that the escrow mechanism itself is outside the application stands
exactly as written.

**The ratios themselves are out of scope for the application** — the product owner's ruling, and the
same boundary C9 drew around the escrow account. Nothing configures 40/60 or 15%, and no screen
computes a split. One consequence has to be taken with that, and it is under *what is still open*
below: a statement of account with no commission line cannot be reconciled, so the commission has to
reach the application as a recorded amount even though the rate does not.

What had to be decided before this could be specified, with what is now answered struck through:

- ~~Does the platform collect and remit, or introduce and invoice a commission?~~ **Answered: both,
  and which one depends on the transaction.** It collects and remits the membership fee; it invoices
  a commission on everything else. See the money map above.
- ~~What is the platform's take, and is it visible to the cultivator?~~ **Half answered: the take is
  15% of a member transaction, and 40% of the membership fee.** Whether a cultivator sees it is still
  open, and so is the base it is calculated on — both are under *what is still open* below.
- ~~When does a cultivator earn — at order, at harvest, at delivery?~~ **Answered by C9: at
  delivery.** The member pays in full at order and the club holds the funds until delivery is
  confirmed, so settlement is a hold-and-release across a months-long grow rather than a split at
  checkout. Two consequences land here rather than in C9. The statement of account has to carry
  **held**, **releasable** and **paid** as three separate lines — funds held against a plant still in
  the ground are not a cultivator's earnings and must never be shown as them. And the release event
  itself is still open (**C9.1**): the preference is Pargo's delivery or collection scan, and it
  cannot be fixed until the integration is understood.
- ~~Who carries a refund (C11) — the platform or the cultivator?~~ **Answered by C9 for the crop
  failure case: the cultivator.** A failed crop is substituted where an equivalent plant exists and
  refunded where it does not, and in both cases the money never left the hold — so nothing is
  recovered from a cultivator, because nothing was paid to one. The general case, a refund after
  release, is still C11's. One new question: a substitute is assumed to come from the same
  cultivator, and a **cross-cultivator substitution** changes who the held funds release to.
- ~~Payfast is a collection gateway. Payouts need something else, or a manual EFT run.~~
  **Confirmed by the product owner, and now split in two.** Collection into the club's account is a
  *second gateway* and is a build item — **C10.1** below. Paying a cultivator is still unsolved:
  Payfast does not disburse, and PayGate and Stitch are being considered for collection rather than
  payout. A manual EFT run remains the working assumption, which changes what the application owes —
  see *what is still open*.
- **Where the funds are held is out of scope for the application.** The product owner has ruled
  that the escrow account and its banking or trust mechanism are a commercial matter — see C9. The
  application's obligation is to know the held-or-released state per order and to report it; it does
  not hold or move the cash, and reconciliation to the actual account is a finance process.
- **The courier component.** C8 puts delivery inside the price the member pays and remits it
  to Pargo at settlement, so a cultivator is paid the listed price less commission *and* less
  courier. Who sets that component, whether it is visible to the cultivator, and who carries
  the difference when the actual Pargo charge exceeds it, are all unanswered — and the commission
  now makes the ordering of the two legs a live number rather than a presentational detail.

#### One correction to C9

C9 closed by saying the membership subscription was unaffected because it "is earned by the club
itself". That is wrong as written. The subscription is collected by **F2C**, and 60% of it is owed
onward to the club. Nothing about the built Payfast integration changes — it collects into whichever
merchant account it is configured with — but that account is F2C's, and the 40/60 is a settlement
obligation running the opposite way from every other flow in this entry. Recorded here rather than by
quietly editing C9, because that reading is the one most likely to be assumed again.

#### C10.1 — the second gateway, which is a build item and not a question

**Status: Open, and it is work rather than a decision waiting on a decision.**

Payfast is built and is the only money path in the system: `app/core/payments` carries the hosted
checkout, the signed server-to-server notification, the subscription and the payment record, and it
bills exactly one thing — the membership fee. The money map needs a second path, into a **different
legal entity's** bank account, and none of it exists.

- **Two merchant accounts, two credential sets, two notification endpoints.** `payfast_config` is a
  single-gateway assumption with one merchant identity in it. Member goods transactions do not settle
  through it and never will, so the payment layer stops being "the Payfast integration" and becomes a
  gateway per money flow.
- **"PayGate or Stitch" is two candidates, not a choice.** They are not interchangeable. PayGate is a
  hosted card gateway of much the same shape as Payfast; Stitch is API-first and leads with
  pay-by-bank. Which one is chosen decides the shape of the checkout, how much of the ledger the
  platform has to hold itself, and — this is the one that reaches another conflict — **whether a
  reversal is available at all**, which is what C11 turns on.
- **The order has to record which gateway took the money and into which account**, because two
  entities' bank reconciliations will be read off the same table.
- **Sequencing.** It belongs in Block A with the payment intent, ahead of both storefronts' checkouts.
  Deciding it during the block means writing the checkout twice.

Not scoped. No integration document for either candidate has been read, and no estimate here would
be worth anything.

#### What is still open

- **The base the 15% is taken on.** C8 puts the courier fee inside the price the member pays and
  remits it to Pargo at settlement. So a member's R1,000 covers grow, commission and courier, and
  nobody has said whether the commission is 15% of the R1,000 or 15% of the R1,000 less the courier
  component. On a R120 delivery that is about R18 a plant, moving in the platform's favour or the
  cultivator's. The same ambiguity sits over VAT — 15% of a VAT-inclusive price and 15% of the
  exclusive price are different amounts, and the commission rate and the VAT rate being the same
  number will produce at least one arithmetic error if the documents stay this loose.
- **Whether the commission is visible to the cultivator.** Recommendation: yes, and as an amount
  rather than a rate. A statement showing gross, commission, courier and net is the only kind that
  can be reconciled or argued with; one showing a net figure turns every query into a phone call.
  That appears to collide with "the ratios are out of scope", and the resolution is cheap: record the
  commission **as an amount on the transaction at the time it is taken** — a fact, not a policy. No
  rate table, no configuration screen, no split engine, and the statement still adds up.
- **The payout mechanism, which is the largest remaining gap.** Collection is now answered twice
  over; disbursement is answered nowhere. If the realistic first release is a manual EFT run, the
  application's obligation is to produce the **payment run** — a payable list per cultivator per
  period, with the released orders behind each line — and to record a payment made against it. That
  is exactly `drawio`'s "record payments made", it needs no payout API, and Block 0.5 already put
  encrypted bank details on `Producer` for it to read.
- **Cross-cultivator substitution**, carried from C9: a substitute from a different cultivator
  changes who the held funds release to.
- **The market's leg is not answered at all.** The money map is written in club terms — "members",
  the Cultivators Collective's account. A farmer selling honey is not a member of a cannabis club and
  the Collective is not an obvious party to that sale. Whether market money also lands in the
  Collective's account, whether F2C's 15% applies there, and who is the seller of record for produce
  that is mostly zero-rated, are all unstated. Since the market is sequenced first, this is now the
  more urgent half of the entry.

**Recommendation.** Narrower than it was: one session with the finance owner covering the commission
base, the visibility of the commission on a statement, and the payout run — all three answerable in
an hour — and a separate decision from whoever owns the Collective's banking on PayGate versus Stitch,
which is C10.1 and gates Block A. It remains a launch blocker for cultivators even though no
member-facing screen depends on it.

**Escalated by C26, and only half of that escalation is now discharged.** This was a Block 12 concern
because the club can demonstrate everything else without it. The market cannot: it pays a farmer on
every order from the first day it trades. With the market sequenced ahead of the club's own commerce,
settlement is on the critical path. The seller-of-record question C26 added is answered **for the
club** — the Collective sells, F2C is the agent — and is untouched for the market, where the VAT
treatment differs line by line and the collecting entity has not been named.

### C11 — Refunds are required and are not built

**Status: Open. Who refunds is now answered; how, and at whose cost, is not.**

`member-roles.md` gives the administrator the power to "reverse/refund transactions or part of
transaction (transaction/platform fees can be withheld)", and `platform.refund_transaction` is in
the catalogue. `features/payments.md` section 9 states plainly: **no refunds, no proration, no plan
changes.**

Partial refunds with fee withholding are not a button on a gateway. They need a transaction ledger
that can express a partial reversal, and they interact with C10 — refunding a plant order takes
money back from a cultivator who may already have been paid.

**Narrowed by C9, not closed.** The commonest refund the platform expects — a crop that failed — is
now mostly not a refund at all: an equivalent plant is substituted and the held funds follow it. Where
there is no equivalent, the return is of money the club still holds, before commission or courier
have been separated out, which needs no partial reversal and takes nothing back from a cultivator.
What is left for C11 is the harder half: a refund **after** the funds have been released on delivery,
and the administrator's power to reverse part of a transaction with fees withheld. C9.1's third
option also lands here — automatic release after a fixed window requires a member-raised dispute to
suspend it, and no dispute path exists.

#### Who refunds, from the product owner

**The Cultivators Collective refunds the member, and F2C's 15% commission is not refundable.** That
follows from C10's money map rather than being a separate ruling: the club took the member's money and
is the seller of record, so the club is the party that gives it back. How the club then absorbs a
refund on which it has already paid away a commission is, in the product owner's words, the club's
problem at this stage.

**The application cannot be neutral about that, because the two readings are different ledger rows.**
Either the member is refunded in full and the club carries the commission it has already paid, or the
member is refunded net of the commission. The first is the only thing a consumer-facing refund can
reasonably mean under the CPA; the second is a deduction the member never agreed to and would be
argued about the first time it happened. **Recommendation: build the full-refund case**, record the
commission as retained on the transaction, and leave the club's recovery of it — if any — outside the
application as a finance matter. That keeps a commercial argument out of the schema without pretending
the money is not gone.

#### How, which is still open and is downstream of C10.1

Two routes, and which is available is not yet known:

- **A gateway reversal.** PayGate may support one — the product owner's expectation, unconfirmed —
  and Stitch's position is different again. This is precisely why the gateway choice (**C10.1**) has
  to be made before refunds are specified: a gateway that reverses makes this a transaction status,
  and one that does not makes it a ledger.
- **A credit on the member's platform account**, which is the product owner's fallback where a
  reversal is not possible. **Recorded as an option, not as a requirement.** An account credit is a
  real ledger and a real liability: a balance per member, spendable at checkout, with a position on
  expiry, a POPIA-relevant record that has to survive or not survive erasure, and a number that sits
  on somebody's books. It is a larger build than a reversal, and it should not be adopted as a
  fallback by default. Note also that C9 ruled credit *out* as the crop-failure remedy on CPA
  grounds; a credit offered because the gateway cannot reverse is a different case, but the question
  of whether the member consents to it is the same one.

**Recommendation.** Specify refunds together with settlement, not before — and specifically after
C10.1, because the gateway decides which of the two routes above is even on the table.

### C12 — A cultivator cannot buy, and the drawio story says they browse

**Status: Substantially closed by C28. One question left, and it is about the brief rather than
about the build.**

`features/roles-and-permissions.md` section 5 recorded the decision that one account holds one role,
and its accepted cost: the Cultivator role did not hold `platform.purchase_plants`,
`platform.use_swap_zone` or `platform.offer_inventory_for_swap`.

**That cost is gone.** `permissions_for` reads three relationships rather than one column, and its
docstring strikes the limitation in as many words — *somebody who does both needs a second
account*, and *it is accepted no longer*. All three codenames sit in `MEMBER_ACTIONS`, granted by an
active `ClubMembership`, so a cultivator who takes out a club membership **on the same account**
holds them. Nothing needs widening and no permission set needs a new member.

The drawio cultivator story lists "View all plants available (**includes other cultivators' offers**)"
under The Plantation. Browsing is granted — cultivators hold `platform.browse_catalogue` — so the
story is satisfiable. But a grower shown a competitor's offers and unable to act on them is an odd
screen, and the story may intend more.

**Recommendation.** Confirm browsing is all the story meant, and close this. If cultivators should
also buy, that is answered too: they take out a club membership on the same account. What is left is
a commercial decision for the club — whether a grower may hold a membership at all — and not a
schema change, a catalogue change or a second account. **The old answer was "a second account, not a
widened role"; both halves of it are now obsolete.**

### C13 — Object-level rules do not exist, and half the brief needs them

**Status: The design question is answered by C28 — what remains is implementation, not a
decision.** Kept in this section because the object-level rules themselves are still unwritten
and `todo.md` still carries them, but **nobody has to decide anything here.** The paragraph
below is the record.

`RoleBackend` refuses object-level questions outright — `has_perm(perm, obj)` returns `False` rather
than answering from the role. That is correct, and it means these requirements have nothing to
enforce them:

| Requirement | Source | What it needs |
| --- | --- | --- |
| Only the **primary** cultivator appoints staff and registers sharing members | `member-roles.md` | A cultivator organisation with a primary flag |
| A cultivator manages **their own** listings, stock and pricing | `member-roles.md` | Ownership on every one of those models. **The stock half is written** — `plant.stock._authorise` asks `platform.manage_plant_stock` and then asks `ProducerMembership` whether the caller is appointed to the farm named in the request. Listings and pricing follow the same shape |
| A cultivator manages **the sharing members they registered** | `member-roles.md` | `registered_by` exists; nothing checks it |
| A member views **their own** inventory | `member-roles.md` | Ownership on the plant |
| Club administrator versus UC administrator reach | C2 | ~~Tier comparison at every administrative endpoint~~ — **struck by C29.** The UC tier is is_staff in the Django admin, so no endpoint compares tiers |

**Largely resolved by C28.** The role column was what left these with nothing to enforce them: "their
own" pointed at nothing, so `RoleBackend` refused every object-level question rather than answer one
wrongly. `cultivators.ProducerMembership` is now a row per person per producer, and the first rule
above — only the primary appoints staff and creates sharing-member placeholders — is enforced in
`permissions_for` off `ProducerMembership.is_primary`. The rest are joins against the same rows, to
be written in the services that own each record rather than in the catalogue. What stays open here
is that work, not the design question.

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

**Sharpened by C8, not closed by it.** C8 ends swapping at the owner's harvest confirmation, and
`harvest.md`'s "no swapping after harvest" is now understood as a statement about *paying members* —
whose plants harvest into a confirmation. Sharing-member stock has no confirming owner, so it does
sit in the zone after harvest, exactly as `harvest.md` says, and a member who swaps for it becomes
the owner and confirms in the ordinary way. That leaves this entry's question untouched and gives it
two live cases rather than one: a member's own plant awaiting processing, and a harvested plant
swapped in. The recommendation is unchanged — the Act's limit is on flowering plants, and neither of
those is flowering.

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

**The window now has an end.** C8 locks a plant to its owner at the harvest confirmation, so the
most mature thing in the zone is one that has not yet been harvested. That caps the maturity
spread the leaf rating fails to price. It does not remove it — a plant a week from harvest and
a seedling of the same grow price still carry the same rating.

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

It is built: `frontend/club/app/(club)/profile/page.tsx`, `app/core/accounts/profile.py`,
`app/core/accounts/avatars.py`, and four endpoints — `GET`/`PUT /api/accounts/me/profile`,
`POST`/`DELETE /api/accounts/me/avatar`. `club-navigation.ts` already marks `own-profile` as the one
`ready` destination.

**Action:** correct `frontend.md` section 9 and `roles-and-permissions.md` section 13.

**Note, later:** the codename quoted above no longer exists. `platform.manage_own_profile` was
retired when the produce market arrived — a store customer holds none of the three granting
relationships and was refused their own name and photograph — and the screen is now offered on the
session alone. `roles-and-permissions.md` section 6.7 records it. Nothing about this conflict
changes; the quotation is kept as written so the drift it describes stays legible.

### C22 — `todo.md` said sign-up stores nothing

The old `todo.md` carried "Create signup/registration process — form built, nothing is stored yet".
`membership.services.register_member` writes the member, `POST /api/members/register` is live, and
`features/sign-up.md` risk 11 is marked closed. Corrected in the rewritten `todo.md`.

### C23a — A third of the frontend was not under version control after all

**Status: Closed.** Cause fixed, and the 133 files landed in `d3731df`; the tree is clean and
`git ls-files frontend/club/lib frontend/market/lib` counts all of them.

C23 below closed `backend.md` risk 12 on the grounds that the project is in git. It is — but
`.gitignore` carried a bare `lib/` from GitHub's Python template, which matches a directory of that
name **at any depth**, not just beside `setup.py`. This repository has two such directories:
`frontend/club/lib` (94 modules) and `frontend/market/lib` (39). All 133 were silently untracked —
`lib/api.ts`, `lib/site.ts`, the sign-in rules, the SA ID number validator, the nickname rules, the
copy-compliance patterns, and every accompanying test.

**What makes this worth its own entry is that nothing anywhere reports it.** `git status` shows a
clean tree. `git add frontend/club/lib` succeeds and adds nothing. `git check-ignore -v` is the only
thing that says so, and nobody runs it unless they already suspect. The files exist on the machine
that wrote them and in no commit, so the loss is invisible until a fresh clone, at which point both
applications fail to build.

Found while checking that the P6 work could be committed. The packaging patterns are now anchored
with a leading `/`, which is what they always meant — `build/` and `dist/` included, both being
ordinary names in a JavaScript workspace. **The 133 files still have to be added**, and that belongs
in a commit of its own rather than buried in a feature branch.

### C23 — `backend.md` risk 12 says the project is not under version control

It is. The repository exists, `.gitignore` covers the Python artefacts, and the work is committed on
`master`.

**Action:** close risk 12 in `backend.md`.

### C24 — 125 source comments cite documents that do not exist

Recorded in `design/README.md` with a mapping table, deliberately not fixed. Repeated here so it is
counted among the known drift rather than rediscovered.

**Action:** none. The mapping table is the fix.

### C25 — A test fails roughly one run in thirty

`frontend/club/app/api/nickname/availability/route.test.ts` asserts an eight-character random hex
reference does not contain `"500"`, `"503"`, `"429"` or `"422"`. All four are valid hex. Known,
one-line fix, not yet taken — `frontend.md` risk 6. Carried into `todo.md` Block 0 so it stops being
a note.

---

## D. Production blockers already recorded, restated so they are counted

Not conflicts. They are in `todo.md` Block 0 because nothing in the brief can be demonstrated to
anybody without them.

| # | Blocker | Recorded in |
| --- | --- | --- |
| P1 | ~~No email provider. Sign-in codes and payment links print to a console~~ — **stated wrongly, and now mostly done.** The console backend only survives under `DEBUG`; `_mailer` refuses a deployed environment naming no host, so this was provisioning, not code. A cPanel provider is configured for both storefronts, the transport corrected from 465-with-STARTTLS to 587, and the two missing `EMAIL_*_FROM` senders added — without which the club sent as the market's domain. **Left:** the market mailbox does not authenticate, and QA and production carry none of the values | `authentication.md` risk 2, `backend.md` risk 3 |
| P2 | Nothing schedules `lapse_memberships`. An unpaid membership keeps access indefinitely | `payments.md` risk 2 |
| P3 | `LocMemCache` makes every rate limit per worker | `backend.md` risk 2, `authentication.md` risk 1 |
| P4 | No documented backup or rotation for `DJANGO_FIELD_ENCRYPTION_KEY`. Losing it destroys every stored identity number | `backend.md` risk 1 |
| P5 | ~~Staff password sign-in at `POST /api/auth/login` is not restricted to staff~~ — **closed by deleting the endpoint.** Nothing called it, members hold an unusable password hash so it could never have signed one in, and staff use `/admin/login/`. Restricting it would have documented the risk; removing it ends it | `authentication.md` risk 5 |
| P6 | ~~`NEXT_PUBLIC_DJANGO_API_URL` is baked in at build time, so one artefact cannot serve two environments~~ **Closed** — now `DJANGO_API_PUBLIC_URL`, read per request | `frontend.md` risk 2 |
| P7 | **A member suspended for conduct could pay the membership fee and be restored to Active automatically**, going around `reinstate_member`. `MembershipStatus.SUSPENDED` sat in `ACTIVATABLE_STATUSES` and in the frontend's `PAYABLE`, justified by a comment calling it the landing state for a subscription that stopped paying — which is `LAPSED`. **Closed:** out of both sets, with tests on both sides; a suspended member is now refused a checkout with a 409 and sent to `/blocked`. Found while implementing C32 | this register, and `payments.md` |
| P8 | **`GET /api/payments/me/checkout` answered 500 for the member it was written for.** It called `open_subscription` unconditionally, and registration has already opened one, so the `live_for_user` partial index refused the second — the pay-now redirect from the club layout was a 500 for anybody at `Pending payment`. The endpoint had no tests at all; its docstring always claimed it found the live subscription first. **Closed:** it does now, with `MyCheckoutEndpointTests` behind it. Found while writing the P7 tests | this register |
---

## D2. Decided while closing Block 0

### C32 — Where a block lives, and how a blocked member is told

**Status: Decided — two levels, kept separate; the member is emailed, not shown a reason.**

Asked because the two `suspended` values looked like one fact recorded twice. They are not, and the
distinction is load-bearing:

| Level | Written by | Means |
| --- | --- | --- |
| `ClubMembership.status = SUSPENDED` | `membership.administration.suspend_member` | The club has suspended a **membership**. Conduct. The account still signs in, and still uses the produce market. |
| `ClubMembership.status = LAPSED` | `payments.lapse_overdue` | Did not pay. Money lifts it. |
| `User.status = SUSPENDED` | `platform.revoke_access`, in the Django admin | Off the **platform**, both storefronts. |

**Merging the account and membership levels was considered and refused.** It would mean a club
conduct suspension locking somebody out of the produce market — which is precisely what Block 0.5
separated, and `administration.suspend_member` carries the note saying so. What was genuinely
muddled was inside `MembershipStatus.SUSPENDED`, and that is **P7**.

**A blocked member is told by email, and the screen does not say why.** Two halves:

- *The sign-in endpoints stay vague.* `_find_user` filters to Active, so a revoked account is
  answered exactly as a stranger is — *"if that address belongs to a member, a code is on its
  way"*. Saying more would confirm to anybody typing addresses that one belongs to a member of a
  cannabis club, which is the disclosure the whole authentication design exists to prevent.
- *The explanation goes to the mailbox*, which only its owner reads — the same reasoning
  `accounts.registration` already uses for a duplicate registration. `accounts.notifications`
  carries both messages.

A club suspension leaves the member able to sign in, so they also reach a screen: `/blocked` names
their standing, offers the support address, and **states no reason**. A reason recorded by an
administrator is not something to render into a page a shared device or a forwarded screenshot can
carry, and the email is the private channel.

**What it cost.** A new required frontend variable, `SUPPORT_EMAIL` — a screen that says "contact
support" with no address on it is the dead end it was written to replace. And none of the mail has
been seen in a real mailbox yet: **P1** has since configured a provider and the club mailbox
authenticates, so this is now testable rather than blocked — it has simply not been done.

---

## E. The second storefront

Added after the pass above, when the product owner confirmed that the produce categories C3 excluded
are a single public market rather than six future sites. The reasoning, the target model and the
sequencing are in [`verticals.md`](verticals.md); what is recorded here is the disagreement with
what is built.

### C26 — The platform serves two storefronts, not one club

**Status: Decided — one platform, two storefronts, one shared commerce spine.**

Every document in this set, and every model in `app/`, assumes the platform is the club. A second
storefront is now in scope: a public produce market where farming organisations list what they grow
— vegetables, fruit, biltong, nuts, dried goods, honey — and anybody with an account buys it by
quantity, searching on price, availability and the farmer's rating. No membership, no age gate, no
subscription.

**Decision.** One Django project, one database, one API, two Next.js applications on two domains.
The two storefronts share identity, the producer organisation, listings, search, cart, order,
payment, settlement, reviews, notifications and support. They do not share what is sold: the club's
plant, batch, serial, ownership, swap and harvest against the market's units, stock, perishability
and delivery.

The line between them is what is sold, not who the customer is. The club sells a serialised,
individually-owned asset with a service attached; the market sells fungible stock by quantity.

What this changes is in `verticals.md` sections 6 to 10. In summary: the app layout splits into
`core`, `commerce`, `club` and `market`; `CultivatorProfile` becomes a general `Producer`; the block
sequence in `plan.md` is rebuilt around a shared spine; and C27 and C28 below become blocking.

**What was rejected.** A tenancy column on every row, which the six-site reading of C3 would have
required. With two storefronts and one shared producer population it would be a fiction maintained
by hand — which storefront a listing appears in is already implied by what it lists. Also rejected:
a generic `Product` model unifying strains and produce. The abstraction that earns its place is the
listing, not the item listed.

### C27 — `User` conflates identity with club membership

**Status: Decided — split it, before either storefront is built.**

`User.status` carries `PENDING_PAYMENT`, and `is_active` is derived from `status` and held to it by
the `user_is_active_matches_status` check constraint (`app/core/accounts/models.py:481`). Exactly one
status value grants access and reaching it means paying for a club membership. **A produce customer
therefore cannot sign in.** The RSA identity number sits on `User` for the same reason, so a person
buying carrots would be asked for one — which POPIA's minimisation principle refuses.

**Decision.** `User` keeps identity and account state — active, suspended, erased. A new
`ClubMembership` takes member status, the subscription, the nickname, the document consents and the
verification flags. A new `ProducerMembership` takes appointed staff and their rights.
`id_number_encrypted` and `id_number_hash` stay on `User` and become optional: identity verification
is plausibly platform-level, since paying a farmer out asks the same question the club asks. What
moves is the requirement, not the column.

The build anticipated this. The `UserStatus` docstring at `app/core/accounts/models.py:70` says
`PENDING_PAYMENT` is a status value rather than a membership row *"on purpose, for now"*, and names
the payment gateway as the event that would change it. The second storefront is that event arriving
early.

**There is no data migration.** The product owner has confirmed the development database can be
dropped, every `migrations/` folder cleared and the schema rebuilt from the new models. No
`ClubMembership` backfill, no check constraint to lift and replace, no encrypted columns to move.

What it costs instead is **test support data**: the five `app/*/tests/support.py` builders and the
two modules under `frontend/club/test-support/` are written against today's `User` and have to be
rewritten. Cost the block by the test suite, not by the models.

**The window closes.** The same change against a club with real members is a data migration over
encrypted identity numbers, live subscriptions and consent records that cannot be re-run. Taking it
now is free; taking it after launch is not.

### C28 — One role per account cannot express one person's three relationships

**Status: Decided — retire the column, keep the catalogue.**

`User.role` (`app/core/accounts/models.py:362`) is a single value under a check constraint, and C2 adds a
fifth value to it. On the market one person may be a customer, a farming organisation's appointed
staff member and a club member at once. A column cannot hold that.

**Decision.** The action catalogue in `app/core/accounts/roles.py` and the resolving backend in
`app/core/accounts/backends.py` survive unchanged in shape. What changes is where a role is read from: an
administrator role from `StorefrontStaff`, a member role from `ClubMembership`, a producer role from
`ProducerMembership`. No role stays on `User` — the UC tier is `is_staff`, per C29.

A club administrator is `StorefrontStaff`, not `ClubMembership`. Today an administrator is
`role='admin'` on a `User` whose status must be `ACTIVE`; under the split that would have meant
issuing them a club membership they never pay for. Administration and membership are different
relationships and get different tables, and the market's administrator is the same table with a
different storefront.

**This is most of the answer to C13.** Object-level rules were a retrofit because "their own" had
nothing to point at. Once a membership row exists, "their own listings" is a join rather than a
special case, and `RoleBackend` refusing object-level questions stops being a gap.

**What it costs.** `roles.py`, `backends.py` and their suites are among the better-tested parts of
the build and all of them assume a column. Every permission test is touched. Accepted: those tests
are the reason the change is safe to make at all.

### C29 — The UC tier is `is_staff` in the Django admin, not a role in the catalogue

**Status: Decided — no UC administration in Next.js.**

C2 decided the platform has two administrative tiers and added `uc_admin` to the role column. C5
decided the administrative portal is Next.js "with the Django admin retained as the operator's
tool". Read together those two left an unanswered question: which tier gets which surface.

**Decision.** Next.js carries two administration areas, one per storefront — the club's and the
market's — and no third. Everything the UC tier does is done in the Django admin, gated by
`is_staff` exactly as Django gates it already: money, refunds, subscription cancellation,
administrator accounts, escalations, and any operation that reaches across both storefronts.

What this changes:

- **`uc_admin` never exists.** It was to be a fifth value in `User.role`; that column is being
  retired entirely under C28, and the UC tier does not reappear in `StorefrontStaff`.
- **The permission catalogue shrinks.** `platform.manage_administrators`,
  `platform.refund_transaction` and `platform.cancel_membership` are Django admin operations and
  need no catalogue entry, no endpoint and no tier comparison. C13's "tier comparison at every
  administrative endpoint" line is struck.
- **`createsuperuser` needs no role argument.** It creates a staff account, which is the whole of
  what the UC tier is.
- **The escalation queue survives** as a model, raised in the club or market administration area and
  worked in the Django admin. It is not a Next.js destination for the receiving side.

**Why this is the right trade.** A third administrative front end would be a month of work
reproducing what `django.contrib.admin` already does, on the one surface whose entire audience is a
handful of trusted staff. The Django admin over accounts, documents, subscriptions and payments is
already built and already tested.

**What it costs.** The UC tier gets no branded interface and no mobile-friendly one, and anything a
UC operator needs that the Django admin cannot express becomes a management command. Accepted.

### C30 — Which storefront gets which domain, and where the API answers

**Status: Decided — `f2c.co.za` is the market, `f2c-cannabis.co.za` is the club, and the API answers
on a subdomain of each.**

C3 read the two hosts as *public marketing site* and *member zone*: `f2c.co.za` would carry seven
category pages and `f2c-cannabis.co.za` would carry the club behind them. C26 then turned the six
excluded categories into a second storefront but left the host assignment as C3 wrote it. The
product owner has now fixed it, and it is not what C3 assumed.

| Host | Serves | Application |
| --- | --- | --- |
| `f2c.co.za` | The produce market — the store | `frontend/market` |
| `f2c-cannabis.co.za` | The club — landing page, age gate, member zone | `frontend/club` |
| `backend.f2c.co.za` | The API, for the market | Django |
| `backend.f2c-cannabis.co.za` | The API, for the club | Django |

**There is no separate marketing site.** The landing page, the age gate and the sign-up call to
action are built in the club application and stay there; the cannabis host is the club's front door
as well as its member zone. What C3 called the public site is the market, and it is a storefront
that transacts rather than a brochure that links to one.

**The two API hostnames are one deployment, and they exist for the session cookie.** One Django
project answers on both. A club frontend at `f2c-cannabis.co.za` calling `backend.f2c.co.za` is
cross-site — different registrable domains — so the session cookie would need `SameSite=None`, and
Safari's ITP and Chrome's third-party cookie posture would drop it anyway. Pairing each frontend
with an API host inside its own registrable domain keeps `SameSite=Lax` and the cookie posture at
`f2c/settings.py:107` exactly as they are. This is `verticals.md` section 8's "give each storefront
its own API hostname", made concrete.

**What follows from it, and all of it is configuration:**

- `DJANGO_STOREFRONT_HOSTS` maps the **API** hosts, not the frontend hosts:
  `backend.f2c.co.za=market,backend.f2c-cannabis.co.za=club`. `storefront_for_request` reads
  Django's host, and Django is never asked to render the frontend's.
- `DJANGO_WEBAUTHN_RP_IDS` is `club=f2c-cannabis.co.za,market=f2c.co.za` — the registrable domain
  each **frontend** is served from. A passkey enrolled at the club cannot be presented at the store,
  which is `verticals.md` section 8 and is accepted.
- `SESSION_COOKIE_DOMAIN` stays unset. One deployment serving two registrable domains cannot name a
  single cookie domain; host-only cookies per API host are what the pairing needs anyway.
- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` and `WEBAUTHN_ORIGINS` each carry
  both sides. The TLS certificate needs both API hosts, so a SAN certificate or two.

**What it closes.** `todo.md`'s "split `SITE_URL` into a public host and a member-zone host" is
already done and nobody noticed: Block 0.5 split the frontend into two applications, and
`frontend/club/lib/site.ts` and `frontend/market/lib/site.ts` each read their own `SITE_URL` from
their own deployment. Two applications, two hosts, two values. The same is true of the per-host
`robots` and canonical rules — each application computes both from its own `SITE_URL`, so they are
per host by construction. What is left of that block is deployment configuration, not code.

**What is deliberately left open.** Whether the apex or `www` is canonical on either domain, and
which way the redirect runs. It is a DNS and reverse-proxy decision with no consequence in the
codebase, provided whichever is canonical is the one in `SITE_URL`.

### C31 — The deployment target: three containers, managed MySQL, West Europe

**Status: Decided, with one thing reopened by the code — see the cache section below.**

**C1** left two things open: no production database, and no hosting target. Both are now fixed, and
the database half was already built before it was written down — `f2c/database.py`,
`app/common/checks.py`, `.env.example` and the CI job all target MySQL, while `plan.md` and
`todo.md` still said PostgreSQL. That drift is what this entry closes.

| | Decision |
| --- | --- |
| Database | **MySQL 8.4** on Azure Database for MySQL Flexible Server. Not PostgreSQL |
| Region | **West Europe**, all resources |
| Frontends | Two Azure Container Apps — `frontend/market`, `frontend/club` — Next.js standalone output |
| API | One Azure Container App — Django on uvicorn — answering on both `backend.*` hostnames |
| Scheduled work | An Azure Function App on a timer, calling the API |
| Registry, media, logs | Azure Container Registry Basic, Blob via `django-storages[azure]`, Log Analytics |

**`uuid7` did not need PostgreSQL.** C1 records the keys as "chosen anticipating PostgreSQL", which
made the database choice look load-bearing. It is not: `uuid.uuid7` is a Python 3.14 standard
library function and the column is a `char(32)` either way. Nothing in the schema depends on the
engine except the constraints `app/common/checks.py` already guards — which is why the MySQL work
could be done without revisiting the key strategy at all.

**Containers rather than Azure Static Web Apps, and the reason is in the frontends.** SWA was the
first proposal. It cannot serve these applications: both render on the server — 25 `page.tsx`,
twelve modules reading `next/headers`, three server actions, a `proxy.ts`, and two route handlers in
the club, with 25 `'use client'` components hydrating on top — so a static export is not on the table
and SWA's hybrid Next.js support is still in preview, capped at 250 MB, and documents its health
check against the `middleware.ts` convention that Next 16 renamed to `proxy.ts`. Containers also
settle `requires-python = ">=3.14"`, which App Service's built-in Python runtime and Azure
Functions' GA runtimes do not yet offer.

**Scale to zero is available and the API must not use it.** `payfast_addresses` resolves four
hostnames on every notification and Payfast expects a prompt 200; a cold start on top of DNS
resolution risks a dropped payment notification, and a dropped notification is a member who paid
and was not activated. `min-replicas 1` on the API is a correctness setting, not a performance one.
The frontends may scale to zero in QA and should not in production, because every page is
server-rendered and a cold start is a blank screen rather than a slow hydrate.

#### The shared cache: the database cannot serve it

This is the part that did not go as decided, and it is worth recording because the obvious answer
is wrong in a way that only shows up when it is tried.

Block 0 P3 needs a cache backend every process can see, because `LocMemCache` gives each worker its
own throttle counters. The cheap answer is Django's `DatabaseCache` on the MySQL that already
exists — no new service, no new cost. **It does not work here.** django-ninja calls
`_check_throttles` synchronously from inside `AsyncOperation._run_checks`
(`ninja/operation.py:537`), every endpoint in this project is async, and `DatabaseCache` reaches the
database through `connection.cursor()`, which Django decorates `@async_unsafe`. The first throttled
request raises `SynchronousOnlyOperation`. Trying it turns 82 tests across the auth, payments and
accounts suites into errors, which is how it was found.

There is no async throttle path in django-ninja to route around it. What distinguishes a
network-backed cache is not that it is faster: Redis and Memcached do blocking *socket* I/O rather
than ORM I/O, and socket I/O is not decorated `@async_unsafe`, so it is permitted from an async
context where the database is not.

So the async architecture — decided long before anyone thought about hosting — forces a cache
server. **Decided: Azure Managed Redis in QA and production, a `redis:7-alpine` container in
development.** Managed Redis rather than Azure Cache for Redis, whose Basic, Standard and Premium
tiers retire on 30 September 2028; roughly $25/month at the smallest SKU. The local container is in
`compose.yaml` and is not decoration — it is how the deployed backend gets exercised before QA,
because `LocMemCache` is correct in one process and wrong in any other, and that difference does not
show up as a failure anywhere.

`f2c/cache.py` carries it, in the shape `f2c/database.py` established: a pure function of a mapping,
`LocMemCache` when nothing is configured, and two refusals. A `qa` or `prod` environment with no
`DJANGO_REDIS_URL` does not start — the failure it would otherwise produce is a rate limit that
quietly does not hold. And `redis://` is refused where `rediss://` belongs, because the Azure access
key travels inside that URL, with `DJANGO_CACHE_ALLOW_PLAINTEXT` as the deliberate way out for CI
against a container on the runner's own loopback.

**Verified rather than reasoned.** The claim that a network cache is permitted where the database
one is not was tested against a real Redis over TCP: the 635 tests in `authn`, `payments` and
`accounts` — the same suites `DatabaseCache` turned into 82 errors — all pass, and the 13 throttle
tests return real 429s through Redis. Sessions stay in the database regardless; see below.

What was *not* chosen, and why it is worth recording: **accepting per-replica rate limits.** It
means the published limit is multiplied by the replica count, and the endpoint it matters most for
is `otp/start`, whose limit is the only thing stopping the API being used to mailbomb a member.

Whichever is chosen, **sessions stay in the database.** `SESSION_ENGINE` is deliberately unset, and
that is what lets the WebAuthn challenges parked in `authn/webauthn.py` survive a second request
landing on a different replica. Moving sessions into the cache would make sign-in depend on a
single-replica Redis with no persistence, which is a much worse trade than the one it looks like.

#### What has to be true in the deployment, and is not yet

- **`DJANGO_PAYFAST_BEHIND_PROXY=true`.** Container Apps ingress is a reverse proxy, so `REMOTE_ADDR`
  is Envoy and not Payfast. `gateway.py:375` defaults `behind_proxy` to `False` and
  `verify_notification` rejects on a source-address mismatch, so without this variable **every
  Payfast notification is rejected** and no membership ever activates. Highest-consequence single
  line in the deployment — and the worst-shaped failure in it, because nothing upstream of the
  notification fails: the member signs up, pays, and is returned to a thank-you page, because the
  return URL is a browser redirect and has nothing to do with the notification. It is a
  configuration value, so it cannot be closed in code — but it can be made impossible to ship
  without, and now is. Three things changed. It is **one variable**, `DJANGO_BEHIND_PROXY`: Django
  needs the same fact for `SECURE_PROXY_SSL_HEADER`, and two switches for one fact fail by having
  one of them set, so `payfast_config` falls back to it and `DJANGO_PAYFAST_BEHIND_PROXY` survives
  only as an override for an edge that terminates TLS without overwriting `X-Forwarded-For`.
  `payments.W001` reports it on `manage.py check --deploy`. And `deploy/entrypoint.sh` runs that
  check at `--fail-level WARNING` before uvicorn, so the revision fails to start and Container Apps
  keeps the previous one serving traffic rather than promoting a deployment that takes money and
  activates nobody. A notification rejected from a private source address also now says so in the
  log, rather than reporting the same "source address is not Payfast" a genuine attempt produces.

**A correction, because an earlier reading of this was wrong and it changed a conclusion.** These
applications were described here as having *no* client components, on a search that only covered
`app/`. Every client component lives in `components/`, and there are **25** — the sign-in form, the
passkey cards, the admin screens, the profile editor. The case against Static Web Apps is unchanged,
because it never rested on that: the server-rendered surface above is what a static export cannot
carry. What it changed is **Block 0 P6**, which has since been closed. `NEXT_PUBLIC_DJANGO_API_URL`
was genuinely inlined into the browser bundle — it appeared in two chunks under
`.next/static/chunks` in a real build — so it could not be fixed by dropping the prefix and
reading it server-side, because a client component has no `process.env` at runtime. It is now
`DJANGO_API_PUBLIC_URL`: the root layout reads it per request and renders it into the document as
a `<meta>` tag, and `lib/api.ts` reads it from there. **Verified by building once with a
deliberately wrong address and serving that one build under two others** — the build-time value
appears nowhere in `.next/static` or `.next/server`, and the two containers served two different
addresses from the same bundle. A deployment that omits the variable answers 500 on the first
request with the variable named, rather than defaulting to localhost as the old code did.

The cost is that both root layouts are now `force-dynamic`. It was measured rather than assumed:
every route that matters was already dynamic, because every page reads cookies. What became
dynamic is `/_not-found` in both applications and the club’s two static sign-up confirmations.
`SITE_URL` and `APP_ENV` are still evaluated during the build, so an image is still specific to
an environment — but the address a browser talks to is not one of them, and it was the one that
mattered: a wrong `SITE_URL` shows up in a canonical tag, a wrong API address breaks every
request after sign-in.

**Two things about the API entrypoint that are not obvious.** `manage.py check` needs a **reachable
database** on this backend — working out a `UUIDField`'s column type calls
`has_native_uuid_field`, which asks the server whether it is MariaDB, which connects — so the
entrypoint waits for the database before it gates, or a container starting seconds ahead of its
database would fail for a reason unrelated to its configuration. And uvicorn runs **without**
`--proxy-headers`: it would rewrite the client address from `X-Forwarded-For` before Django saw it,
which would make `notification_source_ip` correct with `DJANGO_BEHIND_PROXY` unset, make
`payments.W001` warn about a deployment that worked, and move the trust decision into a component
with no opinion on whether the edge overwrites the header. One place in this application interprets
`X-Forwarded-For`, it is opt-in, and it is tested.
- **`DJANGO_ENV=qa` or `prod`.** Closed in code by this pass, but worth recording as the same class
  of trap: `database_config` reads it before anything else and an unset value means `dev`, which
  returns SQLite regardless of how completely MySQL is configured beside it.
- **`DJANGO_DB_SSL_CA`.** Also closed in code by this pass. Flexible Server runs
  `require_secure_transport=ON` and mysqlclient defaults to `ssl_mode=PREFERRED`, so a connection
  with no TLS configuration comes up encrypted, unverified and indistinguishable in any log from one
  that checked the certificate. A deployed connection that names neither a CA bundle nor an explicit
  opt-out is now refused rather than defaulted.

#### POPIA

West Europe puts members' personal data — including the AES-encrypted identity numbers and their
blind indexes — outside South Africa. This is lawful under POPIA section 72(1)(a), the EU's GDPR
regime being one that provides substantially similar protection, but a transborder flow has to be
**disclosed in the privacy notice and the PAIA manual**. It is paperwork rather than architecture,
and it belongs on the Block 0 list rather than being discovered during an information officer's
first audit.

**What is deliberately left open.** The cache server, above. Whether MySQL runs on a burstable tier
(no zone-redundant HA, roughly $15–28/month) or General Purpose (HA available, roughly $131/month) —
West Europe has availability zones, so the upgrade path exists and the decision can wait for real
traffic. And whether Azure Front Door eventually fronts the three containers, which buys a WAF and
edge TLS termination that matters more from South Africa than it would from inside the region.

---

## F. Raised by the sharing-member reversal

C6 was reversed after it had been decided and acted on. The reversal answers the question C6 asked
and opens two it never had to.

### C33 — The cultivator acts as proxy for an owner who does not transact

**Status: Decided — the cultivator transacts, the sharing member views. Carries R-C7.1.**

C6 makes a sharing member a real person whose plants consume their own statutory allowance, and
gives them a read-only login so they can see what they own. C7 accepts the swap model. Between the
two sits the question neither answers: **who offers a sharing member's plant into the swap zone, and
who accepts a swap of it.**

The product owner names this as the grey area:

> The grey area which could be challenged is the sharing member offering plants that they didn't pay
> for essentially as proxy for the cultivator — but this role can be dropped at a later stage once
> the platform has momentum.

Three readings were available:

- **Cultivator proxy, owner views only.** The cultivator offers and swaps. The sharing member sees
  their plants and does nothing.
- **Mandate at registration, revocable.** The cultivator transacts under a written mandate the
  sharing member grants and may withdraw.
- **Owner approves each swap.** Every movement waits on a person who does not transact.

**Decision: cultivator proxy, owner views only.** It is what `member-roles.md` describes, it is the
only one that keeps the zone liquid, and the swap zone exists precisely to hold stock that moves. A
sharing member's login shows them their plants; it does not give them a swap action, a withdrawal
action or an approval queue.

**Two things follow, and both are build constraints rather than notes.**

**The role must stay droppable.** The product owner expects to retire it once the platform has
momentum. So nothing outside the sharing-member feature may assume a sharing member exists: the swap
zone matches on plants and their owners, not on owner *type*; the holding check counts plants per
member without asking which kind of member; the seeding of a new club's zone is a data question, not
a code path. If retiring the role means deleting a branch in the swap-zone matcher, the design was
wrong. Retiring it should mean registering no more of them, and eventually erasing the ones that
exist.

**The proxy has to be evidenced.** "Views only" is the weaker legal position of the three, and the
attestation is what carries it: the cultivator records that this person agreed to hold these plants
and to have them offered on their behalf. That is a widening of what the C6 attestation covers — it
was a POPIA consent for holding an identity number, and it now has to cover the mandate as well.
Two facts, one record, and the attestation version is what tells them apart when the wording changes.

**Revisit when the login is built.** A person who can sign in can withdraw a plant from the zone for
themselves, which converts this decision into the second reading at very little cost and removes most
of R-C7.1. That is the natural moment, and it is not brought forward.

### C34 — A sharing member who wants to be a member

**Status: Open. Small today, unpleasant later. Blocks nothing yet.**

C6 makes a sharing member a real person under the one-account-per-identity-document rule, and gives
their four flowering plants against their own statutory allowance. Neither the brief nor the build
says what happens when that person then wants to join the club properly.

Three collisions, in order of how soon they bite:

1. **Registration is refused and the refusal cannot explain itself.** Sign-up finds the identity
   number already on file and refuses in words that deliberately name no record — the leak control
   that risk 4 carries. The person is standing in front of a refusal caused by a record a cultivator
   created about them, possibly without their remembering it.
2. **Their allowance is already spent.** Four flowering plants are held in their name, so a new
   member may buy nothing until those plants harvest or move. The platform would be enforcing a
   statutory limit correctly and looking broken doing it.
3. **One account, two relationships.** This is C28 — one role per account cannot express one
   person's several relationships to the club — arriving from a new direction. A sharing member who
   becomes a member is not a status change if the sharing plants stay where they are.

**Recommendation.** Treat it as an upgrade of the existing account rather than a new one: the
`ClubMembership` moves from `SHARING` to the ordinary member lifecycle, the person consents for
themselves and supersedes the cultivator's attestation, and the plants held in their name stay theirs
and count against their four. That resolves 1 and 3 and makes 2 true rather than fixing it — which is
correct, if the limit means anything.

Worth deciding before sharing members are registered in numbers, and cheap while they are not.

---

## G. Raised by closing C8

### C35 — Priced finished product types need an order payment flow

**Status: Open. Blocks nothing in the MVP; blocks the second product release.**

C8 empties the harvest confirmation of money on the strength of one fact: loose flower and pre-rolls
cost nothing to manufacture. Oil, gummies and everything after them do, and the product owner intends
to introduce them. The moment one is listed, the confirmation screen stops being a confirmation and
becomes a checkout — at precisely the point in the journey C8 has just cleared.

What that needs, and none of it exists:

- **An order payment, not a subscription.** `features/payments.md` handles one recurring membership
  fee and nothing else. There are no order payments, no stored payment methods and no ledger a
  second charge against a single plant could be written to.
- **A way to charge months after the first transaction.** The member paid at order; this charge lands
  at harvest, possibly a season later. That is a stored mandate or a fresh checkout, and the two have
  very different POPIA and gateway consequences.
- **A price per product type, and somewhere for it to live.** C18 decides whether the catalogue, the
  strain listing or the plant owns the list of available types; whichever wins also has to carry the
  price and its history, because a plant bought under one price sheet may finalise under another.
- **A position when the member does not pay.** Hold the plant, downgrade it to a no-cost type, or
  cancel — three different products, and the plant is in physical storage while it is decided. This
  is the same silence C8 flagged for the member who never confirms, with money added to it.
- **A refund path.** C11 already has none. A manufacturing charge is the first thing a member could
  reasonably ask back after the product type is chosen but before it is made.
- **A fourth party at settlement.** Manufacturing is work somebody performs — the cultivator or a
  third-party processor — so C10's split of price, commission and courier gains a manufacturing leg.

**Recommendation.** Do not build it now. Do build the harvest finalisation so that adding it is not a
rebuild: model the finalisation as a transaction with a zero total rather than as a form that writes
two fields, and give the plant a finalisation record with a status the payment can later attach to.
The cost of doing that in Block 6 is small. The cost of not doing it is that the first priced product
type reopens ownership finality, the swap-window rule and the notification flow at the same time.

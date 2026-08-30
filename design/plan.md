# F2C Cannabis | Cultivators' Collective

## Development plan and product roadmap

This plan is written against two things: the brief in [`twp-tasks/`](twp-tasks/), which says what
the platform should do, and the design set in this folder, which says what exists today. Where those
two disagree, the disagreement is in [`conflict.md`](conflict.md) and is referenced here by number
rather than restated.

Detailed, statused work items are in [`todo.md`](todo.md). This document is the shape and the
sequencing; that one is the list.

> **A second storefront is now in scope, and it changes the sequencing below.** The produce
> categories C3 excluded are a public market, not six future sites. What the two storefronts share,
> what they do not, and the revised block order are in [`verticals.md`](verticals.md), recorded in
> the register as **C26**, **C27** and **C28**. Sections 4 and 5 of this document describe the
> club-only sequence and are superseded by section 4.1.

---

## 1. What the platform is

A membership cannabis club. Members pay a subscription to join, buy plants from cultivators with a
grow service attached, own those plants while a cultivator grows them, swap them with other members
before harvest, and take delivery of a finished product when the plant is harvested.

Three commercial mechanics carry it:

| Mechanic | Revenue | Status |
| --- | --- | --- |
| Membership subscription | Recurring, monthly, Payfast | **Built** |
| Plant purchase with grow service | Per order, split with the cultivator | Not built. Settlement unspecified — C10 |
| Plant subscription — a repeating monthly plant order | Recurring, per cultivator and strain | Not built |

A fourth mechanic is now in scope and is not costed here: a **public produce market** where farming
organisations list vegetables, fruit, biltong, nuts, dried goods and honey, and anybody with an
account buys by quantity. It takes a commission on each order, needs no membership, and carries none
of the club's regulatory load. See [`verticals.md`](verticals.md).

The swap zone earns nothing directly. It exists so a member who buys a seedling can get product
sooner, and so the four-flowering-plant statutory limit can be managed by trading down rather than
by refusing a purchase.

---

## 2. Where the work actually stands

Everything below the line marked *built* is in the repository with tests. Nothing above it exists.

**Built and reachable from a browser**

- Public landing page with compliance-governed copy, age gate, and search-indexing rules per environment.
- Sign-up: age gate, member details with RSA ID and mobile validation, club document agreements,
  registration stored, nickname availability check.
- Membership payment: Payfast checkout, signed notification handling, subscription and payment
  records, activation on payment, a `lapse_memberships` command.
- Authentication: passkeys and emailed six-digit codes, sessions, CSRF, rate limits, passkey
  enrolment and revocation.
- Roles: four roles as a column with a check constraint, a permission catalogue in code resolved
  through an authentication backend, and `permissions` on the session payload.
- Sharing member registration, with a cultivator's POPIA attestation on the record.
- Three role home pages rendering a destination catalogue from `permissions`, never from `role`.
- Member profile: view and edit name, nickname, mobile; avatar upload, crop and delete.
- Django admin over accounts, documents, subscriptions and payments.

**Not built — everything the club is actually for**

No plant. No strain. No batch. No listing. No price. No order. No cart. No swap. No review. No
notification. No support ticket. No cultivator organisation. No delivery address. No administrative
API of any kind.

`roles-and-permissions.md` section 13 puts this most sharply: the roles, the catalogue and the
enforcement path are built and tested, and **almost nothing they govern exists.** Twenty-nine of the
thirty destinations on the club home pages are marked *Not built yet*, honestly.

**The critical path is not a feature.** No member can sign in on a deployed environment, because
sign-in codes print to a server console and no email provider is configured. That is P1 in
`conflict.md` section D and it is Block 0 in `todo.md`.

---

## 3. Architecture

### As built

```
Browser ──▶ Next.js :3000                     Django :8000
            App Router, SSR/RSC  ─────────▶   /api/...    JSON API (django-ninja)
                                              /api/docs   OpenAPI, DEBUG only
                                              /admin/     Django admin
```

Django renders no user-facing page. Every page a member sees is rendered by Next.js, which calls the
API server-side and forwards the member's cookies. That split is the most consequential decision in
the project — `backend.md` section 2 and `frontend.md` section 2.

### The stack, corrected

The previous version of this plan specified ASP.NET Core, Entity Framework, Entra ID B2C and Azure.
None of that was built. **C1** records the divergence; this is what exists.

| Layer | Choice |
| --- | --- |
| Frontend | Next.js App Router, React, TypeScript, Tailwind |
| API | Django 5, django-ninja, async endpoints |
| Data | MySQL 8.4 in QA and production, SQLite in development. `uuid7` keys need neither — C31 |
| Identity at rest | AES field encryption plus blind indexes for ID number and email |
| Authentication | WebAuthn passkeys, emailed six-digit code fallback, Django sessions |
| Payments | Payfast — hosted checkout, signed server-to-server notification |
| Email | Console backend. **No provider configured** |
| Cache | `LocMemCache`. **Per worker, so the rate limits do not hold across replicas** — C31 |
| Hosting | Azure, West Europe. Three Container Apps — market, club, API — and a managed MySQL — C31 |

### Two domains

**C3, amended by C30.** Two storefronts, two registrable domains, and the API on a subdomain of
each:

| Host | Serves | Indexed |
| --- | --- | --- |
| `f2c.co.za` | The produce market — front door, legal pages, catalogue, account | The public pages, in production only |
| `backend.f2c.co.za` | The API, for the market | No |
| `f2c-cannabis.co.za` | The club — landing, intro, membership information, terms, rules, cost, sign-up CTA, age gate, and everything behind the gate | The landing page only, in production only |
| `backend.f2c-cannabis.co.za` | The API, for the club | No |

**There is no separate marketing site.** C3 read `f2c.co.za` as a public brochure in front of the
club; it is the store. The club's landing page and age gate are the front door of the cannabis host.

The six other categories in the member story — Biltong, Fruit, Vegetables, Nuts, Dried, Honey —
were recorded in `conflict.md` and planned for nothing. **That is no longer true.** They are the
catalogue of the produce market: a second Next.js application over the same API, on the apex domain.
See C26 and [`verticals.md`](verticals.md) section 8 for what separate registrable domains cost in
passkeys and sessions, and C30 for why the API answers on two names — each frontend calls an API
host inside its own registrable domain, which is what keeps the session cookie `SameSite=Lax`.

### Roles

**C2.** Four roles today, one per account, enforced as a column with a check constraint: `admin`,
`cultivator`, `member`, `sharing_member`.

**That column is being retired — C28.** One person may be a market customer, a club member, a
farmer's appointed staff member and a club administrator at once, and a column cannot hold that.
A role is read from the relationship instead:

| Read from | Is | Granted by |
| --- | --- | --- |
| `User.is_staff` | The UC operator. Money, refunds, administrator accounts, escalations. **Django admin only, no Next.js surface** — C29 | `createsuperuser` |
| `StorefrontStaff` | An administrator of the club or of the market. Runs it day to day | The UC operator |
| `ClubMembership` | A paying member. Buys, owns and swaps plants | Every completed registration |
| `ProducerMembership` | A cultivator or farmer, primary or appointed staff | An administrator, or the producer's primary |
| `ClubMembership`, sharing | Holds flowering plants so the swap zone is not empty. Never signs in | A cultivator, on their attestation |

`uc_admin` was to be a fifth value in the column and is never built: the UC tier is `is_staff`, and
the Django admin over accounts, documents, subscriptions and payments already exists. See C29.

---

## 4. How the phases are sequenced

The old plan sequenced by user-facing area: marketplace, then memberships, then my plants, then
reviews, then notifications, then swaps. That order cannot be built, because every one of those
areas sits on a plant model, an ownership record and an object-level permission rule that do not
exist. Six phases would each have started by inventing a third of the same schema.

This plan sequences by **what the next thing needs**:

```
Block 0  Production blockers          ── nothing can be demonstrated without these
Block 1  Catalogue: strain, product type, cultivator profile
Block 2  Cultivator organisation      ── unlocks every object-level rule (C13)
Block 3  Plant, batch, serial, status ── the spine of the whole product
Block 4  Pricing and promotions
Block 5  Browse and buy
Block 6  Ownership, harvest, fulfilment
Block 7  Reviews and ratings
Block 8  Notifications                ── harvest already needs this
Block 9  Administration API and portal
Block 10 Swap zone                    ── legally gated on C7
Block 11 Support
Block 12 Plant subscriptions, settlement, reporting
```

Two things drive that order, and both are worth stating plainly.

**The cultivator organisation comes second, not late.** `roles-and-permissions.md` risk 9 says it
"must be resolved with the cultivator organisation, not after". Every "their own" rule in the brief —
their own listings, their own stock, their own pricing, their own sharing members, the *primary*
cultivator who may appoint staff — needs it. Built after the models it scopes, it is a retrofit
across every endpoint.

**The swap zone comes last, and not only because it is hard.** It is the one feature that may be
unbuildable as specified: C7 asks whether allocating four flowering plants to a named adult is
lawful and whether a swap is a sale in substance. Scheduling it last means an opinion can be
obtained without blocking anything else, and a negative answer costs no rework.

### 4.1 Revised sequence — two storefronts

**This supersedes the order above.** The reasoning is in [`verticals.md`](verticals.md) section 10;
the change is that most of what remains unbuilt turns out to be shared between the club and the
market, and building it inside the club means building it twice.

```
Block 0    Production blockers            ── unchanged
Block 0.5  Identity decomposition         ── User / ClubMembership / ProducerMembership,
                                             the role column retired, CultivatorProfile
                                             generalised to Producer.  C27, C28.
                                             Everything below waits on it
Block A    Commerce spine                 ── catalogue, listing, search, cart, order,
                                             payment intent, review, settlement.
                                             Absorbs old Blocks 1, 4, 5, 7. Pulls C10 forward
Block B    Market vertical                ── produce types, units, stock, delivery
Block C    Club vertical                  ── plant, batch, ownership, harvest, fulfilment
                                             (old Blocks 3 and 6)
Block D    Notifications, admin, support  ── old Blocks 8, 9, 11. Two administration
                                             areas, one per storefront. No UC tier — C29
Block E    Swap zone, subscriptions       ── old Blocks 10 and 12. Still gated on C7
```

Two things drive it.

**Block 0.5 is not optional and is not deferrable.** `is_active` is derived from `status` under a
database check constraint, and `PENDING_PAYMENT` is not `ACTIVE` — so on today's model a produce
customer cannot sign in at all. Every line of market work written before the split gets written
again after it. The migration also gets dearer with every member the club signs up, because
`ClubMembership` has to be populated from live rows carrying encrypted identity numbers.

**The market is the shorter path to a transacting platform.** No ownership chain, no swap zone, no
statutory ceiling, no age gate, no copy-compliance corpus, no outstanding legal opinion. It
exercises the same spine the club needs while carrying a fraction of the regulatory load, and it
does not delay the club, because Blocks 0.5 and A are the club's work as much as the market's.

**What it costs.** Settlement — C10 — stops being a Block 12 concern. The market pays a farmer on
every order from the first day it trades.

---

## 5. The blocks

Durations are for a single developer working continuously and assume the open conflicts are resolved
before the block that names them starts.

### Block 0 — Production blockers · 1 week

An email provider, a scheduler for `lapse_memberships`, a shared cache backend, a documented backup
and rotation procedure for the field-encryption key, an `is_staff` check on staff password sign-in,
and a runtime API address so one build artefact can serve two environments.

*Nothing in this plan is demonstrable to a third party until Block 0 is done.* A member cannot sign
in without an email provider.

### Block 1 — Catalogue · 2 weeks

Strain (platform-wide, administrator-curated), finished product type with price, cultivator profile
with its public description and image, and the cultivator's own strain listing joining the two.

**C18** decides how the three levels of finished-product-type selection relate. The recommendation is
that the platform defines the catalogue, the strain listing selects a subset, and the plant inherits.

### Block 2 — Cultivator organisation · 2 weeks

The farm as a record: primary cultivator, appointed staff with full or limited rights, collection
address, and the sharing members registered under it. Object-level permission checks over all of it.

Resolves **C13** and roles risk 9. `platform.appoint_cultivator_staff` becomes exercisable for the
first time.

### Block 3 — The plant · 3 weeks

The spine. Plant with a cultivator plant ID and a platform-allocated serial, optional crop or batch
number, strain, grow price, planting date, estimated bloom and harvest dates, minimum yield,
available finished product types, and a status moving through preflowering, in bloom, harvested,
processed, shipped. Derived fields: cultivator pseudonym, leaf rating, days to bloom, days to
harvest.

Individual capture and an Excel batch upload, per `cultivator-stock-upload.md`.

The leaf rating is computed here even though nothing shows it until Block 10 — it is a property of
the plant's grow price, and **C4** separates it from star ratings for good. Its rounding tie-break is
undefined in the brief and has to be chosen.

### Block 4 — Pricing and promotions · 1.5 weeks

Cultivator-set prices on unsold inventory, a was-price shown for two weeks after a reduction,
promotions scoped by strain, period, batch or quantity, and the saving shown prominently.

### Block 5 — Browse and buy · 3 weeks

The member journey in `member-plant-purchase.md`, which is a specific three-step drill-down and not a
generic product grid:

1. **Strains.** Generic listing with strain information and *grow price from*.
2. **Cultivators offering that strain.** Price, average star rating, the cultivator's short
   description for that strain, minimum yield, available finished product types.
3. **Planting and harvest dates**, with a count of plants per date. Not individual serials.

The member chooses a date and a quantity; the system allocates specific serials.

Filters across the journey: strain, cultivator, estimated harvest, rating, top sales, price, and
promotions only.

**C9** decides when the grow price is paid and what happens when a crop fails. Both are unanswered in
the brief and both change this block's shape.

### Block 6 — Ownership, harvest and fulfilment · 3 weeks

A member's plant inventory. The cultivator converting an estimated harvest date to an actual one.
The notification that sends a member to finalise: finished product type, delivery address, and — if
**C8** says so — a courier fee. Certificates of ownership, packing labels and courier documents.
Order tracking and order queries.

Needs a delivery address model, which does not exist. **C19** decides what a cultivator sees of a
member on a packing label; the recommendation is nothing but a nickname, serials and a waybill.

### Block 7 — Reviews and ratings · 1.5 weeks

Five-star ratings and reviews on received product, shown under the member's nickname, accumulating
against both the cultivator and the individual cultivator-strain offering. Cultivator responses.

**Not** the leaf rating. C4.

### Block 8 — Notifications · 1.5 weeks

In-app and email. Harvest-finalisation, order, payment, subscription, swap and support events.

Block 6 already depends on this — a harvest notification is the only thing that tells a member to
finalise — so the two are built adjacent deliberately.

### Block 9 — Administration API and portal · 4 weeks

**C5**: the brief asks for a Next.js administrator portal, and this is where the twenty-nine planned
destinations get endpoints behind them. Split across the two tiers from C2, with an escalation queue
from the club administrator to the UC administrator.

Also here: member management, warnings, suspensions and expulsions; membership pauses and
cancellations; serial and batch tracing; recent sign-ups; and the administrator CRUD that belongs to
the UC tier alone.

### Block 10 — Swap zone · 4 weeks

**Gated on C7.** Do not start without a legal opinion.

Leaf-rating display with no Rand values anywhere in the zone. Sharing-member stock seeding the zone.
Instant swaps against sharing-member plants, confirmed swaps against member plants. Equivalent-value
matching with an explicit forfeit-the-difference acknowledgement. The four-flowering-plant holding
check, enforced on the write and prompting a member to trade down before it refuses. No swapping
after harvest for paying members, with the sharing-member exception in `harvest.md`.

**C16** decides whether a harvested plant counts toward the four. **C17** decides how equal-value
matching survives the fact that maturity is not in the leaf rating.

### Block 11 — Support · 1.5 weeks

Tickets from members and cultivators, contact us, rules and guidelines, FAQ. New strain and new
finished product type requests from cultivators, landing in the administrator's queue. Escalation
from the club tier to the UC tier.

### Block 12 — Plant subscriptions, settlement and reporting · 4 weeks

Repeating monthly plant orders by cultivator and strain, cancellable on a month's notice, several per
member — `plant-subscription.md`. This is a **different mechanic from the membership subscription**
and the old plan conflated them.

Cultivator settlement: bank details, statement of account, what is earned and when, what the platform
takes, and how money reaches a cultivator. **C10** — entirely unspecified today, and a launch blocker
for cultivators.

Refunds and partial reversals with fee withholding — **C11**. Sales, review and activity reporting.

---

## 6. Releases

| Release | Contents | Gate |
| --- | --- | --- |
| **R0** | Block 0 | A member can sign in on QA |
| **R1** | Blocks 1–2 | A cultivator exists as a record, with staff and a collection address |
| **R2** | Block 3 | Stock is on the platform, individually and by upload |
| **R3** | Blocks 4–5 | A member can find and buy a plant. **First plant revenue** |
| **R4** | Blocks 6–8 | A member receives product. **The loop closes** |
| **R5** | Block 9 | The club is run from the portal, not from the Django admin |
| **R6** | Block 10 | Swap zone, if C7 permits |
| **R7** | Blocks 11–12 | Support, plant subscriptions, settlement, reporting |

Against the revised sequence in section 4.1 the releases become:

| Release | Contents | Gate |
| --- | --- | --- |
| **R0** | Block 0 | A member can sign in on QA |
| **R1** | Block 0.5 | One person can hold an identity, a club membership and a producer role at once |
| **R2** | Block A | Anything can be listed, found, bought, paid for, settled and reviewed |
| **R3** | Block B | **The market trades. First order revenue, no legal opinion required** |
| **R4** | Block C | A member buys a plant and receives product. The club's loop closes |
| **R5** | Block D | Each storefront is run from its own administration area. The UC tier stays in the Django admin — C29 |
| **R6** | Block E | Swap zone, if C7 permits. Plant subscriptions and reporting |

---

## 7. Minimum viable product

The old plan set MVP at the end of its Phase 3 — landing, registration, authentication, profile,
marketplace, ordering, payments, memberships. Everything in that list except the marketplace and
ordering is built, and those two are the whole product.

**MVP is R3.** A member joins, pays a subscription, browses strains and cultivators, and buys a
plant with a grow service. That is the first version that takes money for the thing the club sells.

**Under the revised sequence, MVP moves to R3 there — the market.** It is the first version that
takes money for something, it needs no legal opinion, and it is built entirely out of work the club
needs anyway. The club's own MVP follows at R4 and is not delayed by it.

**R4 is the first version that delivers anything.** Between R3 and R4 a member has paid for a plant
and has nothing to show for it. The gap between those two releases is a real commercial exposure, not
just a schedule — plan the cash and the member communications for it.

---

## 8. Open decisions blocking work

Full detail in [`conflict.md`](conflict.md). These block the block named.

| # | Decision | Blocks |
| --- | --- | --- |
| C6 | Is a sharing member a real person or a placeholder | Block 10, and unwinding it later means deleting stored ID numbers |
| C7 | Is the sharing-member scheme lawful — **legal opinion** | Block 10 entirely |
| C8 | Is a courier fee payable at harvest | Block 6 |
| C9 | When is the grow price paid, and what happens on crop failure | Block 5 |
| C10 | How are cultivators settled — **and how farmers are paid** | Now Block A. The market pays a producer on every order |
| C11 | How do partial refunds work | Block 12 |
| C13 | Object-level permissions | Blocks 4–9 — sequenced into Block 2 |
| C15 | Household and dried-weight limits | Block 10, and the club rules |
| C16 | Does a harvested plant count toward the four | Block 10 |
| C17 | Equal-value swaps versus maturity | Block 10 |
| C18 | Where finished product types are selected | Block 1 |
| C19 | What a cultivator sees of a member | Block 6 |
| C20 | Membership fee on a copy-compliance-governed page | Block 0 or Block 1, whenever the fee goes on the landing page |
| C26 | Two storefronts on one platform — **decided**, see `verticals.md` | Restructures every block below Block 0 |
| C27 | Splitting `User` into identity and membership — **decided** | Block 0.5, and everything after it |
| C28 | Retiring the single role column — **decided** | Block 0.5, and every permission test |
| C29 | UC tier is `is_staff` in the Django admin — **decided** | Shrinks Block D. Removes three catalogue actions |

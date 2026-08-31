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

Everything in the built list is in the repository with tests. Nothing in the not-built list exists.

**Built and reachable from a browser**

*Identity and access*

- Identity decomposed. `User` is an identity and nothing else; standing and authority are carried by
  `ClubMembership`, `StorefrontStaff` and `ProducerMembership`. **The role column is retired — C28**,
  so a role is read from the relationship, and an unpaid registrant can sign in — Block 0.5.
- A permission catalogue in code, resolved through an authentication backend, with `permissions` on
  the session payload.
- Authentication: passkeys and emailed six-digit codes, sessions, CSRF, rate limits, passkey
  enrolment and revocation.
- Soft delete and POPIA erasure.

*The club storefront — `frontend/club`, `f2c-cannabis.co.za`*

- Public landing page with compliance-governed copy, age gate, and search-indexing rules per host
  and per environment.
- Sign-up: member details with RSA ID and mobile validation, nickname availability, club document
  agreements, registration stored.
- Membership payment: Payfast checkout, signed notification handling, subscription and payment
  records, activation on payment, a `lapse_memberships` command.
- Member profile: view and edit name, nickname, mobile; avatar upload, crop and delete.
- Three role home pages rendering a destination catalogue from `permissions`, never from a role.
- Administrator screens: the membership register at `/admin/members` — read, edit, suspend and
  reinstate, with a recorded disclosure of an identity number read in full — and the strain
  catalogue at `/admin/strains`, over `app/club/strains/api.py`.

*The market storefront — `frontend/market`, `f2c.co.za`*

- Front door, legal index, sign-in by passkey or emailed code, sign-up, and the signed-in account
  area — home, details, security. Runs on port 3001 — Block B.
- `POST /api/customers/register`, unauthenticated, over `app/core/accounts/registration.py`. **The
  store takes accounts end to end**: sign-up, sign-in code, account area. It lives in `accounts`
  rather than in `app/market`, which stays empty deliberately.

*Domain models*

- **Strain catalogue** — `Strain`, `CultivatorStrainListing`, and the aroma and effect
  vocabularies — Block 1.
- **Finished product type**, with its price, availability and display order — Block 1.
- **`Producer`** — the farm as a record: trading name, public profile, the storefronts it sells into,
  collection address, encrypted bank details, and appointments carrying primary, full or limited
  rights. Deliberately not cannabis-specific, which is why it sits in `app/commerce` — Block 0.5.
- **The plant** — `Plant`, `Batch`, `PlantOwnership` and `SerialCounter`: platform-allocated serials,
  an append-only ownership ledger, a per-cultivator Excel template and batch upload, individual
  capture, stock-on-hand export, leaf rating, and the disable actions — Block 3.
- Documents for two storefronts, scoped by storefront with `audience` and `agreement`, the consent
  ledger, and `ProducerAgreement` for a farm's signed terms.
- Sharing member registration as a **placeholder** — a nickname and a producer, with no identity
  number, no age rule and no POPIA attestation, per C6.
- Django admin over accounts, documents, subscriptions, payments, producers, strains and plants.

**Not built — what the models are still waiting for**

No price change. No promotion. No cart. No order. No payment intent for anything but the membership.
No delivery address. No harvest. No fulfilment. No swap. No review. No notification. No support
ticket. No settlement. No produce vertical — `app/market` is an empty package, and
`frontend/README.md` records why the emptiness is not an unfinished step.

**The models landed ahead of the endpoints, and that is the shape of the gap.** There is no `api.py`
in `app/club/plant` at all: the plant, its serials, its batches and its ownership ledger are built
and tested, and the only ways to reach any of them are the Django admin and three management
commands. Block 2's producer models sit the same way — `ProducerRole` carries full and limited
rights and the only way to appoint anybody is the admin. `roles-and-permissions.md` section 13 still
puts it most sharply: the catalogue and the enforcement path are built and tested, and most of what
they govern has no surface. Twenty-six of the twenty-nine destinations on the club home pages still
carry no `href`, honestly.

**The critical path is not a feature.** No member can sign in on a deployed environment, because
sign-in codes print to a server console and no email provider is configured. That is P1 in
`conflict.md` section D and it is Block 0 in `todo.md`, where seventeen lines are still open.

---

## 3. Architecture

### As built

```
Browser ──▶ Next.js :3000  club   ┐           Django :8000
            Next.js :3001  market ┴────────▶  /api/...    JSON API (django-ninja)
            App Router, SSR/RSC               /api/docs   OpenAPI, DEBUG only
                                              /admin/     Django admin
```

Django renders no user-facing page. Every page a member or a customer sees is rendered by one of the
two Next.js applications, which call the API server-side and forward the caller's cookies. That split
is the most consequential decision in the project — `backend.md` section 2 and `frontend.md`
section 2.

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
| Cache | Redis — Azure Managed Redis in QA and production, `redis:7-alpine` locally. `f2c/cache.py` refuses a deployed environment that names none. `LocMemCache` survives only as the no-configuration fallback, which keeps the suite runnable with no servers — C31 |
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

**C2.** There were four roles, one per account, enforced as a column with a check constraint:
`admin`, `cultivator`, `member`, `sharing_member`.

**That column is retired — C28, closed in Block 0.5.** One person may be a market customer, a club
member, a farmer's appointed staff member and a club administrator at once, and a column cannot hold
that. A role is read from the relationship instead:

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
before the block that names them starts. **They are the original estimates, and several of these
blocks are now partly or wholly built** — the status line under each heading is the current position.
[`todo.md`](todo.md) is the item-by-item count.

### Block 0 — Production blockers · 1 week

**Status: about half done, and what remains is mostly provisioning rather than code.**

Done: the shared cache backend — Redis, after `DatabaseCache` was tried and could not serve an async
API; a runtime API address, so one build artefact serves two environments; the API container and both
Next.js images; verified TLS to MySQL; the HTTPS settings `check --deploy` asks for, enforced at
container start rather than remembered; and the CI job's silent SQLite fallback.

Open: an email provider, a scheduler for `lapse_memberships`, a documented backup and rotation
procedure for the field-encryption key, the Azure resources themselves, DNS and TLS for four
hostnames, `DJANGO_BEHIND_PROXY` on the API container, the founding administrators granted their
authority by hand, and the transborder disclosure West Europe requires under POPIA.

*Nothing in this plan is demonstrable to a third party until Block 0 is done.* A member cannot sign
in without an email provider.

### Block 0.5 — Identity decomposition · done

**Status: done.** It is not in the original sequence — section 4.1 introduced it, and everything
below waited on it.

`User` reduced to an identity, with `ClubMembership`, `StorefrontStaff` and `ProducerMembership`
carrying standing and authority. The role column retired — **C28**. `CultivatorProfile` generalised
into `Producer` — **C27**. Two storefronts in the schema, documents scoped by storefront, the Django
layout split into `app/core`, `app/commerce`, `app/club` and `app/market`, and `frontend` made an npm
workspace root with the club application under `frontend/club`.

It is why an unpaid registrant can sign in, which is what a produce customer is on the day they
register.

### Block B — Market vertical · 2 weeks

**Status: the storefront and its accounts are built; the vertical itself is not.**

Built: `frontend/market` as the second Next.js application — front door, legal index, sign-in,
sign-up and the signed-in account area — and `POST /api/customers/register` behind it, so the store
takes accounts end to end. A customer may manage their own profile, which cost a codename:
`platform.manage_own_profile` was granted by a relationship no shopper holds, and every profile
endpoint is scoped to the caller anyway, so it is retired rather than widened.

Open: produce types, units, stock and delivery — the vertical itself, which section 4.1 names and
does not decompose. The store's brand. The market's own documents, which must not be published at
`agreement=at_registration` until the registration contract carries consents. An administration area
for it. And `frontend/packages/*`, now that there is a second consumer to draw the seams against.

`app/market` is an empty package deliberately; `frontend/README.md` records why.

### Block 1 — Catalogue · 2 weeks

**Status: every model is built. Two administrator screens and one member-facing page remain.**

Strain (platform-wide, administrator-curated), finished product type with price, the cultivator's
public description and image — now columns on `Producer` — and `CultivatorStrainListing` joining
the two, carrying the brief's six fields exactly. The strain screens at `/admin/strains` are
live.

Left: administrator CRUD for finished product types, the cultivator's own listing screen, and the
member-facing catalogue page, which belongs to Block 5.

**C18** decides how the three levels of finished-product-type selection relate. **The
recommendation is already built** — the plant inherits from its listing with no per-plant
override — so ratifying it costs nothing and reversing it is a model change.

### Block 2 — Cultivator organisation · 2 weeks

**Status: the models landed early, in Block 0.5. What is left is the endpoints.**

Built: the farm as a record — `Producer`, with collection address and encrypted bank details, written
so a farmer supplying the produce market is the same record with a different storefront row; the
primary cultivator flag on `ProducerMembership`; appointed staff carrying full or limited rights; and
sharing member registration as a placeholder, per **C6**.

**C13 and roles risk 9 are closed.** *Only the primary may appoint staff* was an object-level rule
the catalogue could not express, and it is a column now.

Left: `platform.appoint_cultivator_staff` has no endpoint and is exercisable only in the Django
admin; sharing member read, update and withdraw; the object-level rules that arrive with those
endpoints; and a lifecycle on `Producer`. **That last one is a regression, recorded rather than
dropped** — `Strain.exclusive_to` used to refuse a cultivator who had left by checking their account,
and an organisation is not erased and has no departure state, so the rule has nothing left to check.

### Block 3 — The plant · 3 weeks

**Status: built, and unreachable over HTTP.**

The spine. `Plant` with a cultivator plant ID and a platform-allocated serial, `Batch` as a record
rather than a string, strain through the listing so the two cannot disagree, grow price, planting
date, estimated bloom and harvest dates, minimum yield, finished product types inherited from the
listing, and a status moving through preflowering, in bloom, harvested, processed and shipped.
Derived: cultivator pseudonym, leaf rating, and the day counts as properties rather than columns.
`PlantOwnership` is the append-only tenure log behind every transfer.

Individual capture and a per-cultivator Excel batch upload, per `cultivator-stock-upload.md`, sharing
one write path rather than two. Stock-on-hand export. Disable actions for a plant and for a batch.

The leaf rating is computed here even though nothing shows it until Block 10 — it is a property of
the plant's grow price, and **C4** separates it from star ratings for good. Its rounding tie-break
was undefined in the brief and **is now chosen: round half up**, in `Decimal` throughout.

Left: there is no `api.py` in `app/club/plant` at all, so all three routes are staff-side and a
cultivator does nothing themselves until Block 9. `platform.disable_plant` and
`platform.disable_batch` are in the catalogue and **nothing calls `has_perm` on either** — the admin
authorises on `is_staff` like every other Django admin page. And a grow price under R250 rounds to a
leaf rating of 0.0, which has no swap value at all; decide before Block 10 relies on it.

### Block 4 — Pricing and promotions · 1.5 weeks

**Status: not started.** Section 4.1 folds it into Block A, the commerce spine.

Cultivator-set prices on unsold inventory, a was-price shown for two weeks after a reduction,
promotions scoped by strain, period, batch or quantity, and the saving shown prominently.

### Block 5 — Browse and buy · 3 weeks

**Status: not started.** Also Block A — the market needs the same journey, and building it inside the
club means building it twice.

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

**Status: not started — but the ownership ledger it is built on already exists.** `PlantOwnership`
and the transfer that writes it landed with Block 3.

A member's plant inventory. The cultivator converting an estimated harvest date to an actual one.
The notification that sends a member to finalise: finished product type, delivery address, and — if
**C8** says so — a courier fee. Certificates of ownership, packing labels and courier documents.
Order tracking and order queries.

Needs a delivery address model, which does not exist. **C19** decides what a cultivator sees of a
member on a packing label; the recommendation is nothing but a nickname, serials and a waybill, and
the stock export already works that way.

### Block 7 — Reviews and ratings · 1.5 weeks

**Status: not started.** Also Block A.

Five-star ratings and reviews on received product, shown under the member's nickname, accumulating
against both the cultivator and the individual cultivator-strain offering. Cultivator responses.

**Not** the leaf rating. C4, and nothing in `plant` imports or touches a rating.

### Block 8 — Notifications · 1.5 weeks

**Status: not started.**

In-app and email. Harvest-finalisation, order, payment, subscription, swap and support events.

Block 6 already depends on this — a harvest notification is the only thing that tells a member to
finalise — so the two are built adjacent deliberately.

### Block 9 — Administration API and portal · 4 weeks

**Status: three of the twenty-nine destinations are live** — the membership register, the strain
catalogue and the member's own profile. Twenty-six still render as *Not built yet* with no endpoint
behind them, so most administration still happens by hand in the Django admin.
`club-navigation.ts` is the count.

Built: view, edit, suspend and reinstate a member, with recent sign-ups as a filter on the same
register rather than a screen of its own, and **reading an identity number in full, recorded** —
written before the column is decrypted and inside the same transaction, so a read that happened is a
read that is logged. There is no create and no delete, by decision: sign-up is the only route into
the membership, because an account typed in by hand would have no consent ledger behind it. Strain
catalogue CRUD likewise has no delete — a strain the club has sold against cannot be removed, and
retirement is the whole answer.

Left: cultivator CRUD, sharing member CRUD and collection addresses; warnings, suspensions and
expulsions, which need a sanction model and there is none; finished product types; listings
read-write; the platform-wide pricing and inventory views; and `GET /api/documents/outstanding`,
which exists and has no frontend caller, so a member owing a re-acceptance is never asked.

**The two tiers no longer split this block — C29.** The UC tier gets no Next.js surface at all:
`platform.manage_administrators`, `platform.refund_transaction` and `platform.cancel_membership` left
the catalogue entirely, because an operation the Django admin already performs under `is_staff` needs
no codename, no endpoint and no tier comparison. **The escalation queue survives as a model** —
raised by a storefront administrator in Next.js, worked by the UC operator in the Django admin — and
it is the only UC-tier item with anything left to build.

### Block 10 — Swap zone · 4 weeks

**Status: not started and still gated on C7. Do not start without a legal opinion.** The leaf rating
it matches on is built and stored, which is the one dependency that will not hold it up.

Leaf-rating display with no Rand values anywhere in the zone. Sharing-member stock seeding the zone.
Instant swaps against sharing-member plants, confirmed swaps against member plants. Equivalent-value
matching with an explicit forfeit-the-difference acknowledgement. The four-flowering-plant holding
check, enforced on the write and prompting a member to trade down before it refuses. No swapping
after harvest for paying members, with the sharing-member exception in `harvest.md`.

**C16** decides whether a harvested plant counts toward the four. **C17** decides how equal-value
matching survives the fact that maturity is not in the leaf rating.

### Block 11 — Support · 1.5 weeks

**Status: not started.**

Tickets from members and cultivators, contact us, rules and guidelines, FAQ. New strain and new
finished product type requests from cultivators, landing in the administrator's queue. Escalation
from a storefront administrator to the UC tier, worked in the Django admin — C29.

**One decision waits for this block rather than for Block B.**
`platform.submit_support_request` is granted by a relationship a store customer does not hold, so a
shopper cannot raise a ticket. Is support a platform-level entitlement, as a profile turned out to
be, or does each storefront answer its own queue — in which case it stays a permission and gains a
market twin. Nothing is refused that anybody can reach today, because neither storefront shows a
support route.

### Block 12 — Plant subscriptions, settlement and reporting · 4 weeks

**Status: not started, and settlement has left it.** Section 4.1 pulls **C10** forward into Block A,
because the market pays a farmer on every order from the first day it trades. The heading keeps its
name to match `todo.md`; the work does not sit here any more.

Repeating monthly plant orders by cultivator and strain, cancellable on a month's notice, several per
member — `plant-subscription.md`. This is a **different mechanic from the membership subscription**
and the old plan conflated them.

Refunds and partial reversals with fee withholding — **C11**. Sales, review and activity reporting,
and the revenue, membership, plant sales and swap dashboards.

Settlement — what the platform takes, when a cultivator earns, and how money reaches one — is
entirely unspecified today and remains a launch blocker for cultivators wherever it is built. Block
0.5 put a collection address and encrypted bank details on `Producer` and **stopped there on
purpose**: a tax number or a mandate reference would have been inventing a commercial model in a
schema.

---

## 6. Releases

The original release plan, kept because the gates still read correctly and because the numbering is
cited elsewhere. **It is superseded by the revised table below** — section 4.1 re-ordered the blocks
it packages.

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

Against the revised sequence in section 4.1 the releases become — **and this is the one to plan
against**:

| Release | Contents | Gate | Position |
| --- | --- | --- | --- |
| **R0** | Block 0 | A member can sign in on QA | In progress. The gate is **not met**: no email provider |
| **R1** | Block 0.5 | One person can hold an identity, a club membership and a producer role at once | **Done** |
| **R2** | Block A | Anything can be listed, found, bought, paid for, settled and reviewed | Not started. The catalogue half of it is built — Block 1 |
| **R3** | Block B | **The market trades. First order revenue, no legal opinion required** | Storefront and accounts built; the produce vertical is not |
| **R4** | Block C | A member buys a plant and receives product. The club's loop closes | Not started. The plant itself is built — Block 3 |
| **R5** | Block D | Each storefront is run from its own administration area. The UC tier stays in the Django admin — C29 | Three of twenty-nine destinations live |
| **R6** | Block E | Swap zone, if C7 permits. Plant subscriptions and reporting | Not started, gated on C7 |

**R1 is complete and R0 is not, and that is deliberate rather than a slip.** What is left of R0 is
provisioning and one commercial decision about a mail provider; it needs an Azure subscription and a
credit card, not a developer. R1 was code and could proceed in parallel. The consequence to hold on
to is that **finishing a later release does not make an earlier one shippable** — nothing at all
reaches a third party until R0's gate is met, so R1 being done buys no demonstrable ground.

The same reading applies to R2 through R5. Each has had its models built ahead of its endpoints, so
none of them is starting from nothing, and none of them is close to its gate either. A model with no
route in front of it demonstrates nothing.

---

## 7. Minimum viable product

The old plan set MVP at the end of its Phase 3 — landing, registration, authentication, profile,
marketplace, ordering, payments, memberships. Everything in that list except the marketplace and
ordering is built, and those two are the whole product.

**Both sequences put MVP at their own R3, and they mean different things.** Naming them by block
rather than by number is the only way to keep them apart:

- **Original sequence — MVP is Blocks 4–5.** A member joins, pays a subscription, browses strains
  and cultivators, and buys a plant with a grow service. The first version that takes money for the
  thing the club sells.
- **Revised sequence — MVP is Block B, the market.** The first version that takes money for
  *anything*. It needs no legal opinion, carries no age gate and no statutory ceiling, and is built
  entirely out of work the club needs anyway. **The club's own MVP follows at Block C and is not
  delayed by it** — Blocks 0.5 and A are the club's work as much as the market's.

**The revised sequence also closes a gap the original one carried.** Under the original, R4 was the
first release that delivered anything: between R3 and R4 a member had paid for a plant and had
nothing to show for it, which was a real commercial exposure across two releases rather than a
scheduling detail. Under the revised sequence the club's purchase and its fulfilment both sit inside
Block C, so that gap stops being a release boundary and becomes a sequencing decision inside one
block. **It does not disappear** — build fulfilment last within Block C and the same exposure returns
— but it is now weeks rather than months, and it is one team's ordering decision rather than a cash
plan.

**What has not changed is that no release is demonstrable yet.** MVP under either reading is behind
R0, and R0 is behind an email provider.

---

## 8. Open decisions blocking work

Full detail in [`conflict.md`](conflict.md), which is the register and the authority on status. The
tables below name the block each one holds up, by its old number and by the letter section 4.1 gives
it.

### Still open — somebody has to decide

| # | Decision | Holds up |
| --- | --- | --- |
| C7 | Is the sharing-member scheme lawful — **legal opinion, not a product call** | Block 10 → Block E, entirely. Do not start without it |
| C8 | Is a courier fee payable at harvest | Block 6 → Block C |
| C9 | When is the grow price paid, and what happens on crop failure | Block 5 → Block A. Both change the block's shape |
| C10 | How are cultivators settled — **and how farmers are paid** | Block A, pulled forward from Block 12. The market pays a producer on every order from the day it trades |
| C11 | How do partial refunds work, with fees withheld | Block 12 → Block E. Downstream of C10 |
| C14 | May an administrator create and manage sharing members | Block 2 and Block 9 → Block D. **C5 moved the ground under the standing decision**: the prescribed route is the operator's back office, and a Next.js-only club administrator has no access to it |
| C15 | Household and dried-weight limits | Block 10 → Block E, and the club rules |
| C16 | Does a harvested plant count toward the four | Block 10 → Block E |
| C17 | Equal-value swaps versus maturity | Block 10 → Block E |
| C18 | Where finished product types are selected | Block 1 → Block A. **The recommendation is already built** — the plant inherits from its listing — so ratifying costs nothing and reversing is a model change |
| C19 | What a cultivator sees of a member on a packing label | Block 6 → Block C. POPIA-relevant. The stock export already implements the recommendation — nickname only |
| C20 | Membership fee on a copy-compliance-governed page | Block 0 or Block 1. The one item still blocked on the landing page |
| — | **The leaf-rating floor.** A grow price under R250 rounds to 0.0, which has no swap value at all. `swap-zone` sets no floor and its cheapest example is R500 | Block 10 → Block E. Recorded under C4 in `todo.md` and holding no number of its own |

**C7 is the one to move first.** It is the only item on this list that cannot be answered inside the
business, it gates an entire block, and the block it gates is four weeks of work that nothing else
depends on — so it is also the one most easily left until it is the critical path.

### Decided, and recorded here because they restructured the plan

| # | Decision | What it changed |
| --- | --- | --- |
| C6 | A sharing member is a **placeholder, not a person** | Block 10 → Block E. Registration is a nickname and a producer, with no identity number, no age rule and no POPIA attestation — an attestation that a placeholder had consented was a ceremony around a fiction |
| C26 | Two storefronts on one platform — see `verticals.md` | Restructures every block below Block 0 |
| C27 | Splitting `User` into identity and membership | Block 0.5, and everything after it |
| C28 | Retiring the single role column | Block 0.5, and every permission test |
| C29 | The UC tier is `is_staff` in the Django admin | Shrinks Block D. Removes three catalogue actions and the second administration band |
| C30 | `f2c.co.za` is the market, `f2c-cannabis.co.za` is the club, and the API answers on a subdomain of each | The deployment configuration, and two variables that are easy to get backwards |
| C31 | Three Container Apps, managed MySQL, Managed Redis, West Europe | Most of what is left of Block 0, and a POPIA transborder disclosure |

### No decision left — only implementation

| # | Position |
| --- | --- |
| C13 | **Object-level permissions: the design question is answered by C28.** "Their own" pointed at nothing while a role was a column, which is why `RoleBackend` refused every object-level question rather than answer one wrongly. `ProducerMembership` is a row per person per producer now, and the primary-appoints-staff rule is enforced off it. The rest are joins against the same rows, written in the services that own each record. What stays open is that work, not a decision |
| C12 | **A cultivator who wants to buy: substantially closed by C28.** The old recommendation was "a second account, not a widened role", which was the accepted cost of one role per account. That cost is gone: `permissions_for` reads three relationships, so a cultivator who takes out a club membership on the same account holds `purchase_plants`, `use_swap_zone` and `offer_inventory_for_swap` from that membership. What is left is commercial — may a grower hold a membership — and confirming that browsing is all the drawio story meant |

C21 through C25 are documentation drift in `conflict.md` section C and need no decision. **C25 is the
exception worth tracking**: a test that fails about one run in thirty, which is a Block 0 line and a
CI credibility problem rather than a product question.

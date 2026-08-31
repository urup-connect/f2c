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
| Membership subscription | Recurring, monthly, Payfast. **Collected by F2C**, 40/60 with the club — C10 | **Built** |
| Plant purchase with grow service | Per order. **Collected by the club** through a second gateway, 15% commission to F2C — C10 | Not built. The gateway is not built either — C10.1 |
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
- Sharing member registration, currently as a **placeholder** — a nickname and a producer, with no
  identity number, no age rule and no POPIA attestation. **Built against a decision that has since
  been reversed**: C6 now makes a sharing member a real person, and the identity number, age rule,
  attestation and erasure exemption all come back. The code has not been changed yet.
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

**The critical path is not a feature.** No member can sign in on a *deployed* environment, because
QA and production have no mail configuration — not because none exists. P1 said sign-in codes print
to a console, and that was wrong: the console backend survives only under `DEBUG` and `_mailer`
refuses to boot a deployed environment naming no host, so this was always provisioning rather than
code. A provider is now configured locally for both storefronts and the club mailbox authenticates.
What is left of P1 is the market mailbox, which does not, and the same values set on the deployed
environments. Block 0 in `todo.md` has twenty lines still open, one blocked and one part-built.

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
| Payments | Payfast — hosted checkout, signed server-to-server notification. **Membership only.** Member purchases settle into a different entity's account through a second gateway, PayGate or Stitch undecided, and nothing is built — C10, C10.1 |
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
Block 10 Swap zone                    ── no longer gated: C7 is decided, residual risk
Block 11 Support
Block 12 Plant subscriptions, settlement, reporting
```

Two things drive that order, and both are worth stating plainly.

**The cultivator organisation comes second, not late.** `roles-and-permissions.md` risk 9 says it
"must be resolved with the cultivator organisation, not after". Every "their own" rule in the brief —
their own listings, their own stock, their own pricing, their own sharing members, the *primary*
cultivator who may appoint staff — needs it. Built after the models it scopes, it is a retrofit
across every endpoint.

**The swap zone comes last, and the reason has changed.** It was scheduled last because it might be
unbuildable as specified — C7 asked whether allocating four flowering plants to a named adult is
lawful and whether a swap is a sale in substance. **C7 is now decided as residual risk**: the swap
model is in use by other clubs and treated as defendable, and the plants do consume the sharing
member's own allowance. So the block is no longer gated, and it comes last on ordinary grounds — it
is four weeks of work, it depends on the plant and the leaf rating, and nothing else depends on it.
What it now depends on that it did not before: C15, the four-flowering-plant holding check, which
became a statutory ceiling rather than a convention the moment C7 was answered.

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
                                             payment intent, review, settlement, and a
                                             second payment gateway.
                                             Absorbs old Blocks 1, 4, 5, 7.
                                             Pulls C10 forward, and C10.1 with it
Block B    Market vertical                ── produce types, units, stock, delivery
Block C    Club vertical                  ── plant, batch, ownership, harvest, fulfilment
                                             (old Blocks 3 and 6)
Block D    Notifications, admin, support  ── old Blocks 8, 9, 11. Two administration
                                             areas, one per storefront. No UC tier — C29
Block E    Swap zone, subscriptions       ── old Blocks 10 and 12. Ungated: C7 decided
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
every order from the first day it trades. It also pulls in **C10.1**, a second payment gateway: the
membership fee is collected by F2C through the built Payfast integration, and everything a member buys
is collected into the Cultivators Collective's account through a gateway that does not exist yet. The
block cannot specify a payment intent without knowing which one.

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
sharing member registration, built as a placeholder under the **superseded** reading of C6 and now
requiring the identity number, age rule and attestation back.

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
authorises on `is_staff` like every other Django admin page.

The leaf-rating floor **is now decided**: a rating floors at 0.1 rather than rounding to 0.0, and a
plant under one whole step of 0.5 cannot enter the swap zone — `Plant.assert_swappable` refuses it
with the code `below_swap_value` and `Plant.objects.swappable()` excludes it. `swap-zone.md` carries
the reasoning.

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

**C9 is decided and it shapes the checkout.** The member **pays in full at order**, the club **holds
the money** until delivery is confirmed, and the cultivator **guarantees delivery**. So the cart ends
in a single full-price payment — no deposit, no balance due, no receivables — and the order carries a
**held or released** state from the moment it is created. A failed crop is **substituted** with an
equivalent plant, same strain and a leaf rating no lower, and the held funds follow the substitute
serial; a refund happens only where no equivalent exists. The substitution offer itself — how it
reaches the member, how long they have, and what happens in the silence — is a specification item for
this block and Block 6, and it should be answered with the same rule as C8's unanswered harvest
notification rather than a second one.

**The guarantee has to be said, not merely implemented.** It is the reason a member is asked for the
full price of something that does not exist yet, and it belongs in the introductory copy and the
sign-up journey — and, because a guarantee is a term of sale, in the versioned club documents rather
than only in a hero paragraph. C9 carries the detail and the copy-governance constraint.

### Block 6 — Ownership, harvest and fulfilment · 3 weeks

**Status: not started — but the ownership ledger it is built on already exists.** `PlantOwnership`
and the transfer that writes it landed with Block 3.

A member's plant inventory. The cultivator converting an estimated harvest date to an actual one.
The notification that sends a member to finalise: finished product type and delivery address, with
**no money in it** — **C8** folds courier into the price paid at order and settles it to Pargo, and
the launch product types carry no manufacturing charge. Certificates of ownership, packing labels
and courier documents. Order tracking and order queries.

**That confirmation is what makes ownership final**, and it closes the swap window on the plant —
C8 again, and it is a constraint on Block 10 as much as on this block. Build the finalisation as a
zero-total transaction rather than a two-field form: **C35** puts a real charge on this screen the
moment a priced product type is listed. **C8 leaves one thing open** — what happens when the owner
never answers the notification. Answer it before this block is specified.

**Delivery is also what releases a cultivator's money** — C9 holds the member's payment from order
until delivery is confirmed. **Which event counts as confirmed is C9.1 and is open**: the preference
is Pargo's delivery or collection scan, so if this block integrates Pargo, find out early whether that
event is exposed. The fallbacks are worse, and one of them adds money to the silence C8 already
flagged.

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

**Status: not started, and no longer gated.** C7 is decided as residual risk — the swap model is
defendable and a sharing member's plants consume their own allowance. The leaf rating it matches on is
built and stored, which is the one dependency that will not hold it up.

**Two things now sit in front of it that did not before.** C15, the four-flowering-plant holding
check, is a prerequisite rather than a refinement — the ceiling is statutory and attaches to a named
adult. And the holding check must count plants per member without asking what kind of member, because
C33 requires the sharing-member role to be droppable once the platform has momentum.

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

Refunds and partial reversals with fee withholding — **C11**, where who refunds is now answered (the
club refunds the member; the platform's commission is not refundable) and the mechanism waits on the
gateway choice. Sales, review and activity reporting, and the revenue, membership, plant sales and
swap dashboards.

Settlement — what the platform takes, when a cultivator earns, and how money reaches one — is
still a launch blocker for cultivators wherever it is built, though **two of the three are now
answered.** A cultivator earns **at delivery** (C9). What the platform takes is **15% of a member
transaction and 40% of the membership fee** (C10), and the money map behind those numbers is the
larger change: the membership fee is collected by **F2C** through the built Payfast integration and
60% is owed onward to the club, while everything a member buys is collected by the **Cultivators
Collective** through a second gateway that does not exist. The ratios themselves are out of scope for
the application, but the commission has to reach it as a recorded amount, because a statement of
account without a commission line cannot be reconciled.

**How money reaches a cultivator is still unanswered, and it is now the whole of the gap.** Payfast
collects and does not disburse; PayGate and Stitch are candidates for collection, not payout. The
working assumption is a manual EFT run, which makes the application's obligation a **payment run** —
a payable list per cultivator per period, the released orders behind each line, and a recorded payment
against it — rather than a payout integration.

The member's money is held from order until delivery, so the statement of account has to carry
**held**, **releasable** and **paid** as separate lines. Where the funds sit while held is a
commercial and banking matter and is **out of scope for the application** — the platform records the
state and reports it; it does not hold the cash, and C10 confirms it never receives it. Block
0.5 put a collection address and encrypted bank details on `Producer` and **stopped there on
purpose**: a tax number or a mandate reference would have been inventing a commercial model in a
schema. The payment run is what those bank details are for.

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
| **R6** | Block 10 | Swap zone — C7 decided, no longer conditional |
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
| **R6** | Block E | Swap zone. Plant subscriptions and reporting | Not started. **Ungated** — C7 decided as residual risk |

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
| C9.1 | Which event confirms delivery and releases the held funds | Block A's settlement and Block C's fulfilment. The preference is Pargo's delivery or collection scan; it cannot be fixed until the integration is understood |
| C10 | How are cultivators settled — **and how farmers are paid** | Block A, pulled forward from Block 12. **Substantially answered**: the club collects member purchases and owes F2C 15%; F2C collects the membership fee and owes the club 60%; a cultivator earns at delivery (C9). What is left is the commission base against the courier leg, whether the commission shows on a statement, **how a cultivator is actually paid** — no gateway disburses, so a payment run — and the market's leg, which is unstated and trades first |
| C10.1 | **PayGate or Stitch**, and a second gateway into the club's account | Block A, and it is build work rather than a question about the brief. Only Payfast exists and it bills the membership fee alone. Also gates C11 — a gateway that reverses makes a refund a status, one that does not makes it a ledger |
| C11 | How do partial refunds work, with fees withheld | Block 12 → Block E. Downstream of C10 and now of C10.1. **Narrowed by C9**: a failed crop is substituted, and where it is refunded the money is still held, so what is left here is a refund *after* release. **Who refunds is answered** — the club refunds the member and the platform's 15% is not refundable; the mechanism, a gateway reversal or a member account credit, waits on the gateway |
| C14 | May an administrator create and manage sharing members | Block 2 and Block 9 → Block D. **C5 moved the ground under the standing decision**: the prescribed route is the operator's back office, and a Next.js-only club administrator has no access to it |
| C15 | Household and dried-weight limits | Block 10 → Block E, and the club rules. **Promoted by C7** — the four-plant ceiling is statutory and attaches to a named adult, so the holding check is a prerequisite of the block |
| C16 | Does a harvested plant count toward the four | Block 10 → Block E. Promoted with C15 — it decides what the holding check counts |
| C17 | Equal-value swaps versus maturity | Block 10 → Block E |
| C18 | Where finished product types are selected | Block 1 → Block A. **The recommendation is already built** — the plant inherits from its listing — so ratifying costs nothing and reversing is a model change |
| C19 | What a cultivator sees of a member on a packing label | Block 6 → Block C. POPIA-relevant. The stock export already implements the recommendation — nickname only |
| C20 | Membership fee on a copy-compliance-governed page | Block 0 or Block 1. The one item still blocked on the landing page |
| C35 | How a priced finished product type is paid for at harvest | Nothing in the MVP. Blocks the second product release, and shapes Block 6 now — the finalisation has to be built so a charge can be added to it without reopening ownership finality |
| C34 | May a sharing member become a full member, on the same account | Nothing yet. Cheap while sharing members are few, unpleasant once they are not — the person is refused at sign-up by their own record and their allowance is already spent |
| — | ~~**The leaf-rating floor.**~~ **Closed.** A rating floors at 0.1 and a plant under 0.5 cannot be swapped. Pricing sits around R1,000, so a sub-R250 price is unexpected rather than impossible — the rule makes the unexpected case unswappable instead of equivalent to everything | Answered in `swap-zone.md`; built in Block 3 |

**C7 has come off this list.** It was the only item that could not be answered inside the business,
and it is now decided as residual risk: the swap model is in use by other clubs and defendable, and a
sharing member's plants consume their own statutory allowance. A legal opinion is still worth having,
but its brief is narrow — the proxy leg and the physical location of the plants, R-C7.1 and R-C7.2 —
and it blocks nothing.

**C9 has come off this list and left one item behind.** Payment in full at order, held by the club
until delivery and released to the cultivator then, with substitution as the crop-failure rule. What
remains is **C9.1**, the release event, which is an integration question rather than a product one and
holds up settlement rather than the checkout.

**C15 and C16 move up in its place.** Both were refinements of the swap zone while the four-plant
number was a convention. C7 made it a statutory ceiling attaching to a named adult, so the holding
check is now a prerequisite of the block rather than a detail inside it.

**C10 is narrowed and has shed a build item.** The money map is settled for the club: F2C collects the
membership fee through Payfast and keeps 40%, the Cultivators Collective collects everything else and
pays F2C 15%, and the split ratios themselves are out of scope for the application. What that exposes
is **C10.1** — the platform has one gateway, billing one thing, into the wrong entity's account for
every transaction except the subscription. That is work, not a decision waiting on the business, and
it sits in Block A ahead of both checkouts.

### Decided, and recorded here because they restructured the plan

| # | Decision | What it changed |
| --- | --- | --- |
| C6 | A sharing member is a **real person who does not transact** — decided, acted on as a placeholder, then **reversed** | Block 0.5 and Block E. Registration takes the identity number, the age rule and the POPIA attestation back, and the erasure route with them. A read-only login is specified and deferred. The code still implements the superseded reading |
| C7 | The swap model is **defendable** — residual risk, not a gate | Ungates Block 10 → Block E. Makes the four-plant allowance a statutory ceiling, which promotes C15 and C16 to prerequisites |
| C8 | **Nothing is payable at harvest.** Courier sits inside the price paid at order and is remitted to Pargo at settlement | Removes a checkout from Block 6 → Block C. Makes the harvest confirmation the point where ownership becomes final, which closes the swap window and constrains Block 10. Adds a third leg to C10's settlement split, and opens C35 |
| C9 | **Payment in full at order, held by the club until delivery**, then released to the cultivator, who **guarantees delivery**. A failed crop is substituted; refunded only where no equivalent plant exists | Fixes the Block 5 → Block A checkout as a single full-price payment and rules out a receivables ledger. Puts a held / released state on the order, and answers C10's "when does a cultivator earn". Narrows C11 to refunds after release. Leaves C9.1 open, and creates copy that has to appear in the intros, the sign-up journey and the club documents |
| C33 | The **cultivator transacts as proxy**; the sharing member views only | The named grey area. Makes "the role must be droppable" a build constraint on the swap zone, not a note |
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

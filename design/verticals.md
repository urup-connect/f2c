# One platform, two storefronts

## What this document is

**Planned, not built.** Like [`plan.md`](plan.md), [`todo.md`](todo.md) and
[`conflict.md`](conflict.md), this document is an exception to the rule in [`README.md`](README.md)
that the design set describes the system as it stands today. Nothing described here exists.

The club — Cultivators Collective, cannabis, members only — is what this repository has been built
against. A second storefront is now in scope: a public produce market where farmers list what they
grow and anybody with an account can buy it, searching on price, availability and the farmer's
rating.

This document says what the two storefronts share, what they do not, and what has to change in the
code before either can be built without the other paying for it.

**It replaces the reading of C3 that treated the six excluded produce categories as six future
sites.** There is one market carrying many categories, not one site per category. What follows is
not multi-tenancy.

---

## 1. The two storefronts

| | The club | The market |
| --- | --- | --- |
| Who may buy | Paid-up members, age-verified, RSA ID number on file | Anyone with an account |
| What is sold | A living plant, individually serialised, with a grow service attached | Produce by quantity — a kilogram, a bunch, a punnet, a dozen |
| Who sells | Cultivator organisations | Farming organisations |
| Revenue | Membership subscription, plus a split on each plant order | A split on each produce order |
| After the sale | The member owns the plant while a cultivator grows it, may swap it, and takes delivery of a finished product at harvest | It is picked, packed and delivered |
| Regulatory load | Statutory plant ceiling, copy compliance, age gate, a legal opinion still outstanding on the swap zone — **C7** | Ordinary consumer trade. VAT treatment differs by line: most fresh produce is zero-rated, a club subscription is not |
| Status | Partly built — see `plan.md` section 2 | Nothing built |

The categories the market carries are the ones C3 recorded and planned for nothing: biltong, fruit,
vegetables, nuts, dried goods, honey, and more besides. They are rows in a catalogue, not
deployments.

---

## 2. The axis that separates them

One sentence, because everything below follows from it:

> The club sells a **serialised, individually-owned, non-fungible asset with a service attached**.
> The market sells **fungible perishable stock by quantity**.

Every genuine difference between the two lies on that axis. A plant has a serial, an owner, an
ownership history, a grow price, a harvest date and a legal ceiling on how many one person may hold.
A crate of carrots has none of those, and has instead a unit of measure, a quantity that decrements,
a shelf life and a delivery window.

Everything off that axis — who you are, who grew it, how you found it, what you paid, how you rated
them, how you were told — is the same product built twice if it is not built once.

---

## 3. What is shared

| Shared concern | Where it is today |
| --- | --- |
| Identity, passkeys, emailed codes, sessions, profile, avatar | Built — `app/core/accounts`, `app/core/authn` |
| Documents, immutable revisions, and the agreements given to them | Built — `app/core/documents`. The **machinery** is shared; no document ever is. See section 6 |
| Producer organisation: the farm as a record, its appointed staff, collection address, bank details, published profile | `app/commerce/producers.CultivatorProfile` exists as a thin profile. Block 2 was to grow it into the organisation |
| Curated catalogue item, platform-owned — a strain, a produce type | `app/club/strains.Strain` is the club's. The market needs the same pattern, not the same table |
| Listing: producer against catalogue item, with price, image, description, status and availability | `app/club/strains.CultivatorStrainListing` already **is** this shape |
| Search and facets over listings — price, availability, producer rating | Not built. Block 5 needs it for the club; the market needs the same thing |
| Cart, order, order line, checkout | Not built. Needed identically by both |
| Payfast: signature, hosted checkout, signed notification | Built — `app/core/payments/gateway.py`, reusable unchanged |
| Producer settlement and payouts | Not built, and unspecified — **C10** |
| Reviews and star ratings over producers and over listings | Not built. The market's "farmer rating" is the club's cultivator rating |
| Notifications | Not built. Block 8 |
| Support and escalation | Not built. Block 11 |
| Permission catalogue and the resolving backend | Built — `app/core/accounts/roles.py`, `app/core/accounts/backends.py`. The machinery survives; the role column does not. See section 5 |
| Administrative front end | Not built. **Two of them** — a club administration area and a market one, both in Next.js, over one shared shell. The UC operator tier is not among them; see section 6 |
| UI kit, brand system, form components, auth screens, profile, checkout | Built — `frontend/club/components`, `frontend/club/lib` |

The list is long, and that is the finding. Most of what remains unbuilt in `plan.md` is shared
between the two storefronts. Built once it serves both; built inside the club it gets rewritten.

---

## 4. What is not shared

**The club alone.** Strain attributes — cannabinoid content, terpene profile, flowering weeks;
`Plant`; `Batch`; the serial; `PlantOwnership`; grow price; the leaf rating; the swap zone; harvest
and the finished product; the four-flowering-plant ceiling; the membership subscription; the age
gate; and the copy-compliance rules in `frontend/club/lib/copy-compliance.ts`.

**The market alone.** Unit of measure — kilogram, bunch, punnet, each; a stock quantity that
decrements on order and cannot oversell; perishability, lead time and harvest-window availability;
delivery and collection zones with their fees; and per-line VAT treatment, since zero-rated produce
and a standard-rated subscription cannot share one tax assumption.

---

## 5. The collision: `User` is both an identity and a club membership

This is the change that has to happen before either storefront can be built, and it is not
avoidable by sequencing.

**A produce customer cannot sign in.** `User.status` carries `PENDING_PAYMENT`, and `is_active` is
derived from `status` and held to it by a database check constraint — `app/core/accounts/models.py:378`
and the `user_is_active_matches_status` constraint at `app/core/accounts/models.py:481`. Exactly one
status value grants access, and reaching it means paying for a club membership. Someone buying
carrots has no membership to pay for.

**A farmer who is also a member is two things in a one-thing column.** `User.role`
(`app/core/accounts/models.py:362`) is a single value under its own check constraint. On the market one
person may plausibly be a customer, a producer's appointed staff member and a club member at once.
C2 already adds a fifth value to this column; the market makes the column itself the wrong shape.

**The RSA ID number is on the wrong record.** `id_number_encrypted` and `id_number_hash` sit on
`User` because club membership requires them. Asking a produce customer for an identity number
because the account model happens to hold one is precisely what POPIA's minimisation principle
refuses.

The build already anticipated the first of these. From the `UserStatus` docstring at
`app/core/accounts/models.py:70`:

> `PENDING_PAYMENT` is a status value rather than a row in a membership table on purpose, *for
> now* … A `Membership` model with a subscription period and a gateway reference arrives with the
> payment gateway; until there is a payment to record, a second table would hold one fact that this
> field already holds.

That reasoning was right when the club was the whole platform. The second storefront is the event
it was waiting for.

**One behaviour change falls out of this, and it is not cosmetic.** `PENDING_PAYMENT` gated the
account, so an unpaid registrant could not sign in at all. It now gates the membership, so they sign
in and land on a screen asking them to pay. That is forced rather than chosen — a produce customer
cannot be held behind a club payment — but it changes what the club does, not only how it is
modelled, and the payment-link flow in `payments/services.py` is written against the old behaviour.

The pay-now redirect is therefore a requirement rather than a nicety: a member whose membership is
`PENDING_PAYMENT` or `LAPSED` signs in successfully and every club destination sends them to the
payment screen. It is the club layout's job, not the API's — the session carries `membership_status`
beside `status`, which is what lets it decide.

Two things fall out of it that were not obvious until it was built.

**The gate has to refuse a checkout as often as it offers one.** A membership awaiting the club's
verification, or a placeholder, is not settled by money. Sending either to a payment screen invites
a payment for something the payer does not thereby get, so both go to the front door instead. The
rule lives in one pure function, `frontend/club/lib/club-membership.ts`, and `ACTIVATABLE_STATUSES` in
`payments/services.py` enforces the same line on the API — a payment gate with two copies is how
somebody eventually reaches the club without paying.

**There had to be a second way into payment.** `/pay` reads its token from an `httpOnly` cookie the
sign-up action sets, which a member signing in a week later does not have; the redirect would have
delivered them to "your payment link is unavailable". `GET /payments/me/checkout` is the answer —
session-authenticated, about `request.user` alone, taking no member identifier. Before the split
there was no second way in because there was no second way to arrive: an unpaid member could not
sign in at all.

**And one open question was closed while this was being built. C6: a sharing member is a
placeholder, not a person.** The old `UserStatus.SHARING` became `NON_AUTHENTICATING`, named for
the fact the authentication stack needs — this identity holds records and signs in nobody — rather
than for the club concept on top of it. The POPIA consent attestation went out of the schema
entirely, because a placeholder consents to nothing.

That deletion was taken now rather than with the swap zone for one reason: C6's own recommendation
is that unwinding "real people" after launch means a migration that deletes stored identity numbers,
and Block 0.5 is the one moment when there is no data to migrate. **C7 is changed by this and not
resolved** — the club now holds the stock itself rather than allocating it to named adults, which is
a different legal question, not the absence of one.

---

## 6. The target model

### Core identity

| Model | Holds |
| --- | --- |
| `User` | Email, name, avatar, credentials, an account state of *active*, *suspended* or *erased*, and `is_staff` — nothing about membership, nothing about role |
| `ClubMembership` (user and club) | A **paying member** of the club: member status including *pending payment*, the subscription, the nickname, the document consents, and whether age and identity have been verified |
| `StorefrontStaff` (user and storefront) | An **administrator** of the club or of the market. Not a member, and pays nothing |
| `ProducerMembership` (user and producer) | Appointed staff of a producer, primary or otherwise, with full or limited rights |

**A market customer is a `User` with no rows in any of the other three.** Buying produce requires an
account and nothing else — no membership, no subscription, no identity number, no consent record.
That is the whole reason the market can ship first.

**A club administrator is `StorefrontStaff`, not `ClubMembership`.** Today an administrator is
`role='admin'` on a `User` whose status must be `ACTIVE`, which under the split would have meant
issuing them a membership they never pay for. Administration and membership are different
relationships and get different tables. The market's administrator is the same table with a
different storefront.

`nickname` moves to `ClubMembership`. It is a member-facing handle inside the club, not a property
of a person, and a produce customer has a name and needs no pseudonym. The membership-scoped
uniqueness this implies replaces the global `nickname_key` index at `app/core/accounts/models.py:296`.

**`id_number_encrypted` and `id_number_hash` stay on `User`, and become optional.** The alternative
— moving them to `ClubMembership` alongside the requirement that produces them — was considered and
rejected. Identity verification is plausibly platform-level rather than club-level: paying a farmer
out means knowing who they are, and any future age-restricted category asks the same question the
club asks. Moving two encrypted columns and a blind index is a migration with a real failure mode
and no upside if a second caller appears. What moves is the *requirement*, which becomes a rule on
`ClubMembership` rather than a column on `User`.

**`User.role` is removed, and so is `uc_admin`.** The catalogue in `roles.py` and the resolving
backend in `backends.py` survive unchanged in shape; what changes is where a role is read from. An
administrator role is read from `StorefrontStaff`, a member role from `ClubMembership`, a producer
role from `ProducerMembership`. This is also most of the answer to **C13**: object-level rules stop
being a retrofit once "their own" has a membership row to mean.

**The UC operator tier is `is_staff`, not a role.** C2 decided there are two administrative tiers
and that stands, but the second one is not a value in a catalogue and has no Next.js surface. Money,
administrator accounts, refunds, subscription cancellation and escalations are done in the Django
admin, gated by `is_staff` exactly as Django gates it already. This is C5 taken to its conclusion —
that decision already kept the Django admin as the operator's tool — and it is a simplification: the
UC-tier actions never enter the permission catalogue, no endpoint has to compare tiers, and
`createsuperuser` needs no role argument. Recorded as **C29**.

### Producer and commerce

| Model | Holds |
| --- | --- |
| `Producer` | The organisation. Trading name, public description, image, collection address, bank details, published state. `CultivatorProfile` becomes this |
| `ProducerCategory` | Which storefronts this producer sells into. A farm may do both |
| `Listing` | Producer against catalogue item: price, image, description, status, availability. Which storefront a listing appears in is a property of what it lists, not a tenancy column |
| `Order`, `OrderLine` | A line points at a listing and carries a quantity and a unit price. Shared |
| `PaymentIntent` | Subscription or order. `payments/gateway.py` sits beneath both unchanged; `payments/services.py` splits |
| `Review`, `ProducerRating` | Over listings and over producers. One implementation |

### Documents

**No document is ever shared between the two storefronts.** Not the privacy notice, not the terms.
`storefront` is therefore a non-null foreign key on the document, and `slug` becomes unique per
storefront rather than globally — a plain two-column unique index, so nothing about the portability
rules in `migrations.md` section 2 applies to it.

*The rejected alternative was a nullable `storefront` meaning "both".* It would have let two
platform-wide documents share a slug, because nulls are distinct under a unique index on every
backend this project runs on — the exact failure `backend.md` section 8.2 exists to prevent. With
nothing shared, the question does not arise.

There are now four kinds of document, and today's single `required_at_signup` boolean cannot
describe them:

| Example | Who it concerns | Agreement | Readable without an account |
| --- | --- | --- | --- |
| Store privacy notice, terms, data policy | Anyone | None | Yes |
| Club rules, annexures, constitution | Members | At registration | Yes — sign-up reads them before an account exists |
| Store customer terms, if they are wanted | Customers | At registration | Yes |
| Farmer agreement | Producers | At onboarding | No |

So the boolean becomes two fields on `Document` — the model `ClubDocument` is renamed to:

- **`audience`** — `public`, `customer` or `producer`. Who the document concerns.
- **`agreement`** — `none`, `at_registration` or `at_onboarding`. When agreement is collected.
  `at_checkout` is a value to add if store terms turn out to be accepted at first order rather than
  at registration; it is not a redesign, so it is not added speculatively.

**Readability derives from audience** rather than carrying a flag of its own. `public` and
`customer` documents are served unauthenticated, because sign-up already has to read them before
an account exists — that is why `/documents/current` is `auth=None` today. `producer` documents are
not.

**Retirement keeps a field of its own — `retired_at`.** Today `required_at_signup=False` takes a
document out of sign-up without deleting it or its consent history, and the model comments that this
is the only safe way to retire one. Under the enum, setting `agreement=none` would retire a document
*and* publish it as a public readable page. Those are two different intentions and they get two
different fields.

#### Endpoints

All four scoped to the requesting storefront. The unauthenticated pair cannot read it from a
session, so it comes from the host — the same resolution the passkey RP ID needs, section 8.

| Endpoint | Auth | Serves |
| --- | --- | --- |
| `GET /documents/published` | None | **New.** Every document with `audience in (public, customer)` and a published revision. The store's legal pages |
| `GET /documents/current` | None | Today's endpoint, narrowed to `agreement=at_registration`. What the sign-up form ticks |
| `GET /documents/outstanding` | Session | Today's endpoint, extended to take an audience so producer onboarding can ask for its own set |
| `POST /documents/accept` | Session | Unchanged in shape |

#### A farmer agreement is not a `DocumentConsent`

`DocumentConsent.user` records **a person agreeing to a text**. A farmer agreement is a contract with
**the organisation**: one person may run two farms, and a farm's agreement has to stand when its
contact person moves on. Recorded against the user alone, the agreement evaporates with that
person's association.

```
ProducerAgreement
  producer      FK -> Producer
  version       FK -> DocumentVersion   (PROTECT, as DocumentConsent does)
  signed_by     FK -> User              who ticked, on the organisation's behalf
  accepted_at, file_sha256, consent_text_sha256
  unique (producer, version)
```

Same immutability and the same two digests copied from the revision; a different subject and a
different uniqueness rule.

*The rejected alternative was a nullable `producer` foreign key on `DocumentConsent`.* It is fewer
lines and it loses the structural guarantee: nothing in the database could refuse a producer
agreement recorded with no producer, because a check constraint cannot reach across tables to read
the document's audience. This project's convention is to make that kind of rule a fact about the
database, so the second table wins and the duplicated digest logic is the price.

#### Unchanged

The three-model split, published-revision immutability, `effective_from` dating,
`requires_reacceptance`, the two digests copied onto every agreement, append-only consents, and
`DocumentConsent` itself. `DocumentConsent.user` points at `User`, which is the right level after
C27: a person agreed to a text, and which storefront it belonged to arrives through the version.

The storage path gains the storefront —
`documents/<storefront>/<slug>/<label>/<file>` — because once both storefronts have a `terms` at
`v1` the present path collides, and a revision's address never changing is the whole point of it.

### The verticals

The club keeps `Strain`, `CultivatorStrainListing`, `Plant`, `Batch`, `PlantOwnership`,
`SerialCounter` and the swap zone. The market gets produce types, units of measure, stock quantity
and delivery. Neither knows about the other, and both sit on the commerce spine.

---

## 7. Layout

Both halves of this are **built**. What follows describes the shape as it stands, and names what is
deliberately still empty.

### Django

```
app/core/       accounts  authn  common  storefronts  documents  payments
app/commerce/   producers
app/club/       membership  strains  finished_product  plant
app/market/     — nothing yet
```

`core` is the platform spine and knows nothing about what is sold. `commerce` is what both
storefronts sell through. `club` is the cannabis vertical, and `market` is the produce vertical,
which has no apps because it has no features yet.

The eventual shape adds `notifications` and `support` to core; `catalogue`, `listings`, `orders`,
`reviews`, `settlement` and `search` to commerce; `batches`, `ownership` and `swap` to the club; and
the whole of the market. The four packages exist now so each of those lands in a decided place
rather than wherever the flat layout suggested.

**`label` is set explicitly on every `AppConfig`** — `label = 'accounts'` beside
`name = 'app.core.accounts'` — so the tables stay flat. Without it the fresh initial migration would
produce `core_accounts_user`, and `AUTH_USER_MODEL` would have had to move with it. No table changed
name and no migration dependency moved: the grouping was a package move and nothing more.

One app was renamed rather than only moved: `cultivators` → `commerce/producers`. That was the point
of the exercise — a farmer growing carrots is the same record as a cultivator growing cannabis, and
the old name filed the shared thing under the club's word for it.

The boundary earns its keep by what it forbids. `club/plant` importing `club/strains` is ordinary;
`commerce/producers` importing `club/strains` would be the commerce spine learning about cannabis,
and the directory is what makes that visible in a diff.

The project package `cultivatorscollective/` is now **`f2c/`**. It is the platform, not one of its
storefronts.

### Frontend

```
frontend/
  club/        the club application — moved here
  market/      the market application — built, on port 3001
  packages/*   shared code. Empty, deliberately
```

npm workspaces, declared in `frontend/package.json`. One lockfile and one hoisted `node_modules` for
both applications; each application keeps its own `package.json`, Next config and test setup.

**`packages/` is empty, and that is a decision rather than an unfinished step.** There is one
application, so nothing is *shared* — extracting a UI kit, an API client and a config reader now
would mean drawing three boundaries with no second consumer to test them against, which is how a
shared package ends up shaped like its only caller. It is the same reasoning section 11 gives for
refusing a generic `Product` model.

The candidates are known and will come out when `market/` needs them: the UI kit, the API client,
and the per-application environment reading.

**Update: `market/` now exists, and `packages/` is still empty.** The store storefront is built —
front door, legal pages, sign-in, sign-up, and the signed-in account area; `design/frontend.md`
section 11 describes it. Writing it against the club sorted the candidates into three kinds rather
than one, which is what a second consumer was for:

- Platform rules, copied verbatim with their tests — `person-name`, `sa-mobile-number`,
  `email-address`, `env`. Unambiguously `packages/` material.
- Same shape, different content — the API client, the sign-in form, the passkey card, the form
  primitives. Extractable, but two of them already differ in ways that would become props on a
  shared component: the club routes to one of three homes and the store to one account area, and the
  club's text field carries a notice slot the store has no use for.
- Looks shared and is not — the environment reading. The club requires `CDN_BASE_URL` and the store
  must not, so a shared reader would take a schema argument and be two readers wearing one name.

The extraction is therefore a pass of its own, with the duplicated test suites as the tripwire in the
meantime. `frontend/README.md` carries the same note beside the code; it is risk 11.3 in
`design/frontend.md`.

**Why move the club into a subdirectory before the market exists.** Until this pass, `frontend/`
*was* the club, which meant every new file landed inside that assumption without anybody choosing
it. Moving while there was exactly one application to move cost a directory rename; moving later
would have cost the same rename plus whatever had accumulated against the old shape.

**What must not be shared**, whatever else does: `club/lib/copy-compliance.ts`. It forbids currency,
retail voice and clinical claims in member-facing copy, and the market is held to none of it — a
market that could not name a price would not be a market.

**Each application carries its own administration area.** `frontend/club` administers members,
producers, strains and stock; `frontend/market` will administer customers, farmers, produce types
and orders. Neither carries a UC tier — see section 6 and C29.

The store's is not built, and one finding from building the rest of it belongs here rather than in the
frontend document: **a market customer holds no `platform.*` codename at all.** `permissions_for`
grants from a club membership, a storefront appointment or a producer appointment, and an ordinary
shopper has no row in any of the three — which is correct, and which means the store's account menu
cannot be derived from permissions the way the club's is. It is a fixed list of two *your own*
destinations, whose endpoints take no account identifier and therefore make no authority decision.
The administration area is the first store screen that *is* such a decision, and it needs a codename
in the catalogue before it can be gated on one.

---

## 8. Domains and sign-in

The two storefronts sit on separate registrable domains. **C30 fixes which is which**, and the API
answers on a subdomain of each:

| Host | Serves |
| --- | --- |
| `f2c.co.za` | The produce market — `frontend/market` |
| `backend.f2c.co.za` | The API, for the market |
| `f2c-cannabis.co.za` | The club, landing page and age gate included — `frontend/club` |
| `backend.f2c-cannabis.co.za` | The API, for the club |

One Django deployment answers on both `backend.*` names. Two consequences follow from the split
domains and neither is optional.

**Passkeys do not cross a registrable domain.** A credential enrolled on the club's domain cannot
be presented on the market's. Each storefront enrols its own passkey; the emailed code works
anywhere. `rp_id()` at `app/core/authn/webauthn.py:37` takes the request's storefront and reads
`WEBAUTHN_RP_IDS` (`f2c/settings.py:549`), falling back to the single `WEBAUTHN_RP_ID` for anything
unlisted — so the value follows the storefront rather than the deployment. Under C30 the mapping is
`club=f2c-cannabis.co.za,market=f2c.co.za`: the domain each **frontend** is served from, not the
API's.

**Sessions do not cross either.** Give each storefront its own API hostname so `SameSite=Lax` and
the present cookie posture survive untouched. One identity, two sessions, two passkeys. That is what
the `backend.*` pairing above buys: a club frontend calling the market's API host would be
cross-site, needing `SameSite=None`, and Safari's ITP and Chrome's third-party cookie posture would
drop the cookie regardless. It also means `SESSION_COOKIE_DOMAIN` stays unset — one deployment on
two registrable domains cannot name a single cookie domain.

**Nor does outbound email.** Separate domains mean separate mailbox providers, and a provider will
refuse a `From` it does not own — so `MAILERS` holds one SMTP mailer per storefront, keyed by the
storefront code, built from `EMAIL_CC_*` and `EMAIL_F2C_*`. `app/core/storefronts/mail.py` is the
one place that resolves a storefront into a server, a sender and the name in the subject and
signature, because those three have to agree: a sign-in code from the store's provider signed
"Cultivators Collective" is indistinguishable from a phishing attempt, and a one-time code is
exactly the thing a member is taught to distrust on that basis.

Which storefront is decided by the **host** Django was reached on — `backend.f2c.co.za` or
`backend.f2c-cannabis.co.za`, never the frontend's name, which Django never sees — through
`storefront_for_request`, the same signal `rp_id()` reads, and for the same reason. It cannot be
decided by what the member belongs to: the
address may have no account at all, and a member of both signing in at the store should be answered
by the store. Note what this does *not* change — the code itself is still not storefront-scoped, so
one issued at the club is verifiable at the market. Only the envelope moved.

There is deliberately no fallback to the other storefront's server. It would send successfully,
which is the failure mode worth guarding: nothing looks wrong, and a storefront's members are
receiving mail from a provider with no relationship to them. A blank host or sender refuses startup
outside `DEBUG`, and `app/core/storefronts/checks.py` refuses a storefront added to the enum without
a mailer of its own.

A single sign-on across both — one credential, one session, cross-sell in both directions — needs a
central authentication origin. It is worth costing and it is not being built now. It is recorded
here as **risk 3** so that it stays a decision rather than becoming a discovery.

---

## 9. What this changes in the conflict register

| Entry | Change |
| --- | --- |
| **C3** | Amended. The two hosts stand; the six excluded categories become a catalogue on one market rather than six planned-for-nothing sites |
| **C10** | Escalated. Producer settlement was a Block 12 concern and a launch blocker for cultivators. The market pays a farmer on every order from the first day it trades, so it is now a near-term blocker for the earlier of the two storefronts |
| **C13** | Largely dissolved. Object-level rules become membership lookups once `ProducerMembership` exists |
| **C2** | Narrowed. The two administrator tiers stand, but as platform roles on `User`; the club and producer roles leave the column |
| **C26** | New — the platform serves two storefronts, not one club |
| **C27** | New — `User` conflates identity with club membership |
| **C28** | New — one role per account cannot express one person's three relationships |
| **C29** | New — the UC tier is `is_staff` in the Django admin, not a role in the catalogue |
| **C30** | New — `f2c.co.za` is the market and `f2c-cannabis.co.za` is the club; the API answers on `backend.` of each. Closes the `SITE_URL` split, which the two-application layout had already done |
| **C5** | Reinforced. The Django admin is not merely retained as the operator's tool, it *is* the operator's tier |

---

## 10. Sequencing

| | Block | Why here |
| --- | --- | --- |
| 1 | **Block 0** — production blockers | Unchanged. Nothing is demonstrable without an email provider |
| 2 | **Block 0.5** — identity decomposition | `User`, `ClubMembership`, `StorefrontStaff` and `ProducerMembership`; the role column and `uc_admin` retired; `CultivatorProfile` generalised to `Producer`; migrations regenerated from scratch. One to two weeks, and everything else waits on it |
| 3 | **Commerce spine** — catalogue, listing, search, cart, order, payment intent, review, settlement | Built once, serving both storefronts. Absorbs most of the old Blocks 1, 4, 5 and 7, and pulls C10 forward |
| 4 | **Market** — produce types, units, stock, delivery | The shorter of the two verticals |
| 5 | **Club** — plant, batch, ownership, harvest, fulfilment | The old Blocks 3 and 6 |
| 6 | Notifications, administration portal, support | The old Blocks 8, 9 and 11 |
| 7 | Swap zone, plant subscriptions, reporting | The old Blocks 10 and 12. Still gated on **C7** |

**The market is the shorter path to a transacting platform.** No ownership chain, no swap zone, no
statutory ceiling, no age gate, no copy-compliance corpus and no outstanding legal opinion. It
exercises the same spine the club needs and carries a fraction of the regulatory load. If revenue
ahead of legal clearance is worth anything, it is the market that delivers it — and the club's own
build is not delayed by the choice, because steps 2 and 3 are the club's work too.

---

## 11. What is deliberately not being done

The rejected half is usually the more useful one, so it is recorded rather than omitted.

- **No generic `Product` model.** `Strain` carries cannabinoid content, terpene profile and
  flowering weeks; a carrot has none of them and has a shelf life instead. Generalising a domain
  that has not been specified is the expensive mistake, and the shared abstraction that actually
  earns its place is the **listing**, not the item it lists.
- **No `Site` foreign key on every row.** An earlier reading of this problem had seven tenanted
  sites and a tenancy column throughout. With two storefronts and one shared producer population a
  tenancy column would be a fiction maintained by hand: which storefront a listing appears in is
  already implied by what it lists.
- **No single sign-on, yet.** See section 8 and risk 3.
- **No second database, no second Django deployment, no second repository.** One of each.
- **No market work before the identity split.** Building it on today's `User` means building the
  split twice.
- **No UC administration in Next.js.** A third administrative front end, for one operator, to
  reproduce what `django.contrib.admin` already does — on the one surface whose entire audience is a
  handful of trusted staff. See C29.
- **No preserved migration history.** The development database is dropped and the migrations
  cleared. That is a decision taken while it is still free, and it stops being available the day the
  club has members beyond the founding set.

---

## 12. Risks

1. **The migration history is being discarded, and the window for that closes.** There is no data
   migration and no constraint to lift, because the development database is dropped and every
   `migrations/` folder is cleared and regenerated. What it costs is the test support data — five
   `app/*/tests/support.py` builders and two modules under `frontend/club/test-support/` — which has to
   be rewritten against the new models. *Accepted, and the reason to move now: the same change
   against live club members is a data migration over encrypted columns that cannot be re-run.*

   **Done.** Seventeen migrations cleared and the database dropped. What they encoded beyond the
   models — two data seeds, one open decision about the auth groups, and the conventions every
   future migration here follows — is recorded in [`migrations.md`](migrations.md).
2. **Retiring `User.role` touches every permission test.** `roles.py`, `backends.py` and their
   suites are among the better-tested parts of the build, and all of them assume a column. The
   catalogue survives; the resolution path does not, and neither does `uc_admin`. *Accepted: those
   tests are the reason this is safe to do at all — but they are also the bulk of the work, so cost
   the block by the test suite rather than by the models.*
3. **Separate registrable domains foreclose shared passkeys.** A person on both storefronts enrols
   twice and signs in twice. If cross-sell turns out to matter commercially, a central
   authentication origin has to be retrofitted into a system with two live session models.
   *Open — see section 8.*
4. **Settlement is still unspecified — C10.** The market cannot launch without paying farmers, and
   nothing in the brief says how. This is now on the critical path rather than in Block 12.
5. **Two storefronts, one team.** The spine is genuinely shared, but the verticals are not: the
   market's delivery, stock and VAT work has no overlap with the club's ownership and harvest work.
   The saving is in steps 2 and 3, not in steps 4 and 5.
6. **The club's copy-compliance rules must not leak into the market.** They are a cannabis
   constraint, and a shared component library carrying them by default would forbid the market from
   naming a price. *Mitigation: the rules live in the application, not in the package — see
   section 7.*

# Consolidated build list

Every outstanding item from [`twp-tasks/`](twp-tasks/), the drawio stories and the design set, in one
list, in the order it can be built.

Sequencing and reasoning are in [`plan.md`](plan.md). Disagreements between the brief and the build
are in [`conflict.md`](conflict.md) and are cited by number.

## Status marks

| Mark | Meaning |
| --- | --- |
| `[x]` | Built, tested, reachable |
| `[~]` | Partly built — what is missing is stated on the line |
| `[ ]` | Not built |
| `[!]` | Blocked on an open decision in `conflict.md` |

Source citations: `stock-upload` means `twp-tasks/cultivator-stock-upload.md`, `member-roles` means
`twp-tasks/member-roles.md`, and so on. `drawio` means one of the story diagrams in the same folder.

---

## Block 0 — Production blockers

Nothing below this block can be demonstrated to anybody until these are done. **A member cannot sign
in on a deployed environment today.**

- [ ] Configure a real email provider. `MAILERS` is the console backend, so sign-in codes and the
      duplicate-registration payment link reach nobody — P1
- [ ] Schedule `manage.py lapse_memberships`. Until something runs it, an unpaid membership keeps
      access indefinitely — P2
- [ ] Shared cache backend. `LocMemCache` makes every rate limit per worker, including the one
      bounding outbound email — P3
- [ ] Document backup and rotation for `DJANGO_FIELD_ENCRYPTION_KEY`. Losing it destroys every
      stored identity number with no recovery path — P4
- [ ] Restrict `POST /api/auth/login` to `is_staff`. Unreachable today only because members are
      created with an unusable password — P5
- [ ] Move the API address to runtime configuration. `NEXT_PUBLIC_DJANGO_API_URL` is baked into the
      bundle at build time, so a promoted artefact carries the wrong address — P6
- [ ] Choose a hosting target and provision PostgreSQL. `uuid7` keys were chosen anticipating it
- [ ] Run `manage.py check --deploy` and clear it
- [ ] Fix `frontend/app/api/nickname/availability/route.test.ts` — it asserts a random hex string
      does not contain `500`, `503`, `429` or `422`, all valid hex, so it fails about one run in
      thirty — C25
- [x] Clear the stale-document drift: `frontend.md` §9 and `roles-and-permissions.md` §13 both say
      profile editing is unbuilt, and it is built — C21. Close `backend.md` risk 12, which says the
      project is not under version control — C23

### Two domains — C3

- [ ] Split `SITE_URL` into a public host and a member-zone host
- [ ] Apply the `robots` and canonical rules per host rather than per environment
      (`features/landing.md` §5)
- [ ] Deploy and index `f2c.co.za` (public) and `f2c-cannabis.co.za` (member zone) separately

### Public landing page

- [x] Landing page with compliance-governed copy — `features/landing.md`
- [x] Age gate before sign-up
- [x] Sign-up call to action
- [x] Intro blurb and introduction video — `drawio`, member story
- [ ] Platform information section, including a snapshot of plants available. Needs Block 3
- [x] Terms, conditions and club rules on the public page
- [!] Display the membership fee. The copy-compliance patterns refuse currency and retail voice on
      this page; needs a named exemption rather than a relaxed pattern — **C20**

---

## Block 1 — Catalogue

- [ ] **Strain** model, administrator-curated, platform-wide — `member-roles`
- [ ] Generic strain listing page: strain information and *grow price from* — `member-plant-purchase`
- [ ] **Finished product type** model with price. Pre-rolls and loose to start, both at no cost —
      `product-types`
- [ ] **Cultivator profile**: public description, image, pseudonym — `member-roles`
- [ ] **Cultivator strain listing**: image, description, available finished product types, price,
      minimum yield, short description shown to members — `member-roles`, `member-plant-purchase`
- [!] Decide how the three levels of finished-product-type selection relate — platform catalogue,
      strain listing, individual plant. Three documents put the list in three places — **C18**
- [ ] Administrator screens for strain and product type CRUD. Endpoint work is Block 9; the models
      are here

---

## Block 2 — Cultivator organisation

Resolves **C13** and `roles-and-permissions.md` risk 9. Built after the models it scopes, this is a
retrofit across every endpoint.

- [ ] **Cultivator organisation** model — the farm as a record
- [ ] Primary cultivator flag. Only the primary may appoint staff and register sharing members —
      `member-roles`
- [ ] Appointed staff with full or limited rights — `platform.appoint_cultivator_staff` is in the
      catalogue and cannot be exercised today
- [ ] Collection address on the farm — `drawio`, cultivator story
- [ ] Bank details on the farm — `drawio`. Settlement itself is Block 12, **C10**
- [ ] **Object-level permission rules.** `RoleBackend` refuses object-level questions outright, so
      every "their own" rule in the brief has nothing enforcing it:
  - [ ] A cultivator's own listings, stock and pricing
  - [ ] The sharing members that cultivator registered. `registered_by` exists; nothing checks it
  - [ ] A member's own inventory
  - [ ] Primary versus appointed staff
- [x] Sharing member registration with POPIA attestation — `accounts.services.register_sharing_member`
- [ ] An endpoint for registering a sharing member. The service authorises its own caller, so it is
      already the right shape to put a router in front of. Reachable from the admin and the shell only
- [ ] Sharing member read, update and withdraw — `platform.manage_sharing_members`
- [!] Decide whether an administrator may CRUD sharing members. §3.6 deliberately withholds it; both
      drawio administrator stories ask for it — **C14**

### Two administrator tiers — C2

- [ ] Add `uc_admin` as a fifth role, with the check constraint and catalogue test moved to match
- [ ] Split the administrative catalogue. `refund_transaction`, `cancel_membership` and a new
      `manage_administrators` go to the UC tier alone
- [ ] Change the `createsuperuser` default from club administrator to `uc_admin`
- [ ] Promote the existing administrator accounts by hand. **A data migration cannot guess which
      accounts belong in which tier**
- [ ] Second administration band and an escalation destination in `club-navigation.ts`

---

## Block 3 — The plant

The spine of the product. Nothing in Blocks 4 to 10 can start without it.

### Model — `stock-upload`, `plant-id-numbers`

- [x] Cultivator plant ID, supplied by the cultivator
- [x] Platform-allocated unique serial, used to track ownership changes — `SerialCounter` and
      `allocate_serials`, one allocation per upload. It refuses to recreate a missing counter rather
      than restart a sequence whose numbers are already on certificates
- [x] Optional crop or batch number — a `Batch` record rather than a string, because Block 4 promotes
      by batch and Block 3 disables one, and a string can do neither
- [x] Strain, grow price, planting date, estimated bloom date, estimated harvest date, minimum yield.
      Strain comes through the listing, which *is* the (cultivator, strain) pair, so the two cannot
      disagree
- [x] Available finished product types — inherited from the listing, no per-plant override, per
      **C18**. Reads live; snapshotting it onto the order is a Block 5 question
- [x] Status: preflowering, in bloom, harvested, processed, shipped — `member-roles`. Plus the actual
      harvest date from `harvest.md`, tied to the status by a check constraint
- [x] Derived: cultivator pseudonym, leaf rating, days to bloom, days to harvest. The day counts are
      properties, not columns — a stored one is wrong by one every midnight
- [x] Ownership, and an ownership history that survives every transfer — `Plant.owner` for the reads,
      `PlantOwnership` as the append-only tenure log, both written by `transfer_to` in one transaction

### Capture

- [x] **Excel batch upload against a published template** — `stock-upload`. The template is generated
      per cultivator (`manage.py plant_template`), because the useful half of a template is the
      dropdown of their own listed strains — a generic one has somebody typing strain names from
      memory into a column that refuses what it does not recognise. Loaded with
      `manage.py upload_plants --cultivator ... [--dry-run]`
- [x] **Batch upload validation and an error report a cultivator can act on.** Row numbers as Excel
      shows them, the column heading, the offending value, and the fix. **Nothing is written unless
      every row is valid** — a 500-row upload that loads 480 leaves a cultivator working out which,
      and a second upload that either duplicates or skips
- [x] No cultivator column, though the brief lists "Cultivator ID" as a field. It would let one
      cultivator load stock as another; who is uploading is an argument, not a cell
- [x] Dates must be dates. `03/04/2026` is refused rather than guessed — a planting date wrong by a
      month is a harvest estimate wrong by a month that nobody questions
- [ ] **Individual plant capture.** The same validation against one row, and it belongs with the
      endpoint in Block 9 rather than as a second code path now
- [ ] An endpoint for either. Both run from the command line; staff generate and load on a
      cultivator's behalf until Block 9
- [ ] Stock on hand **export** — `drawio`, cultivator story v1. The read is
      `Plant.objects.available_from(cultivator)`; there is no stock model and
      `design/backend.md` section 3 records why. Import is the upload above
- [ ] Adjust available plants, add and remove — `member-roles`. Withdrawing is built
      (`platform.disable_plant`); adding is the capture work above

### Leaf rating — C4

- [x] Compute as `grow_price / 1000` rounded to the nearest 0.5 — `swap-zone`. Stored rather than a
      property, because Block 10 has to *match* equal values and a `WHERE` clause cannot call a
      property. Derived on write; nothing displays it until Block 10
- [x] Choose the tie-break. **Round half up**, so R1,250 gives 1.5 — conventional, and it favours the
      member offering the plant. Computed in `Decimal` throughout: a float implementation would put
      that case at 1.0 and disagree with the brief on the one value the brief does not cover
- [x] **Do not** wire it to reviews. It is swap value, not reputation. Nothing in `plant` imports or
      touches a rating
- [!] A grow price under R250 rounds to a leaf rating of **0.0**, which has no swap value at all.
      `swap-zone` sets no floor and its cheapest example is R500. Decide before Block 10 relies on it

### Administration

- [x] Disable or remove a plant — `platform.disable_plant`. A `disabled_at` timestamp and a batch
      action, which refuses any plant a member holds: withdrawing stock is taking it off sale, and
      taking a paid-for plant back is a refund, which **C9** has not decided
- [x] Disable or remove a batch — `platform.disable_batch`. Does not withdraw the batch's plants; a
      mis-numbered crop must not void stock a member has bought
- [x] Trace serials and batches — `drawio`, administrator stories. The plant admin searches on both
      identifiers, and the ownership ledger is read-only throughout
- [ ] The permission checks themselves. Nothing calls `platform.disable_plant`; the admin authorises
      on `is_staff` like every other Django admin page — **C13**

---

## Block 4 — Pricing and promotions

All from `price-changes`.

- [ ] Cultivator adjusts prices on unsold inventory
- [ ] Was-price and now-price shown for two weeks after a reduction
- [ ] Promotions scoped by strain, by period, by batch, or by quantity
- [ ] Promotions marked prominently with the saving to the member
- [ ] Members can filter for promotional items when browsing
- [ ] Special offers section — `drawio`, member and cultivator stories

---

## Block 5 — Browse and buy

The journey in `member-plant-purchase` is a specific three-step drill-down, not a product grid.

- [ ] **Step 1 — strains.** Generic listing, general strain information, *grow price from*
- [ ] **Step 2 — cultivators offering that strain.** Price, average star rating, the cultivator's
      short description for that strain, minimum yield, available finished product types
- [ ] **Step 3 — planting and harvest dates**, with a count of plants per date. Individual serials
      are deliberately not shown
- [ ] Member picks a date and a quantity; the system allocates specific serials
- [ ] Cart and checkout
- [ ] Order confirmation and order history

### Filters — `drawio`, member story

- [ ] By strain
- [ ] By cultivator
- [ ] By estimated harvest date
- [ ] By rating
- [ ] By top sales
- [ ] By price
- [ ] Promotions only — Block 4

### Open before this block starts

- [!] When is the grow price paid — in full at order, deposit and balance, or at harvest? The brief
      does not say, and each answer implies a different refund position — **C9**
- [!] What happens when a crop fails. No document in `twp-tasks/` addresses it. Substitution, refund
      and credit are three different products — **C9**

---

## Block 6 — Ownership, harvest and fulfilment

- [ ] Member plant inventory — plants owned, and where each is in its cycle
- [ ] Cultivator converts an estimated harvest date to an actual one — `harvest`
- [ ] Harvest notification to the owner to finalise the transaction — needs Block 8
- [ ] Member chooses the finished product type at harvest — `product-types`
- [ ] **Delivery address model.** Does not exist. Members need to manage several — `drawio`
- [ ] Member confirms the delivery address at harvest
- [!] Courier booking and fee. `harvest` says the member books and pays; `product-types` says nothing
      is due. Recommendation is to fold the courier cost into the grow price — **C8**
- [ ] Plants for processing — confirmed product type and address, awaiting confirmation — `drawio`
- [ ] Ready for collection
- [ ] Delivered, proofs of delivery, delivery tracking, escalations — `drawio`
- [ ] Certificate of ownership: plant IDs, planting date, harvest date, strain, cultivator
      pseudonym — `plant-id-numbers`
- [ ] Packing labels and courier shipping documents — `platform.view_fulfilment_documents`
- [ ] Track and trace an order — `platform.track_orders`
- [ ] Query an order — `platform.query_orders`
- [ ] Upcoming events for a cultivator: batch and serial harvest dates, processing dates, delivery
      dates, late items — `drawio`
- [!] What a cultivator sees of a member on a packing label. Members are concealed behind a nickname,
      and a packing label carries a name and an address. Recommendation: nickname, serials and a
      waybill number, with the club as shipper of record — **C19**

---

## Block 7 — Reviews and ratings

All from `reviews-ratings`. **Not** the leaf rating — C4.

- [ ] Members review and rate product they have received. Five stars
- [ ] Reviews show the member's nickname only
- [ ] Ratings accumulate against the cultivator
- [ ] Ratings accumulate against the individual cultivator-strain offering
- [ ] Average rating shown in the browse journey — Block 5, step 2
- [ ] Cultivator views and responds to reviews — `platform.respond_to_reviews`
- [ ] Administrator sees all reviews — `drawio`
- [ ] Member's own review history
- [ ] Cultivator notes against members, strains, plants and subscriptions —
      `platform.record_notes`

---

## Block 8 — Notifications

Block 6 depends on this: a harvest notification is the only thing that tells a member to finalise.

- [ ] Notification model and in-app notification centre
- [ ] Email delivery — needs the provider from Block 0
- [ ] Harvest finalisation — the one Block 6 cannot work without
- [ ] Order placed, order status changed, delivery
- [ ] Payment received, payment failed
- [ ] Membership activated, renewed, lapsed, cancelled. `payments.md` §9 records that none of these
      is sent today, and `/signup/paid` promises one
- [ ] Swap requested, accepted, rejected — Block 10
- [ ] Support ticket response — Block 11
- [ ] Club communications: updates, promotions, refer a friend — `drawio`, administrator stories

---

## Block 9 — Administration API and portal

**C5.** The brief heads its administrator section "Admin (NextJs)". Today twenty-nine destinations
render as *Not built yet* with no endpoint behind any of them, and administration happens by hand in
the Django admin.

Everything here is split across the two tiers from C2.

### Members

- [ ] View, edit, suspend, reinstate — `platform.disable_user`
- [ ] Recent sign-ups — `drawio`
- [ ] Warnings, suspensions, expulsions — `drawio`
- [ ] Revoke access — `platform.revoke_access`
- [ ] Membership pauses and cancellations — `platform.cancel_membership`

### Cultivators

- [ ] Cultivator CRUD — `platform.manage_cultivators`
- [ ] Cultivator user CRUD, sharing member CRUD, collection addresses — `drawio`, and see C14
- [ ] Hide a cultivator and everything it offers — `platform.hide_cultivator`
- [ ] Warnings, suspensions, expulsions

### Platform

- [ ] Strain catalogue CRUD — `platform.manage_strain_catalogue`
- [ ] Finished product type and price CRUD — `platform.manage_product_types`
- [ ] Club and platform rules. Published through the Django admin by decision; the brief says they
      need no button — `platform.manage_club_rules`
- [ ] All pricing and special offers, platform-wide — `drawio`
- [ ] Member-owned inventory view — `drawio`
- [ ] Subscription orders view — `drawio`
- [ ] Surface outstanding club document re-acceptances. `GET /api/documents/outstanding` exists and
      nothing calls it, so a member owing one is never asked

### The two tiers — C2

- [ ] Escalation queue: club administrator raises, UC administrator receives — `drawio`
- [ ] Administrator CRUD, UC tier only — `platform.manage_administrators`
- [ ] Membership subscription and payment management, UC tier only — `drawio`, UC story

---

## Block 10 — Swap zone

**Gated on C7. Do not start without a legal opinion.**

- [ ] Swap zone listing. **No Rand values anywhere in it** — `swap-zone`
- [ ] Leaf rating displayed on every plant in the zone
- [ ] An explanation of how the leaf rating works — `drawio`, member story
- [ ] Sharing-member stock seeds the zone. Four flowering plants per sharing member —
      `platform.allocate_sharing_member_stock`. `SHARING_MEMBER_PLANT_ALLOCATION` is `4` and is
      enforced nowhere, because there is no plant to count
- [ ] Instant swaps against sharing-member plants
- [ ] Confirmed swaps against member plants — the member story draws this distinction already
- [ ] Members offer their own plants, and withdraw them again —
      `platform.offer_inventory_for_swap`
- [ ] Equivalent leaf-value matching
- [ ] Explicit acknowledgement when a member accepts a lower-valued request and forfeits the
      difference — `swap-zone`
- [ ] Four-flowering-plant holding check, enforced on the write
- [ ] Prompt a member to trade a flowering plant for a pre-flowering one before refusing —
      `stock-holding-limit`
- [ ] Refuse any swap that would leave a member overstocked
- [ ] No swapping after harvest for paying members — `harvest`
- [ ] A sharing member's harvested item may sit in the zone; a member swapping for it locks in and
      receives the harvested plant — `harvest`
- [ ] Swap audit trail, and ownership history through every swap
- [ ] Administrator oversight: manage plants in the zone, handle disputes, moderate listings

### Open before this block starts

- [!] Is a sharing member a real person or a placeholder? The build has committed to real people, and
      unwinding it later means a migration that deletes stored identity numbers — **C6**
- [!] Is the scheme lawful — does allocating four flowering plants consume that person's own
      statutory allowance, where are the plants physically, and is a swap a sale in substance?
      **Legal opinion** — **C7**
- [!] Does a harvested plant count toward the four? `harvest` permits a swap the holding rule might
      refuse. Recommendation: count only preflowering and in bloom — **C16**
- [!] Equal-value matching versus maturity. Leaf rating derives from grow price alone, so a plant
      three weeks from harvest and a seedling of the same price trade at par, and everyone wants the
      mature side. Recommendation: require confirmation for mature stock — **C17**
- [!] Household and dried-weight limits are not modelled. Recommendation: enforce four flowering
      plants, record the other two as accepted with a stated reason, and put them in the club rules
      rather than pretending to enforce them — **C15**

---

## Block 11 — Support

- [ ] Support tickets, raised by members and by cultivators —
      `platform.submit_support_request`
- [ ] Ticket status tracking and responses
- [ ] Contact us page
- [ ] Rules and guidelines page
- [ ] FAQ
- [ ] Cultivator requests a new strain listing — `platform.request_catalogue_addition`
- [ ] Cultivator requests a new finished product type — `drawio`, cultivator story v1
- [ ] Administrator queues for both request types
- [ ] Escalation from the club tier to the UC tier — C2

---

## Block 12 — Plant subscriptions, settlement and reporting

### Plant subscriptions — `plant-subscription`

A **different mechanic** from the membership subscription. The old plan conflated them.

- [ ] Member subscribes to a strain from a particular cultivator, at a number of plants per month
- [ ] Several concurrent subscriptions per member, across cultivators and strains
- [ ] Runs until cancelled with a month's notice
- [ ] Subscription orders visible to the member, the cultivator and the administrator

### Cultivator settlement — C10

Unspecified in every document. A launch blocker for cultivators.

- [!] Does the platform collect and remit, or introduce and invoice a commission?
- [!] What is the platform's take, and is it visible to the cultivator?
- [!] When does a cultivator earn — at order, at harvest, or at delivery?
- [ ] Statement of account, payments due, record payments made — `drawio`
- [ ] Payout mechanism. Payfast collects; it does not pay cultivators

### Refunds — C11

- [!] Partial reversal with transaction and platform fees withheld —
      `platform.refund_transaction`. `payments.md` §9 records that no refunds exist
- [!] Who carries a refund when the cultivator has already been paid — C10

### Reporting — `drawio`, administrator stories

- [ ] Sales reports
- [ ] Review reports
- [ ] Activity reports
- [ ] Revenue, membership, plant sales and swap activity dashboards

---

## Already built — for reference

Recorded so that this list is a complete picture rather than only the remainder.

- [x] Public landing page, compliance-governed copy, per-environment indexing
- [x] Age gate before sign-up
- [x] Sign-up: member details, RSA ID and mobile validation, nickname availability, club document
      agreements, registration stored
- [x] Membership subscription: Payfast checkout, signed notification, subscription and payment
      records, activation on payment, `lapse_memberships` command
- [x] Authentication: passkeys, emailed six-digit codes, sessions, CSRF, rate limits
- [x] Passkey enrolment, listing and revocation
- [x] Four roles as a constrained column, a permission catalogue in code, resolution through an
      authentication backend, `permissions` on the session payload
- [x] Sharing member registration with a cultivator's POPIA attestation
- [x] Member, cultivator and administrator home pages rendering from `permissions`, never from `role`
- [x] Member profile: name, nickname, mobile; avatar upload, crop and delete
- [x] Club document publication, versioning and consent ledger
- [x] Django admin over accounts, documents, subscriptions and payments
- [x] Soft delete and POPIA erasure

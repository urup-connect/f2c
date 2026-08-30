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

> **Block 0.5 is new and everything after it is resequenced.** A second storefront — the produce
> market — is in scope, and most of what is unbuilt turns out to be shared with it. **Block B — Market
> vertical** carries the market's own work and is lettered, not numbered: the blocks from 1 onward
> keep their contents and their numbers so nothing is lost, but they are re-ordered by `plan.md`
> section 4.1, which sequences Block B immediately after Block 0.5. See
> [`verticals.md`](verticals.md) and C26 to C28.

---

## Block 0 — Production blockers

Nothing below this block can be demonstrated to anybody until these are done. **A member cannot sign
in on a deployed environment today.**

- [x] **`.gitignore` was excluding both frontends' `lib/` directories — 133 TypeScript modules,
      never committed.** A bare `lib/` from GitHub's Python template matches at any depth, so
      `frontend/club/lib` and `frontend/market/lib` were silently untracked: `api.ts`, `site.ts`,
      every domain rule and every one of their tests. Nothing reports this — `git status` is clean
      and `git add` says nothing. Found while checking that the P6 work could be committed. The
      packaging patterns are now anchored to the repository root. **`backend.md` risk 12 said the
      project was not under version control and C23 closed it; a third of the frontend genuinely
      was not.** The 133 files still need adding in a commit of their own

- [ ] Configure a real email provider. `MAILERS` is the console backend, so sign-in codes and the
      duplicate-registration payment link reach nobody — P1
- [ ] Schedule `manage.py lapse_memberships`. Until something runs it, an unpaid membership keeps
      access indefinitely — P2
- [x] Shared cache backend. **Decided and built: Azure Managed Redis in QA and production, a
      `redis:7-alpine` container locally** (`compose.yaml`). `f2c/cache.py` reads
      `DJANGO_REDIS_URL`, refuses a deployed environment that names none, and refuses `redis://`
      where the Azure access key would travel in clear. `LocMemCache` survives only as the
      no-configuration fallback, which is what keeps the suite runnable with no servers.
      `DatabaseCache` on the existing MySQL was tried and cannot serve this — django-ninja checks
      throttles synchronously inside an async operation and the database cache is `@async_unsafe`,
      so it raised `SynchronousOnlyOperation` on the first throttled request and turned 82 tests
      into errors. Verified against a real Redis over TCP: the same 635 tests pass — **C31** — P3
- [ ] Document backup and rotation for `DJANGO_FIELD_ENCRYPTION_KEY`. Losing it destroys every
      stored identity number with no recovery path — P4
- [ ] Restrict `POST /api/auth/login` to `is_staff`. Unreachable today only because `create_user`
      calls `set_unusable_password()` — and **Block 0.5 narrowed that to the only thing holding the
      door**: accounts used to be created at `PENDING_PAYMENT`, which `aauthenticate` refused on its
      own, and they are created `ACTIVE` now. The endpoint's own docstring says it is retained for
      staff; nothing enforces it — P5
- [x] Move the API address to runtime configuration — P6. **Done.** `NEXT_PUBLIC_DJANGO_API_URL` is
      gone; `DJANGO_API_PUBLIC_URL` is read per request by `lib/api-address.ts`, rendered into the
      document by the root layout, and read from there by `lib/api.ts`. Neither Dockerfile takes it
      as a build argument any more. **Verified by building once with a deliberately wrong address
      and serving that single build under two others**: the build-time value appears nowhere in
      `.next/static` or `.next/server`, and two containers served two different addresses from the
      same bundle. Omitting it answers 500 on the first request naming the variable, rather than
      defaulting to localhost as the old code did. Cost: both root layouts are `force-dynamic`,
      which moved `/_not-found` and the club's two static sign-up confirmations off the static path
      and nothing else — every other route already read cookies — **C31**
- [ ] Grant the founding administrators their authority by hand — `is_staff` for the UC tier, and a
      club `StorefrontStaff` row for each club administrator. **No migration can guess which
      accounts belong in which tier**, and until somebody does it a deployed environment has nobody
      who can administer it. This was Block 2's *promote the existing administrator accounts*; C29
      turned it from a role change into a deployment step
- [x] Choose a hosting target and provision the database. **Decided, and not as written**: the
      database is MySQL 8.4 and was already built that way — `f2c/database.py`, `app/common/checks.py`
      and the CI job — while this line still said PostgreSQL. `uuid7` needed neither. The target is
      Azure in West Europe: three Container Apps, a managed MySQL, a Function App for the timer —
      **C31**
- [ ] Provision the Azure resources for the above: two Container Apps for `frontend/market` and
      `frontend/club`, one for the API, an Azure Database for MySQL Flexible Server 8.4, an **Azure
      Managed Redis**, a Container Registry, a storage account for media, and a Log Analytics
      workspace. West Europe throughout. Provision Managed Redis rather than Azure Cache for Redis —
      the Basic, Standard and Premium tiers retire on 30 September 2028
- [x] Write the two Next.js Dockerfiles. Both configs now set `output: 'standalone'` and
      `outputFileTracingRoot` to the workspace root — the applications share a hoisted
      `node_modules` one level up, so tracing from the application directory produces output that
      points outside its own tree. `frontend/club/Dockerfile` and `frontend/market/Dockerfile` build
      from the `frontend/` context, refuse a build with no `SITE_URL` or
      `SITE_URL`, and run non-root. Both builds were run and the assembled runtime layout was served
      locally: `/` at 200, stylesheet at 200, `robots.txt` generated. `SITE_URL` and `APP_ENV` are
      still build arguments — `lib/site.ts` evaluates them during prerendering — so an image is
      still specific to an environment even though the API address no longer is
- [ ] Set `DJANGO_BEHIND_PROXY=true` on the API container. **Without it every Payfast notification
      is rejected and no membership ever activates** — Container Apps ingress is a reverse proxy, so
      `REMOTE_ADDR` is Envoy and `verify_notification` refuses the source address. The single
      highest-consequence variable in the deployment — C31.
      **Forgetting it no longer reaches production.** It is one variable now rather than two —
      Django's `SECURE_PROXY_SSL_HEADER` and the Payfast source check are the same deployment fact —
      `payments.W001` fires on `manage.py check --deploy`, the container entrypoint runs that check
      at `--fail-level WARNING` so the revision never starts, and a notification rejected from a
      private address says in the log that the address is the proxy
- [x] Write the API container. `Dockerfile` builds `mysqlclient` in a build stage and ships
      `libmariadb3` and the CA roots in the runtime stage, non-root; `deploy/entrypoint.sh` waits
      for the database, gates on `check --deploy --fail-level WARNING`, migrates, then serves. The
      two Next.js images are still to write
- [x] Set the HTTPS settings `check --deploy` asks for. `SECURE_PROXY_SSL_HEADER`,
      `SECURE_SSL_REDIRECT` and HSTS all derive from `DJANGO_BEHIND_PROXY`, so a correct deployment
      sets one variable. `SECURE_HSTS_PRELOAD` is deliberately refused and `security.W021` silenced
      with the reason recorded in settings — the preload list is close to irreversible and covers
      subdomains this project does not serve
- [ ] Pin `min-replicas 1` on the API container. Scale-to-zero plus the four DNS lookups in
      `payfast_addresses` risks timing out an inbound notification, and a dropped notification is a
      member who paid and was not switched on — C31
- [ ] Replace `lapse_memberships`' intended home. Its docstring still says "a daily cron or an Azure
      App Service WebJob"; the decision is a timer-triggered Function App. That needs a protected
      endpoint on the API for the Function to call — packaging Django into the Function App instead
      would mean a second deployment artefact on a preview Python runtime — C31
- [ ] Disclose the transborder flow. West Europe puts members' identity numbers outside South
      Africa; lawful under POPIA s72(1)(a), but it has to appear in the privacy notice and the PAIA
      manual — C31
- [x] Put the deployed MySQL connection on verified TLS. Flexible Server runs
      `require_secure_transport=ON` and mysqlclient defaults to `ssl_mode=PREFERRED`, so the
      connection was coming up **encrypted but unverified** and saying so nowhere. `tls_options`
      now takes `DJANGO_DB_SSL_CA` and sets `VERIFY_IDENTITY`, or `DJANGO_DB_SSL_DISABLED` for a
      server with no certificate, and refuses a deployment that names neither — C31
- [x] Fix the CI job's silent SQLite fallback. `DJANGO_ENV` was never set anywhere — not in
      `ci.yml`, not in `.env.example` — and `database_config` reads it first, so `dev` was returned
      and the MySQL job ran against a local file with every MySQL variable set and ignored. Only the
      `connection.vendor` assertion caught it. Now set to `qa` in the workflow and documented
- [x] Run `manage.py check --deploy` and clear it. Cleared, and it is now enforced rather than
      remembered: `deploy/entrypoint.sh` runs it at `--fail-level WARNING` before uvicorn starts, so
      a warning is a failed revision and Container Apps keeps the previous one serving
- [ ] Fix `frontend/club/app/api/nickname/availability/route.test.ts` — it asserts a random hex string
      does not contain `500`, `503`, `429` or `422`, all valid hex, so it fails about one run in
      thirty — C25
- [x] Clear the stale-document drift: `frontend.md` §9 and `roles-and-permissions.md` §13 both say
      profile editing is unbuilt, and it is built — C21. Close `backend.md` risk 12, which says the
      project is not under version control — C23

### Two domains — C3, C30

**The assignment is fixed and it is not what C3 assumed** — see **C30**. `f2c.co.za` is the
**market** (`frontend/market`), `f2c-cannabis.co.za` is the **club** (`frontend/club`), landing page
and age gate included. There is no separate marketing site. The API answers on
`backend.f2c.co.za` and `backend.f2c-cannabis.co.za`: one Django deployment, two hostnames, paired
so each frontend calls an API inside its own registrable domain and `SameSite=Lax` survives
untouched.

- [x] Split `SITE_URL` into a host per storefront. **Closed by Block 0.5 rather than by work of its
      own**, and it went unnoticed: splitting the frontend into two applications split the value with
      it. `frontend/club/lib/site.ts` and `frontend/market/lib/site.ts` each read their own
      `SITE_URL` from their own deployment — C30
- [x] Apply the `robots` and canonical rules per host rather than per environment
      (`features/landing.md` §6). Also closed by the two-application split: each application derives
      `robots`, `sitemap` and `metadataBase` from its own `SITE_URL`, so the rules are per host by
      construction. `APP_ENV` still gates indexing on top of that, and should — it is what keeps QA
      out of the index — C30
- [ ] Set the deployment configuration for both domains. Every variable exists and none has a
      production value. `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`,
      `DJANGO_CORS_ALLOWED_ORIGINS` and `DJANGO_WEBAUTHN_ORIGINS` each carry both sides. Two are
      easy to get backwards and worked examples are now in `.env.example` — C30:
      - `DJANGO_STOREFRONT_HOSTS` takes the **API** hosts, because `storefront_for_request` reads
        Django's host and never sees the frontend's:
        `backend.f2c.co.za=market,backend.f2c-cannabis.co.za=club`
      - `DJANGO_WEBAUTHN_RP_IDS` takes the **frontend** domains, because a credential is bound to the
        origin the JavaScript runs on: `club=f2c-cannabis.co.za,market=f2c.co.za`
      - `SESSION_COOKIE_DOMAIN` stays **unset**. One deployment on two registrable domains cannot
        name one cookie domain, and host-only cookies per API host are what the pairing needs
- [ ] Provision DNS and TLS for four names — `f2c.co.za`, `backend.f2c.co.za`,
      `f2c-cannabis.co.za`, `backend.f2c-cannabis.co.za` — and route both `backend.*` names to the
      one Django deployment. A SAN certificate per domain, or one covering all four
- [ ] Decide apex versus `www` per domain and set the redirect. No consequence in the codebase
      provided the canonical one is what `SITE_URL` names — C30
- [ ] Deploy and index `f2c.co.za` (store) and `f2c-cannabis.co.za` (club) separately

### Public landing page

- [x] Landing page with compliance-governed copy — `features/landing.md`
- [x] Age gate before sign-up
- [x] Sign-up call to action
- [x] Intro blurb and introduction video — `drawio`, member story
- [ ] Platform information section, including a snapshot of plants available. **Block 3's model is
      built, so the snapshot has something to read**; the section itself is not
- [x] Terms, conditions and club rules on the public page
- [!] Display the membership fee. The copy-compliance patterns refuse currency and retail voice on
      this page; needs a named exemption rather than a relaxed pattern — **C20**

---

## Block 0.5 — Identity decomposition — done

New. Resolves **C27** and **C28**, and most of **C13**. Nothing in the market and nothing in the
shared commerce spine can be built before this, because `is_active` is derived from `status` under a
check constraint and `PENDING_PAYMENT` is not `ACTIVE` — **a produce customer cannot sign in on
today's model.** Reasoning in [`verticals.md`](verticals.md) sections 5 and 6.

**There is no data migration.** The development database is dropped, every `migrations/` folder is
cleared and the schema is rebuilt from the new models. What that costs is test support data, listed
at the end of this block. The window closes the day the club has members beyond the founding set —
against live rows this is a backfill over encrypted columns that cannot be re-run.

**Status — done.** Every section below is closed and both suites are green: **1448 backend tests and
1932 frontend tests, no failures** (28 August 2026). Nothing here is outstanding. What the block
deferred rather than dropped now sits in the block that owns it.

### Clear the ground first — done

- [x] Record what the migrations encoded that the models do not, **before** deleting them —
      [`migrations.md`](migrations.md). The list of four named here was wrong in both directions:
      `accounts/0008` carries nothing but generated output, and two data operations were missing
      from it entirely. See `migrations.md` section 3
- [x] Delete `db.sqlite3` (untracked, `.gitignore:67`). Backed up out of tree first
- [x] Delete all seventeen `app/*/migrations/0*.py`, keeping the `__init__.py` files. Recoverable
      from git history at `cddd2e2` if anything here proves incomplete
- [x] Confirm the models are self-consistent without them — `makemigrations --dry-run` produces one
      initial per app and no circular dependency

**Carried into the rebuild, from `migrations.md` section 4.** These are the items the cleared set
held and the models do not. **All five were closed by *Migrations regenerated* below**, which was
brought forward once the producer and document work landed — they are kept here as the list that was
carried rather than restated as done in two places.

- [x] Re-seed the three club documents — identities only, no revisions, so sign-up fails closed
      until each has one published. `migrations.md` §3.1. Under **C26** they seed against the club
      storefront with `audience=customer`, `agreement=at_registration`. The store's own privacy
      notice, terms and data policy are new rows, not copies — see Documents above
- [x] Re-seed the plant serial counter, last in its migration. `allocate_serials` refuses to create
      it on purpose — a missing counter and a counter at 1 are indistinguishable to code and would
      reissue serials already printed on certificates of ownership. `migrations.md` §3.2
- [x] **Decide what happens to the four auth groups.** Dropped, as recommended. They mirrored the role column, which C28
      retires. Drop them and let `RoleBackend` resolve from the membership tables, or keep them as
      the admin-side view and define what a group means when one person holds three.
      `migrations.md` §3.3 recommends dropping them, with `ROLE_GROUP_NAMES`
- [x] Do **not** recreate the superuser-to-`admin` backfill. Not recreated. C29 makes `is_staff` the tier outright
      — `migrations.md` §3.4
- [x] Confirm the four derived-column rules survive with both their unique index and their check
      constraint **in the same migration** — `nickname_key`, `mobile_key`, `live_for_user`,
      `current_for_plant`. `migrations.md` §2. **Five, not four**: `primary_for_producer` and
      `trading_name_key` appeared during the block and `current_for_plant` was not among them

### Split the record — done

The three tables exist, `User` is reduced, and the app registry and Django admin load. The ~200 call
sites that read the moved columns are done too — the sweep is at the end of this section, with what
verifies it.

- [x] **`ClubMembership`** — `app/club/membership/models.py`. Status, nickname and key, the four
      sharing-member columns, `erased_at`. Four constraints — C27
- [x] **`StorefrontStaff`** — `app/core/storefronts/models.py`, a new app. `Storefront` is a
      `TextChoices` column with a check constraint rather than a table: there are exactly two, every
      row carries exactly one, and a table would buy a join and a seed migration to answer no
      question — C28, C29
- [x] **`ProducerMembership`** — appended to `app/commerce/producers/models.py` with a `ProducerRole` of
      primary / full / limited. Carries `primary_for_producer`, a derived column enforcing **one
      primary per producer** — the fourth use of the null-slot trick, after `nickname_key`,
      `mobile_key` and `live_for_user`, and for the same MySQL reason — C28
- [x] Reduce `User.status`. Now `ACTIVE`, `SUSPENDED`, `INACTIVE` and **`NON_AUTHENTICATING`**
- [x] Keep `user_is_active_matches_status` — the expression is unchanged, only the value set it
      ranges over is smaller
- [x] Move `nickname` and `nickname_key`, with the unique index and the derived-column check
      constraint, to `ClubMembership`. `User.club_nickname` reads it back for the callers that want
      the club's name for somebody
- [x] `soft_delete` clears the membership nickname and stamps `erased_at` in the same transaction.
      The sharing-member completeness constraint needed the exemption and a database `CHECK` cannot
      read `User.deleted_at` across the table boundary
- [x] `id_number_encrypted` and `id_number_hash` were already nullable, so nothing moved. **The
      requirement is not yet enforced anywhere** — see the call-site list below

**Two decisions, both since confirmed by the product owner:**

- [x] **An unpaid club registrant can sign in.** `PENDING_PAYMENT` gated the account; it now gates
      the membership. `create_user` defaults to `ACTIVE`. Confirmed, with the redirect below as its
      condition
- [x] **Pay-now redirect — done.** Nine changes, and the interesting ones are not the redirect:

  - [x] `UserOut` carries `membership_status` beside `status`, and `nickname` resolves from the
        membership. `UserManager.with_club_membership()` exists because both read a reverse
        one-to-one and an unloaded relation inside `authn`'s async views raises
        `SynchronousOnlyOperation`. All four sign-in endpoints load it
  - [x] `clubGateFor` in `frontend/club/lib/club-membership.ts` — one pure, tested function, because a
        payment gate that grows a second copy in a page guard is how somebody reaches the club
        without paying
  - [x] `requireClubMembership` in `club-session.ts`, called by the `(club)` layout. Two gates now:
        is this anybody, then is the club open to them
  - [x] **Nobody is sent to a checkout that cannot help them.** A membership at `pending` awaits the
        club's verification and a `sharing` row is a placeholder; money settles neither, and
        offering a payment there takes money for something the payer does not get. Both go to the
        front door. `payments/services.ACTIVATABLE_STATUSES` refuses them on the API side too
  - [x] **`GET /payments/me/checkout`** — new, session-authenticated. `/pay` took a token from an
        `httpOnly` cookie the sign-up action sets, which a member signing in a week later does not
        have, so the redirect would have landed on "your payment link is unavailable". `/pay` now
        falls back to this when there is no cookie; `/pay/[token]` deliberately does not, so a stale
        emailed link cannot quietly charge whoever is signed in on that browser
  - [x] Payment activates the **membership**, not the account — `_activate_account` became
        `_activate_membership`
  - [x] `lapse_overdue` lapses the membership and leaves the account alone. It called
        `user.deactivate()`, which would now lock a produce customer out of the market because their
        club subscription stopped paying, and deny the member the one screen that fixes it
  - [x] Registration writes the account and the membership in one transaction, with the nickname on
        the membership where its uniqueness index lives
  - [x] The membership card reads `membership_status`. It would otherwise have reported "Active" at
        a member who has not paid

  Verified: `manage.py check` clean, frontend non-test typecheck clean, eight new unit tests pass.
- [x] **`UserStatus.SHARING` became `NON_AUTHENTICATING`**, named for the fact the auth stack needs
      rather than the club concept — **C6** is now decided and the name still holds

**C6 is decided: a sharing member is a placeholder, not a person.** Acted on here rather than
deferred, because the deletion is free exactly once — see C6 and `verticals.md` §5.

- [x] Drop `sharing_consent_attested_by`, `_at` and `_version` from `ClubMembership`
- [x] `sharing_member_is_complete` becomes `sharing_member_has_a_cultivator` — orphaned stock was
      always the real failure, and the swap zone can tighten it against a defined feature
- [x] Drop `erased_at` and the erasure exemption. A placeholder has no personal data to erase
- [x] `registered_by` and the nickname stay
- [x] `accounts.services.register_sharing_member` stops collecting an identity number and stops
      validating the age rule. Done under *Retire the role column* — the signature is now
      `(*, actor, producer, nickname)` and nothing else

**The call sites — done.** Roughly 200 references to `nickname`, `UserStatus.PENDING`,
`UserStatus.PENDING_PAYMENT`, `UserStatus.SHARING`, `registered_by` and `sharing_consent_*`.
Verified mechanically: a grep for `UserStatus.PENDING_PAYMENT`, `UserStatus.SHARING`,
`sharing_consent_*`, `ROLE_GROUP_NAMES` and `with_role(` over `app/` and `f2c/` returns **nothing**
outside one docstring naming the call it replaced.

- [x] `app/club/membership/` — services, schemas, api, administration, throttles. The largest single
      group and the one that decides how registration writes two rows in one transaction
- [x] `app/core/accounts/` — services, schemas, profile, roles. `register_sharing_member` writes to the
      membership now
- [x] `app/core/payments/services.py` — `ACTIVATABLE_STATUSES` gates on the membership, not the account.
      This is where the sign-in change above becomes real
- [x] `app/core/common/validators.py` and `app/core/common/checks.py` — the nickname helpers stay, their
      callers move
- [x] `app/club/plant/`, `app/club/strains/`, `app/commerce/producers/`, `app/core/authn/`, `app/core/documents/` — admin
      classes and `_cultivator.py`, mostly nickname display. Every list view that shows a nickname
      needs `select_related('club_membership')` or it pays a query per row
- [x] 27 test modules, and the seven support builders already listed under *Recreate the test
      support data*
- [x] 44 frontend modules. The nickname is still a member concept there, so most of this is the
      API contract rather than the UI. **1932 of 1932 frontend tests pass**
- [x] Django admin for `ClubMembership`, `StorefrontStaff` and `ProducerMembership` — its own
      section below

- [x] Regenerate one initial migration per app and check the schema by hand. Held until the role
      column and the producer rename had landed, then done — see the migrations section below

### Retire the role column — done

- [x] `User.role`, its check constraint, `set_role`, `sync_role_group`, the `_role_in_db` /
      `from_db` plumbing and the four `is_*` properties are all gone — **C28**
- [x] **The Django groups went with it.** `ROLE_GROUP_NAMES` and the group mirroring in `save()`
      are removed. They existed so future model permissions would have somewhere to hang; with no
      column to mirror there is nothing to keep them in step with, and a group that drifts is worse
      than no group — `migrations.md` §3.3, decided as recommended
- [x] `permissions_for` reads three relationships instead of one column. An active `ClubMembership`
      grants the member set; a `StorefrontStaff` row for the club grants the administrator set; each
      `ProducerMembership` grants a base set, plus full rights, plus the primary's
- [x] `User.objects.with_platform_roles()` — `select_related` the membership, `prefetch_related`
      both appointment sets. **Required, not an optimisation**: unloaded it is three queries per
      account, and inside `authn`'s async views it is `SynchronousOnlyOperation`
- [x] Drop `platform.refund_transaction` and `platform.cancel_membership` from the catalogue —
      Django admin operations, **C29**. `platform.manage_administrators` was never built
- [x] `createsuperuser` creates an `is_staff` account and nothing else. It used to also stamp the
      club administrator role so the founder did not appear as an ordinary member; there is no list
      of roles to appear in now
- [x] `UserOut.role` survives as a **derived** value — most-capable-first, for routing only — so
      `clubHomeFor` and the club home pages are unchanged. `permissions` remains the answer to what
      somebody may do, and the two can legitimately disagree
- [x] `register_sharing_member` rewritten for **C6**: no names, no identity number, no age rule, no
      attestation. A nickname and the cultivator, written as a `User` at `NON_AUTHENTICATING` plus a
      `ClubMembership` at `SHARING`, in one transaction
- [x] Call sites: `strains/admin.py`, `strains/services.py`, `plant/.../_cultivator.py`,
      `membership/administration.py`, `membership/schemas.py`, `membership/services.py`,
      `accounts/{admin,forms,profile,schemas,services}.py`. `User.objects.producers()` replaces
      `with_role(CULTIVATOR)`; `User.is_producer` and `User.is_sharing_member` read the relations

**Two things this closed that were carried as open:**

- [x] **C13 and `roles-and-permissions.md` risk 9.** "Only the primary appoints staff" was an
      object-level rule the catalogue could not express. It is now a column on the appointment, read
      in `permissions_for`. The remaining half — "may they price *this* listing" — has
      `ProducerMembership` rows to join against, which is what it never had
- [x] **The two-accounts limitation.** The design document recorded, as accepted, that somebody who
      both administers and buys needs two accounts. Verified gone: an administrator who also holds a
      membership resolves to exactly the union of both sets

Verified by smoke test: an unpaid membership grants nothing, a limited appointment cannot appoint
staff, a primary can, administrator + member is the exact union, and every granted action is in the
catalogue.

- [x] **`design/features/roles-and-permissions.md` rewritten** against `roles.py` in one pass.
      Verified mechanically: every `platform.*` codename in the document exists in `roles.py` apart
      from the two it discusses as removed, and every symbol it names resolves
- [x] Six risks closed by the change rather than by work — 1, 2, 3, 4, 5, 6 — each marked closed
      with what closed it rather than deleted. Risk 7 narrowed. Three new ones added: 11 (the
      `with_platform_roles()` discipline nothing enforces), 12 (derived `role` mistaken for
      authority), and 8 restated
- [x] Two dead navigation destinations removed — `refunds` and `cancel-membership` pointed at the
      codenames **C29** deleted. The `club-navigation.test.ts` contract test failed on both the
      moment they left `roles.py`, which is that test doing exactly its job

### Generalise the producer — done

- [x] **`CultivatorProfile` becomes `Producer`**, and it is more than a rename. The one-to-one to a
      user is **gone**: the organisation is the record, people are `ProducerMembership` rows against
      it, and the primary is the appointment that says so. Its own comments had said twice that it
      pointed at a user and should point at a farm
- [x] **`trading_name`**, with `trading_name_key` and a case-insensitive unique index over it — the
      fifth use of the derived-column trick after `nickname_key`, `mobile_key`, `live_for_user` and
      `primary_for_producer`, for the same MySQL reason. `pseudonym` reads it. The old model
      predicted this: *"if the club ever does decide a farm needs a trading name distinct from its
      owner's nickname, there is one place to change"* — a farm with three appointed staff has no
      single owner whose nickname to borrow
- [x] **`ProducerStorefront`** — which storefronts a producer sells into, one row each, so a farm
      may supply the club with cannabis and the market with vegetables. Named for the storefront
      rather than `ProducerCategory`, deliberately: *which storefront* and *which produce category*
      are different axes, and the second belongs to the market catalogue
- [x] **Collection address and bank details** — the drawio cultivator story's "My Farm". The account
      number is encrypted through the same helper the identity number uses and is **not**
      blind-indexed: an identity number is searched, an account number is only ever read back. The
      admin renders it write-only, following `backend.md` §10
- [x] Four foreign keys repointed at the organisation, verified: `strains.Strain.exclusive_to`,
      `strains.CultivatorStrainListing.cultivator`, `plant.Batch.cultivator` and
      `membership.ClubMembership.registered_by`. The field name `cultivator` **stays** on the club's
      two — that is what the club calls a farm, and renaming it to match a table would rename the
      club's vocabulary
- [x] `Producer.primary` reads the appointments; returns `None` for a producer nobody is appointed
      to yet, which is a legitimate intermediate state rather than an error
- [x] Producer admin rebuilt: appointments and storefronts as inlines, because neither means
      anything away from the farm it belongs to. `primary_name` on the list, showing a dash — a
      producer with no primary is exactly what staff look for when nobody can appoint anyone
- [x] `resolve_cultivator` in the plant commands resolves a **trading name**, not an email address
      or a nickname. A farm with three appointed staff had three equally good answers to "who is the
      cultivator"; a trading name has one
- [x] Strain exclusivity and the cultivator pickers offer producers, not people. The erased-account
      filter went with the user: an organisation is not erased under POPIA

**`register_sharing_member` now makes the first object-level check in the codebase.**

- [x] Takes `actor` and `producer` separately. The permission says the caller is a primary
      *somewhere*; a second check says they are the primary *of this farm*
- [x] That is **C13** and roles risk 9 closed in practice rather than in principle — the check is a
      join against `ProducerMembership`, which is exactly what those two said did not exist. It is
      the shape the rest of the object-level rules should take: the catalogue answers "may they at
      all", the service that owns the record answers "may they here"
- [x] Superusers exempt, as they are from every other check

Verified: `manage.py check` clean, all ten constraints present across the three models, the four
foreign keys resolve to `cultivators.Producer`, and the bank account number encrypts, round-trips
digits-only and leaves blank as blank.

### Documents, for two storefronts — done

No document is shared between them — `verticals.md` section 6. The models were being rebuilt, so all
of this landed in the schema rather than as an alteration.

- [x] `ClubDocument` → **`Document`**, with a non-null `storefront` column and `slug` unique per
      `(storefront, slug)`. A column with a check constraint rather than a foreign key, for the
      reason `storefronts.models` gives; and **no nullable "both" value**, because nulls are distinct
      under a unique index and two platform-wide documents could then share a slug — the exact
      failure `backend.md` §8.2 exists to prevent
- [x] `required_at_signup` replaced by **`audience`** (`public` / `customer` / `producer`) and
      **`agreement`** (`none` / `at_registration` / `at_onboarding`). `at_checkout` deliberately not
      added: it is an enum value if market terms turn out to be accepted at first order
- [x] **`retired_at`**, its own field. Setting `agreement=none` would retire a document *and*
      publish it as a public page in one edit — two different intentions
- [x] A fifth constraint that was not on the list and should have been:
      **`document_public_needs_no_agreement`**. A public page that also demands agreement has nobody
      to demand it of before an account exists, and the sign-up form would ask a visitor to tick
      something it cannot record
- [x] **`ProducerAgreement`** — producer, version, `signed_by`, both digests, unique on
      `(producer, version)`. `signed_by` is `SET_NULL` where `DocumentConsent.version` is `PROTECT`,
      and that asymmetry *is* the model: the agreement outlives the person, so their erasure must
      neither be blocked by it nor delete it. Keyed on the producer, not the signatory — two
      primaries signing one revision is one agreement by one organisation
- [x] **`GET /documents/published`**, unauthenticated — the store's legal pages and the club's
      rules. Separate from `/current` rather than a flag on it, because they differ on the one thing
      that matters: `/current` answers **503** when a required document has no published revision,
      since sign-up must refuse the form; a legal-pages index with one entry missing is still usable
- [x] All four endpoints scoped by storefront
- [x] **Host resolution** — `app/core/storefronts/resolution.py`, plus `DJANGO_STOREFRONT_HOSTS` and
      `DJANGO_DEFAULT_STOREFRONT` in `.env.example`. The two unauthenticated endpoints have no
      session, so the host is what is left; this is the same question `rp_id()` has to answer.
      Verified: port stripping, IPv6 literals left intact, mapped hosts, unmapped fallback
- [x] Storage path is `documents/<storefront>/<slug>/<label>/<file>`. Without the segment a `terms`
      at `v1` on each storefront is **one key**, and the second upload overwrites a file somebody has
      already agreed to — the one thing that path exists to prevent
- [x] `manage.py publish_club_document` → **`publish_document`**, with a required `--storefront`.
      Required and not defaulted: a slug is only unique within a storefront now, so "publish terms
      v2" is ambiguous, and a default would resolve the ambiguity silently
- [x] `membership.services` passes `Storefront.CLUB` explicitly rather than reading the host —
      registration creates a `ClubMembership`, so it is club-scoped by definition, and resolving
      from the request would make it possible to join the club through the market's domain

Verified: `manage.py check` clean, five constraints on `Document` and one on `ProducerAgreement`,
schema generates, frontend non-test typecheck clean.

### Layout — done

- [x] Apps moved into `app/core`, `app/commerce`, `app/club`, with `app/market` created empty.
      `label` set explicitly on every `AppConfig`, so **no table changed name**, `AUTH_USER_MODEL`
      is still `accounts.User`, and no migration dependency moved. Verified against the model
      registry
- [x] `cultivators` → `commerce/producers` — the one app renamed rather than only moved, which was
      the point: a farmer growing carrots is the same record as a cultivator growing cannabis
- [x] `INSTALLED_APPS` regrouped and commented by what each group serves
- [x] Project package `cultivatorscollective/` → **`f2c/`**. 21 files rewritten; `manage.py`,
      `asgi.py`, `wsgi.py`, settings, CI and both PowerShell scripts follow
- [x] `rp_id()` takes the request's storefront, with `DJANGO_WEBAUTHN_RP_IDS` mapping
      `storefront=domain`. Falls back to `DJANGO_WEBAUTHN_RP_ID`, so a single-storefront deployment
      is configured exactly as it was. Verified both paths
- [x] Frontend moved to `frontend/club`, with `frontend/package.json` as an npm workspace root
      (`club`, `market`, `packages/*`). One lockfile, one hoisted `node_modules`
- [x] `turbopack.root` repointed one level up. It had been pinned to the application directory, and
      after the move `node_modules` is hoisted to the workspace root — pinning the app directory
      left Turbopack unable to resolve `next` itself
- [x] The `club-navigation.test.ts` contract test reads `../../app/core/accounts/roles.py`. It was
      one level up and is now two — the kind of break a move makes that nothing but running the
      suite finds
- [x] `copy-compliance.ts` stays in the club application, per **C26**
- [x] Docs: `backend.md` §3, root `README.md`, `verticals.md` §7, plus every frontend source path
      across ten files

**`packages/` is deliberately empty.** There is one application, so nothing is shared — extracting a
UI kit, an API client and a config reader now would mean drawing three boundaries with no second
consumer to test them against, which is how a shared package ends up shaped like its only caller.
The same reasoning as refusing a generic `Product` model. `frontend/README.md` records it so the
emptiness is not read as an unfinished step.

Verified after the move: `manage.py check` clean, schema generates with flat table names, frontend
builds past module resolution, **1926 of 1930 frontend tests pass**. The four failures are the
pre-existing `inactive` membership-status test data, unchanged by the move and on the list below.

### Migrations regenerated — done

Brought forward from the end of the block: the tests need a schema, and the models were stable once
the producer and document work landed.

- [x] `makemigrations` — one initial per app, eleven apps, 25 models
- [x] **Club document seed restored** — `migrations.md` §3.1. Three rows against the club storefront
      at `audience=customer`, `agreement=at_registration`; identities only, no revisions, so sign-up
      still fails closed until each has one published
- [x] **Serial counter seed restored**, last in its migration — `migrations.md` §3.2
- [x] Auth groups: **nothing seeded**, per the decision in `migrations.md` §3.3
- [x] Superuser backfill: **not** recreated, per §3.4
- [x] All five derived-column rules verified with their unique index *and* their check constraint in
      the same migration: `mobile_key`, `nickname_key`, `live_for_user`, `primary_for_producer`,
      `trading_name_key`
- [x] `migrate` runs clean; seeds verified present in the database

### The Django admin — done

Last of the block, and it is the interface catching up with the split. The account page was
administering three records; it now administers one and links to the other two.

- [x] **`ClubMembershipAdmin`** — `app/club/membership/admin.py`, new. The status, the nickname and
      the placeholder's producer, which is everything C27 moved off the account page. Editable, and
      **the nickname is the reason**: the uniqueness rule lives on `nickname_key`, so a form that
      compared the text it was given would agree with the index for most inputs and return a 500 for
      the rest. `ClubMembershipAdminForm.clean_nickname` calls `administration._validated_nickname`
      rather than restating it
- [x] **Suspending is an action, not the dropdown**, and both routes exist because they are not
      equivalent. The actions delegate to `administration.suspend_member` and `reinstate_member`, so
      an erased account, a placeholder, an unpaid membership and the administrator's own record are
      refused *with the sentence the service raised* rather than counted. The field stays editable
      because staff need to correct a status that is simply wrong, and `save_model` closes the gap
      that leaves — a membership edited out of Active would otherwise keep a signed-in browser
      working until its cookie expired
- [x] **`StorefrontStaffAdmin`** — `app/core/storefronts/admin.py`, new. **This is the page that
      hands over the register**, and nothing about one dropdown and an autocomplete says so, which is
      why the form carries the sentence that does. The appointee and the storefront freeze once the
      row exists: retyping a club appointment into a market one is two events against two different
      permission sets, and revoking and appointing says that truthfully. `appointed_by` defaults to
      whoever is filling the form in and stays editable, because it is provenance and nothing reads
      it for authority
- [x] **`ProducerMembership` needed nothing** — it was already an inline on `ProducerAdmin`, and an
      appointment away from the farm it belongs to is not an appointment
- [x] **The accounts admin, rewritten against what is actually there.** A **Relationships** panel
      replaces the nickname field and the Sharing member panel: the three rows that decide authority,
      linked rather than reproduced, each granted on its own page. An account with none of them says
      so in a sentence — on the produce market that is an ordinary customer, and three empty rows
      would not say it
- [x] **A real N+1 closed, not only documented.** `display_name` is on `list_display` and prefers the
      club nickname, which C27 moved one table away, so the changelist walked a reverse one-to-one
      **per row**. `get_queryset` selects it. This is risk 11 firing a second time, quietly rather
      than loudly, and it is now held by a query-count test rather than by discipline
- [x] The nickname is searchable again from the account page, through the relation
- [x] **`groups` is editable again.** It was read-only while `save()` mirrored the role column into
      it — a picker whose value is overwritten on the next save is worse than no picker. C28 removed
      the mirroring, so nothing maintains them and a group is once more only what somebody put in it.
      The stale panel description that said otherwise is gone with it
- [x] **A latent guard that never fired, in three places.** `if obj.pk is None` is the obvious test
      for an unsaved instance and is wrong on every model here: the primary key is a `UUIDField` with
      `default=uuid.uuid7`, so an unsaved row already carries one. `obj._state.adding` in all three
- [x] Dead `Group` import removed from `accounts/models.py`, and the docstrings in `accounts/forms.py`
      and `common/validators.py` that still routed the nickname clash through `User`

**38 new tests, and the shallow one earns its place.** `f2c/tests/test_admin_pages.py` asserts only
that every admin page renders — `manage.py check` covers a field that does not exist, and covers
nothing that happens while a page is being drawn: a display method that raises on a value it did not
expect, a `reverse()` to a route no longer registered, an `autocomplete_fields` entry pointing at an
admin with no `search_fields`. All three are 500s on a page that passed every check.

Verified: `manage.py check` clean, `makemigrations --check` reports no schema change, **1445 backend
tests pass** (1407 before), 1932 frontend tests pass.

### Recreate the test support data — done

**`f2c/testing.py` is new, and it is the piece that was actually missing.** Building a test account
used to be one call with a `role=` keyword. It is now three apps' models — `User` plus
`ClubMembership`, or plus `StorefrontStaff`, or plus `ProducerMembership` against a `Producer`. Five
support modules were about to grow five slightly different copies of that, which is how two of them
end up differing in a way nobody intended, in exactly the suites that exist to catch it. It lives in
`f2c` for the same reason `f2c.api` does: the one package allowed to know about all of them.

- [x] `make_account`, `make_member`, `make_producer`, `make_cultivator`, `make_administrator`,
      `make_sharing_placeholder`. None is a shortcut past the rules — an inactive account still
      resolves to no permissions, an unpaid membership still grants nothing
- [x] Six support modules rewritten: `payments`, `documents`, `membership`, `plant`, `strains`, and
      the shared factories
- [x] `payments`' `assertStillPendingPayment` now asserts on the **membership**. Checking the
      account would have passed trivially — it is Active from the moment it exists — so the
      assertion could no longer have failed
- [x] `membership`'s `sharing_member` fixture reduced to a nickname and a producer, per **C6**

**The suite found a second real bug, of the same family as the first.** `User.get_short_name()`
returned the club nickname, which since C27 lives one table away — and both callers are wrong to
reach there: `authn.otp.issue` runs in an `async def` view, where a lazy relation is fatal, and a
produce-market customer has no membership for a greeting to read. It now returns `first_name`.
`display_name` is the one that prefers the nickname, and its callers are club surfaces that select
the relation.

**The suite found the first bug the same way.** `authn`'s four async endpoints
loaded `with_club_membership()`, but `permissions_for` reads *three* relationships since C28.
`UserOut` serialises the permission set, so every sign-in and every `/api/auth/me` would have raised
`SynchronousOnlyOperation` in production. Corrected to `with_platform_roles()`, and the docstrings
in `accounts/schemas.py` that named the narrower loader with it. **This is risk 11 in
`roles-and-permissions.md` firing exactly as predicted** — loudly, which is the mitigation.

Test collection went from **323 to 1148** as the import failures cleared. **1085 pass, 63 do not.**

- [x] **All of it — done.** The failures were test *bodies* asserting on the old model and were
      rewritten by hand; regex passes stopped converging and were reverted once for introducing a
      syntax error. By cluster:
  - [x] **`strains` — done. 174 tests, all passing** (was 65 failing). App code again as much as
        tests: the listing's `__str__`, the two `reserved_to` resolvers and `CultivatorOut` now read
        `Producer.pseudonym`, and three orderings plus the admin search moved from
        `cultivator__nickname` to `cultivator__trading_name` — a join that no longer resolves is a
        500 on a list page, not a wrong answer

  - [x] **`membership` — done. 182 tests, all passing** (was 77 failing). Most of the work was app
        code rather than tests: the register lists **club members only**, so a produce-market
        customer never appears in it and neither does an administrator who never joined;
        `suspend_member` suspends the **membership**, because locking the account would sign
        somebody out of the market over a club matter — the same call `lapse_overdue` makes; the
        `role` filter became a join over the relationships, and an unrecognised value narrows to
        nothing rather than being ignored, since a filter that silently returns everybody is how an
        administrator believes they are looking at cultivators and is not
  - [x] **The last four clusters — done. 233 tests across the seven modules, all passing.**
        `authn/test_otp` and `test_throttles` (`nickname=` on `create_user`),
        `payments/test_services` (activation moved to the membership), `plant/test_upload`,
        `test_capture` and `test_export` (producer fixtures), and `documents/test_command`
        (`publish_document` and its `--storefront`)
- [x] **The three conceptual modules — rewritten by hand. 94 tests, all passing.**
  - [x] `accounts/test_roles` (41). `GroupMirrorTests` and `RoleColumnTests` **deleted** rather than
        adapted — there is no derived state left for them to guard. Replaced by `UnionTests`, the
        class the column made impossible: an administrator who is also a member holds the **exact
        union**, so a regression that passed by widening the member set fails there instead. Adds
        the C29 assertion that `is_staff` alone grants nothing, and an async test that pins the
        `with_platform_roles()` discipline — the one that would have caught this block's real bug
  - [x] `accounts/test_sharing_members` (31). Most of it deleted with C6: the identity number, the
        age rule, the attestation, and the duplicate-ID refusal whose leak was carried as risk 4.
        New `AbsenceTests` asserts what C6 *removed*, because a placeholder quietly regaining a name
        and an identity number breaks no feature — it is a POPIA problem nothing functional would
        notice. New `AuthorisationTests` covers the object-level check: a primary of one farm may
        not create a placeholder for another
  - [x] `accounts/test_uniqueness_keys` (22). The nickname key moved table with C27, so the
        assertions moved with it. **`PortabilityTests` now sweeps every model rather than `User`** —
        it was written when one model carried a derived key, and three more have appeared since
        (`live_for_user`, `primary_for_producer`, `trading_name_key`), each reaching for the same
        trick and none of them covered. All five are now named individually, because "no partial
        indexes" is trivially satisfied by having no constraints at all
- [x] `f2c/tests/test_admin_branding` reads `frontend/club/app/globals.css` — the path the layout
      move changed. It resolves again; twelve tests, all passing
- [x] The four frontend `inactive` membership-status failures, carried from this block's earlier
      sections, are gone

**Verified 28 August 2026: `manage.py test` runs 1448 tests and all pass (1445 before); the frontend
suite runs 1932 tests in 103 files and all pass (1928 before). Nothing on the test side of this block
is outstanding.**

---

## Block B — Market vertical

The produce market storefront. `plan.md` §4.1 sequences it immediately after Block 0.5 and ahead of
the club's remaining verticals, because it is the shorter path to a transacting platform: no
ownership chain, no swap zone, no statutory ceiling, no age gate, no copy-compliance corpus and no
outstanding legal opinion. It is lettered rather than numbered because the blocks below keep their
own numbers and are re-ordered by that section.

`app/market` exists and is empty, deliberately — `frontend/README.md` records why, so the emptiness
is not read as an unfinished step. `frontend/market` **now exists** and fills the workspace slot
`frontend/package.json` declares.

- [ ] **The vertical itself** — produce types, units, stock, delivery. `plan.md` §4.1 names the four
      and does not break them down; that decomposition belongs here and has not been done
- [x] **Create `frontend/market`** as the second Next.js application, filling the workspace slot that
      `frontend/package.json` already declares. Built: the front door, the legal index, sign-in
      (passkey and emailed code), sign-up, and the signed-in account area — home, details, security —
      with 338 colocated tests. Runs on port 3001. `design/frontend.md` section 11 is the design
- [ ] **A customer registration endpoint.** The one thing standing between the store application and
      a usable storefront, and it is backend work: Django's only registration endpoint is
      `POST /api/members/register`, which requires an identity number and document consents and
      creates a `ClubMembership`. A produce customer has none of those — `verticals.md` §6 — so
      calling it would enrol shoppers in a cannabis club. The frontend contract is already written and
      tested against, in `frontend/market/lib/sign-up-api.ts`:

      ```
      POST /api/customers/register        auth=None
        { first_name, last_name, email, mobile }
        201     -> accepted. The SAME answer for an address already on file, per RegistrationOut
        409/422 -> { "detail": ..., "fields": { "email": ["email-malformed"] } }
      ```

      The store currently gets a 404 and says "accounts are not open yet", which is honest and is not
      a placeholder to be replaced — it is the branch that stays for the day the API is down
- [ ] **The store's brand.** Palette, typography and a wordmark are neutral placeholders under the
      name *Farm to Consumer* (F2C), structured on the club's tokens so ratified values land in
      `frontend/market/app/globals.css` and nowhere else. `design/frontend.md` §11.5
- [ ] **Extract `frontend/packages/*`.** Now has a second consumer to draw the seams against, and the
      three kinds of candidate are sorted in `frontend/README.md`. Four modules are duplicated
      verbatim with their tests in the meantime — risk 11.3

### Shared work already built, waiting on the market

Each of these was built for two storefronts in Block 0.5 and has nothing to point at until the
market has content of its own.

- [ ] **The market's own documents**: privacy notice, terms of use, data policy. New rows against
      `Storefront.MARKET`, **not copies of the club's three**. The `Document` model, its `audience`
      and `agreement` columns and the `--storefront` flag on `publish_document` are all in place; no
      seed exists because there is nothing to seed. **There is now a page waiting for them**:
      `frontend/market/app/legal` reads `GET /api/documents/published` and today correctly says
      nothing is published — distinguishing that from "could not be read", because telling a shopper
      the store has no privacy notice on a day when it has one and the API was down is an untrue
      statement about a legal obligation
- [ ] **`frontend/club/lib/club-documents.ts` and `CLUB_DOCUMENT_IDS` per application.** The file has
      moved under `frontend/club` and the API contract did not change shape, so nothing is broken —
      the identifiers stay club-specific and split when the market has documents of its own
- [ ] **An administration area in the market application**, over a shared admin shell. Two
      administration areas, one per storefront, and **no UC tier** — **C29**. `StorefrontStaff`
      already carries the market appointment; there is no page that exercises it. **It also has no
      codename**: nothing in `roles.py` names authority over a storefront, so the store deliberately
      shows no administration tile rather than one gated on `undefined`. The codename comes first

---

## Block 1 — Catalogue

**Every model in this block is built.** The strain catalogue landed with its administrator screens,
the finished product type carries its price, and Block 0.5 generalised the cultivator profile into
`Producer`. What is left is one member-facing page — which belongs to Block 5 — and two
administrator screens.

- [x] **Strain** model, administrator-curated, platform-wide — `app/club/strains/models.py`.
      `StrainStatus` for curation, `exclusive_to` for the reservation, with aroma and effect
      vocabularies of its own — `member-roles`
- [x] **Finished product type** model with price — `app/club/finished_product/models.py`, with
      `code`, `price`, `is_available` and a display order — `product-types`
- [x] **Cultivator profile**: public description, image, pseudonym — `Producer`, generalised from
      `CultivatorProfile` in Block 0.5. `public_description` and `image` are columns; **the pseudonym
      is not**, and that is a recorded decision rather than an omission — a second namespace for a
      public name could hold a value identical to another member's nickname and no single constraint
      could span the two, so the farm's public name is `trading_name` — `member-roles`
- [x] **Cultivator strain listing** — `CultivatorStrainListing`, carrying `image`, `description`,
      `short_description`, `finished_product_types`, `default_grow_price` and `minimum_yield_grams`:
      the brief's six fields exactly — `member-roles`, `member-plant-purchase`
- [!] Decide how the three levels of finished-product-type selection relate — platform catalogue,
      strain listing, individual plant. Three documents put the list in three places — **C18**.
      **The recommendation is already built**: Block 3's plant inherits from its listing with no
      per-plant override, so the schema assumes the answer while `conflict.md` still records the
      question as open. Ratifying it costs nothing; reversing it is a model change
- [~] Administrator screens for strain and product type CRUD. Endpoint work is Block 9; the models
      are here. **Strains are done** — `/admin/strains` and the three routes under it, over
      `app/club/strains/api.py`. **Finished product types are not**, and neither is the cultivator's own
      listing screen: staff still write a listing in the Django admin

---

## Block 2 — Cultivator organisation

**The models landed early, in Block 0.5**, because the identity decomposition needed them. `Producer`,
`ProducerMembership` and the primary appointment are built, so **C13 and `roles-and-permissions.md`
risk 9 are closed** — under the role column, *only the primary may appoint staff* was an object-level
rule the catalogue could not express, and it is a column now. What is left of this block is the
endpoints and the object-level rules that arrive with them. Still a retrofit across every endpoint,
and still built after the models it scopes.

- [x] **Cultivator organisation** model — the farm as a record. `Producer` in
      `app/commerce/producers/models.py`, deliberately **not** cannabis-specific: a farmer supplying
      the produce market is the same record with a different `ProducerStorefront` row, which is why
      it sits on the commerce side rather than in the club vertical
- [ ] **Give `Producer` a lifecycle** — retired, or left the club — and restore `Strain.exclusive_to`
      against it. **A rule was lost in Block 0.5's producer generalisation, and it is recorded here
      rather than quietly dropped.** `exclusive_to` used to refuse a cultivator who had left, by
      checking `deleted_at` on their account — *"a departing grower must not take a catalogue entry
      with them."* A `Producer` is an organisation: it is not erased under POPIA and **has no
      departure state at all**, so there is nothing left to check. `is_published` is not a
      substitute — it is also false for a farm being set up, and reserving a strain to one before it
      opens is legitimate. `strains.services._validated_exclusive_to` carries the same note, and
      three tests are written against the current behaviour with docstrings saying why
- [x] **Primary cultivator flag.** `primary_for_producer` on `ProducerMembership`, a derived column
      enforcing one primary per producer, with `PRODUCER_PRIMARY_PERMISSIONS` in `roles.py` naming
      the three actions only a primary may take — appoint staff, register a sharing member, manage
      sharing members. **This is what closed risk 9**: under the role column those actions went to
      every cultivator — `member-roles`
- [~] **Appointed staff with full or limited rights.** The model is built: `ProducerRole` of
      primary / full / limited, with `has_full_rights` carrying the commercial decisions — pricing,
      listings and the public profile, as against moving stock — and the primary holding them too,
      because being the primary is more than full rights rather than an alternative to them.
      **There is still no endpoint.** `platform.appoint_cultivator_staff` is in the catalogue and
      held by primaries, and the only way to exercise it is the Django admin
- [x] Collection address on the farm — `drawio`, cultivator story
- [x] Bank details on the farm — `drawio`. Encrypted through the same helper the identity number
      uses and **not** blind-indexed, because an identity number is searched and an account number is
      only ever read back; the admin renders it write-only. Settlement itself is Block 12, **C10**
- [~] **Object-level permission rules.** `RoleBackend` still refuses object-level questions outright,
      and that is now a **recorded decision rather than a gap**: a role is a fact about an account,
      not about that account's relationship to one record, so answering an object-level question from
      it would come back yes for every listing on the platform. The rules arrive with the models they
      are scoped to, and two of them have:
  - [ ] A cultivator's own listings, stock and pricing
  - [~] The sharing members that cultivator registered. **Creation is checked** —
        `register_sharing_member` refuses a primary of one farm creating a placeholder for another,
        with a superuser exemption and a test covering both. Read, update and withdraw are not, and
        cannot be until the endpoints below exist
  - [ ] A member's own inventory
  - [x] Primary versus appointed staff — the `role` column on the appointment, read in
        `permissions_for`
- [x] Sharing member registration — `accounts.services.register_sharing_member`. **Without the POPIA
      attestation, and that is the point**: C6 made a sharing member a placeholder, and an
      attestation that a placeholder had consented was a ceremony around a fiction. The signature is
      `(*, actor, producer, nickname)` and nothing else
- [ ] An endpoint for registering a sharing member. The service authorises its own caller **including
      the object-level half**, so it is already the right shape to put a router in front of.
      Reachable from the admin and the shell only
- [ ] Sharing member read, update and withdraw — `platform.manage_sharing_members`
- [!] Decide whether an administrator may CRUD sharing members. §3.6 deliberately withholds it; both
      drawio administrator stories ask for it — **C14**. **Current behaviour refuses, deliberately,
      so as not to pre-empt the decision**: the register will not edit a sharing member, and
      `roles-and-permissions.md` records the Django admin as the route an administrator uses instead

### Two administrator tiers — C2

- [x] ~~Add `uc_admin` as a fifth role~~ — never built. The role column is retired (**C28**) and the
      UC tier is `is_staff` in the Django admin (**C29**)
- [x] **Split the administrative catalogue — done by removal rather than by splitting.**
      `refund_transaction` and `cancel_membership` left `ADMINISTRATOR_ACTIONS` entirely and
      `manage_administrators` was never added: an action in that catalogue is one an API endpoint
      checks, and the UC tier has no endpoint — the platform operator does both in the Django admin
      under `is_staff`. `test_roles` asserts all three are absent, and the navigation contract test
      failed on the two stale destinations, which is that test doing its job
- [x] ~~Change the `createsuperuser` default to `uc_admin`~~ — it creates an `is_staff` account and
      no role at all. See Block 0.5 — **C29**
- [x] ~~Second administration band and an escalation destination in `club-navigation.ts`~~ — not
      being built. C29 gives the UC tier no Next.js surface at all, so there is no band to add and
      nowhere to escalate to, and the two destinations that would have filled it are gone from the
      catalogue

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
- [x] **Individual plant capture** — `services.capture_plant`, reached from `manage.py add_plant`
      and from the admin's add form. **Not a second code path**: both routes share the coercion, the
      three database checks and the write with the upload, because the brief gives one field list for
      both. Errors are keyed by field so a form can attach each to the right input
- [x] The admin's add form allocates a serial. Before it did, `serial` was `editable=False` and so on
      no form, and the column is unique but not null — the first plant added by hand would have saved
      blank and the second would have failed on the index
- [ ] An endpoint for either. There is no `api.py` in `app/club/plant` at all — all three routes are
      staff-side, and a cultivator does nothing themselves until Block 9
- [x] Stock on hand **export** — `drawio`, cultivator story v1. `manage.py export_stock`, plus an
      admin action for whatever staff have filtered. Scoped to that story's own two screens — *my
      inventory for sale* (the default, and what SOH means) and *my member-owned inventory* — and it
      flags the "late items" the same story asks for. There is no stock model; the read is a queryset,
      and `design/backend.md` section 3 records why
- [x] The owner column carries a nickname and nothing else, and is absent when nothing in scope is
      owned. An export is a file that leaves the platform — **C19**
- [x] Adjust available plants, add and remove — `member-roles`. Withdrawing is the admin action on
      `platform.disable_plant`; adding is the capture work above

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
- [ ] The permission checks themselves. `platform.disable_plant` and `platform.disable_batch` are in
      the catalogue and the admin actions exist, but **nothing calls `has_perm` on either** — the
      admin authorises on `is_staff` like every other Django admin page. Waits on the endpoints in
      Block 9; the object-level half is **C13**, still open

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

- [ ] **Step 1 — strains.** Generic listing, general strain information, *grow price from*. This is
      Block 1's *generic strain listing page*, tracked here rather than there: the page only makes
      sense as the first step of this drill-down, and the model behind it is built
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

**C5.** The brief heads its administrator section "Admin (NextJs)". **Three of the twenty-nine
destinations are live** — the membership register, the strain catalogue and the member's own profile
— and twenty-six still render as *Not built yet* with no endpoint behind them, so most
administration still happens by hand in the Django admin. `club-navigation.ts` is the count:
`state: 'ready'` against `state: 'planned'`.

Everything here is split across the two tiers from C2.

### Members

- [x] **View, edit, suspend, reinstate** — `platform.disable_user`. A second router on the sign-up
      prefix (`GET /api/members`, `GET|PUT /api/members/{id}`, `POST .../suspend`,
      `POST .../reinstate`) and the screens at `/admin/members`: the register, and a member's own
      record. Five editable columns — both names, nickname, email, mobile — and **nothing that
      carries authority or money**: `role` stays a Django-admin appointment per `backend.md`
      section 10, and the standing moves through suspend and reinstate, which have rules a field
      assignment does not. Three writes are refused outright: an erased account, a sharing member
      (**C14** has not decided whether an administrator may touch one), and an administrator
      suspending themselves — that one signs the caller out and leaves nobody able to undo it
- [x] **There is no create and no delete**, by decision. Sign-up is the only route into the
      membership, because an account typed in by hand would have no consent ledger behind it and
      `documents` is where the club's lawful basis for holding an identity number lives. Erasure
      stays `User.soft_delete`, an explicit action in the Django admin — an erased account still
      appears on the register, marked, and every write against it is refused
- [x] Recent sign-ups — `drawio`. A *joined within* filter on the register rather than a screen of
      its own: the list is newest-first already, so a window on it is the same list in the same
      order
- [x] **Reading an identity number in full, recorded.** `accounts.IdentityNumberDisclosure` — who
      read whose, when, and why, with the reason required and required to say something. The row is
      written *before* the column is decrypted and inside the same transaction, so a read that
      happened is a read that is logged and a decrypt failure leaves no row claiming otherwise. The
      masked last four remain the default everywhere else, per `backend.md` section 10
- [ ] Warnings, suspensions, expulsions — `drawio`. Needs a sanction model, and there is none
- [ ] Revoke access — `platform.revoke_access`
- [ ] Membership pauses and cancellations — `platform.cancel_membership`. UC tier alone, per **C2**
- [ ] **A `platform.manage_members` codename.** The register is gated on `platform.disable_user`
      because that is the only action in the catalogue over a member's account — so correcting a
      mistyped address currently needs the authority to suspend one. `manage_cultivators` has no
      member-side twin. Splitting read from sanction belongs with the C2 tier work rather than
      ahead of it, and the gap is named in `membership/administration.py`

### Cultivators

- [ ] Cultivator CRUD — `platform.manage_cultivators`
- [ ] Cultivator user CRUD, sharing member CRUD, collection addresses — `drawio`, and see C14
- [ ] Hide a cultivator and everything it offers — `platform.hide_cultivator`
- [ ] Warnings, suspensions, expulsions

### Platform

- [x] Strain catalogue CRUD — `platform.manage_strain_catalogue`. `/api/catalogue` and the screens
      at `/admin/strains`: the catalogue list, a strain's own record, and the aroma and effect
      vocabularies. **There is no delete**, by decision: both foreign keys into a strain are
      `PROTECT`, so a strain the club has sold against cannot be removed, and retirement
      (`status = inactive`) is the whole answer — it is platform-wide through
      `CultivatorStrainListingQuerySet.visible` and it is reversible. Withdrawing a vocabulary term
      works the same way through `is_available`
- [ ] Cultivator listings, read-write. The strain screen shows every offer against a strain and is
      deliberately read-only — a grower's commercial terms are not an administrator's to edit while
      curating botanical facts. Editing one is still Django-admin-only
- [ ] Finished product type and price CRUD — `platform.manage_product_types`
- [ ] Club and platform rules. Published through the Django admin by decision; the brief says they
      need no button — `platform.manage_club_rules`
- [ ] All pricing and special offers, platform-wide — `drawio`
- [ ] Member-owned inventory view — `drawio`
- [ ] Subscription orders view — `drawio`
- [ ] Surface outstanding club document re-acceptances. `GET /api/documents/outstanding` exists
      (`app/core/documents/api.py:109`) and **no frontend caller does**, so a member owing one is
      never asked

### The two tiers — C2, C29

The UC tier has no Next.js surface. Everything below is either a model with a Django admin
registration, or already done by the Django admin that exists.

- [ ] Escalation queue: a storefront administrator raises it in Next.js, the UC operator works it in
      the Django admin — `drawio`. **The only UC-tier item with anything left to build**, now that
      the second administration band is not being built at all — see Block 2
- [x] Administrator accounts — the Django admin over `User`. `platform.manage_administrators` is not
      built and is not needed — **C29**
- [x] Membership subscription and payment management — the Django admin over `payments`.
      `platform.refund_transaction` and `platform.cancel_membership` likewise — **C29**

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

- [x] Is a sharing member a real person or a placeholder? **Decided and built in Block 0.5: a
      placeholder.** The identity number, the age rule and the POPIA attestation are gone, and the
      fixture is a nickname and a producer — **C6**
- [ ] **Everything about how a placeholder behaves in this zone was deferred here, by decision.** It
      has no personal data, no erasure path and no statutory allowance of its own, so every rule
      above that reads *sharing member* needs restating against a placeholder before it can be
      built. `sharing_member_is_complete` became `sharing_member_has_a_cultivator` for the same
      reason — orphaned stock was always the real failure, and this block is where it tightens
      against a defined feature
- [!] Is the scheme lawful — does allocating four flowering plants consume that person's own
      statutory allowance, where are the plants physically, and is a swap a sale in substance?
      **Legal opinion** — **C7**. **Changed by Block 0.5, not resolved by it**: under C6 the club
      holds the stock itself rather than allocating it to named adults, so the opinion is still
      required and still gates this block — on a different brief
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
- [!] What else does a payout need on the producer record? Block 0.5 put a collection address and
      encrypted bank details on `Producer` and **stopped there on purpose** — a tax number or a
      mandate reference would have been inventing a commercial model in a schema. Whatever this
      section decides is what adds the fields
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
- [x] A permission catalogue in code, resolution through an authentication backend, `permissions` on
      the session payload. **No role column** — it was four values under a check constraint and C28
      retired it; authority now resolves from the three relationship tables
- [x] Sharing member registration as a **placeholder** — a nickname and a producer. No identity
      number, no age rule and no POPIA attestation: C6 decided a sharing member is not a person
- [x] Member, cultivator and administrator home pages rendering from `permissions`, never from `role`
- [x] Member profile: name, nickname, mobile; avatar upload, crop and delete
- [x] Club document publication, versioning and consent ledger
- [x] Django admin over accounts, documents, subscriptions and payments
- [x] Soft delete and POPIA erasure
- [x] Administrator's membership register: `/admin/members`, read, edit, suspend and reinstate, with
      a recorded disclosure of an identity number read in full — Block 9
- [x] **Identity decomposition** — `User` reduced to an identity, with `ClubMembership`,
      `StorefrontStaff` and `ProducerMembership` carrying standing and authority. Two storefronts in
      the schema, and an unpaid registrant can sign in — Block 0.5
- [x] **`Producer`** — the farm as a record: trading name, public profile, storefronts it sells into,
      collection address, encrypted bank details, and appointments with primary, full or limited
      rights — Block 0.5
- [x] **Documents for two storefronts** — `Document` scoped by storefront with `audience` and
      `agreement`, the consent ledger, and `ProducerAgreement` for a farm's signed terms — Block 0.5
- [x] **Strain catalogue and its administrator screens** — `/admin/strains`, the strain record and
      the aroma and effect vocabularies, over `app/club/strains/api.py` — Block 1
- [x] **The plant** — model, serials, batches, ownership ledger, Excel template and batch upload,
      individual capture, stock-on-hand export, leaf rating, disable actions — Block 3
- [x] **Django and frontend layout** — `app/core`, `app/commerce`, `app/club`, `app/market`;
      `frontend` as an npm workspace root with the club application under `frontend/club` — Block 0.5

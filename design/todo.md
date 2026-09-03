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
      was not.** **Closed:** all 133 are tracked and the tree is clean — they landed in `d3731df`

- [~] Configure a real email provider — P1. **Most of the way, and the line as written was already
      wrong twice over.** It said `MAILERS` is the console backend: the console backend survives
      only under `DEBUG`, and `f2c/settings.py` `_mailer` refuses to boot a deployed environment
      that names no `EMAIL_CC_HOST` or `EMAIL_F2C_HOST`, with `_from_email` doing the same for the
      two senders. So this was never a code task and it could never have shipped silently wrong —
      it is provisioning, and the provisioning is now largely done.
      **A cPanel provider is configured for both storefronts** and the transport was corrected in
      the process: both were set to port 465 with `USE_TLS=True`, which is implicit TLS and STARTTLS
      at the same time, so a send opened a plaintext conversation on a port expecting a handshake
      and sat there until the ten-second timeout. `_mailer` does not catch that — it refuses only
      `USE_TLS` and `USE_SSL` together. Probed rather than assumed: 465 presents a certificate with
      no subject, issuer or SANs and fails verification, while 587 presents the cPanel certificate
      covering the mail host and verifies. **Both are 587 with STARTTLS now, and both mailboxes
      authenticate.**
      **`EMAIL_CC_FROM` and `EMAIL_F2C_FROM` were missing entirely**, which mattered more than the
      port: absent, `_from_email` falls back to `DEFAULT_FROM_EMAIL` under `DEBUG` — the *market's*
      address — so every club email was set to send as a domain the club's provider does not own.
      That is the failure the settings docstring names. Both senders are now the authenticated
      mailbox for their own storefront.
      One thing left, and it is not a repo change:
  - [x] **The market mailbox authenticates now.** It did not: `noreply@f2c.co.za` timed out during
        AUTH, repeatably, where `noreply@f2c-cannabis.co.za` succeeded against the same server with
        the same settings — both hosts resolve to one cPanel box, so it was always a mailbox or
        host-side matter rather than a settings one. **Re-probed on 2 September 2026 and it
        succeeds**: EHLO, STARTTLS, AUTH against `mail.f2c.co.za:587` answers `235 Authentication
        succeeded` in 0.6s with the credentials already in `.env`, and the club mailbox still does
        the same. Nothing in the repository changed to fix it. **This was the critical path in
        `deploy.md` section 1** — `MAILERS` is built for both storefronts unconditionally, so the
        API container could not start without it — and that path is now clear
  - [ ] **The deployed environments.** The eight variables per storefront are present in `.env.qa`,
        `.env.prod` and `.env.uat`, but nothing in `deploy/` or `.github/` pushes an env file to a
        Container App, so each environment still needs them set on the app itself. **Left open
        because it could not be verified rather than because it is known to be outstanding** — the
        Container App configuration was not readable from the session that closed the line above
- [x] **The test suite must not reach a mail server, and it was pointed at one** — `f2c/test_runner.py`.
      Django's `setup_test_environment` stubs `EMAIL_BACKEND`, and nothing in this project sends
      through it: mail goes per storefront through `MAILERS` and `send(using=...)`. So a developer
      with a populated `.env` had a suite aimed at a real host, and the only thing keeping it quiet
      was that almost nothing sent outside a `TestCase`, whose `on_commit` callbacks never run.
      **C32's suspension email ended that** — `accounts.tests.test_models` is a
      `TransactionTestCase`, which does run them — and the suite began opening connections to the
      provider and waiting out the timeout on each. Nothing was ever delivered, but a suite that
      tries is one that can succeed, against the addresses in the fixtures. `MailSafeRunner` points
      every alias in `MAILERS` at locmem for the duration
- [ ] **A mail outage answers 500 on two paths that have already written, and one of them is a
      dead end.** New, and found by running `/api/customers/register` against a configured SMTP
      server that was not answering. Nothing in this project sends with `fail_silently`, so a send
      that raises propagates: `POST /auth/login/start` answers 500, and so does the club's
      duplicate-registration path where `email_outstanding_checkout` runs in an `on_commit` hook.
      Both are retryable and lose nothing.
      **Customer registration was not**, and that is why it is the only one fixed: the send follows a
      row that has already committed, so a 500 goes to somebody whose account exists — and every
      retry repeats it, because the retry is a duplicate and the duplicate path emails too. It
      answers 503 with the account kept, worded so the answer is identical for a new address and one
      already on file. **The other two are left alone deliberately**, because changing `authn` and
      `payments` in passing is not the same decision: whether a sign-in code that cannot be sent
      should be a 500 or a 503 is a contract question for those endpoints' own callers. Sequenced
      with the mail provider above, since a provider that works is most of the answer
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
- [x] ~~Restrict `POST /api/auth/login` to `is_staff`~~ — **deleted instead, and the line as
      written was misleading.** It read as though members were at risk of being locked out or let in
      by this endpoint, and members never touched it: it was username-and-password sign-in, and the
      club and market frontends both sign in through `login/start`, `login/passkey`, `otp/start` and
      `otp/verify` — `frontend/club/lib/api.ts` and `frontend/market/lib/api.ts`. Its only callers in
      the repository were two lines of its own tests. Members hold an unusable password hash from
      `set_unusable_password()`, so it could never have signed one in, and staff reach Django admin
      through `/admin/login/`, which does not route through django-ninja. **So `is_staff` would have
      restricted an endpoint nobody could use to a group that does not need it.** The route, its
      `LoginIn` schema and the `aauthenticate` import are gone; `NoPasswordLoginTests` asserts the
      route answers 404 and that a staff password still authenticates, so the deletion is enforced
      rather than remembered. Closes **P5** by removal — `authentication.md` risk 5
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
- [x] **Finish what P6 started: `SITE_URL`, `APP_ENV`, `CDN_BASE_URL` and `SUPPORT_EMAIL` were
      baked at image build time — done.** P6 above moved the API address to runtime and proved one
      bundle can serve two addresses; these four did not move with it, which is why `release.yml`
      tagged every frontend image `qa-`. A frontend image could not be promoted from QA to
      Production, and R-D4 was the risk that named it.
      **It was one line per application.** `lib/site.ts` ended with
      `export const SITE_CONFIG = readSiteConfig(process.env)`, evaluated on import — and
      `next build` imports every module to analyse the route tree, so the read was a build
      requirement. It exports `siteConfig()` now, called during render, which is the shape
      `lib/api-address.ts` established: *nothing here runs at module load*.
      **Four pieces.** Both root layouts build their metadata in `generateMetadata`, because
      `export const metadata` is an object evaluated at import and `metadataBase` read `SITE_URL`.
      Both proxies call `siteConfig()` per request — which works because Next 16 defaults proxy to
      the Node.js runtime, where `process.env` is the container's; the edge runtime would have
      inlined it at build and returned a stale value without erroring. Both Dockerfiles dropped
      their `ARG`s, and `frontend/deploy/entrypoint.sh` took over the fail-fast the build used to
      give. And the `qa-` prefix went with R-D4: the registry now holds `f2c/club:<sha>` plus the
      moving `:qa`, `:uat` and `:production` tags, exactly like the API, so `promote.yml` moves the
      frontends by digest instead of rebuilding them.
      **CI is now the regression test.** The frontend job used to set four throwaway values
      because the build could not import a route without them; it sets none, so a read put back at
      module load fails the build in the same run. `deploy.md` 3, 4.2 and R-D4
- [ ] Grant the founding administrators their authority by hand — `is_staff` for the UC tier, and a
      club `StorefrontStaff` row for each club administrator. **No migration can guess which
      accounts belong in which tier**, and until somebody does it a deployed environment has nobody
      who can administer it. This was Block 2's *promote the existing administrator accounts*; C29
      turned it from a role change into a deployment step
- [x] Choose a hosting target and provision the database. **Decided, and not as written**: the
      database is MySQL 8.4 and was already built that way — `f2c/database.py`, `app/core/common/checks.py`
      and the CI job — while this line still said PostgreSQL. `uuid7` needed neither. The target is
      Azure in West Europe: three Container Apps, a managed MySQL, and — since the scheduler moved
      into Django — **two more Container Apps off the API image for the Celery worker and beat**
      rather than a Function App for the timer. `design/deploy.md` 5.2 — **C31**
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
- [x] Replace `lapse_memberships`' intended home. **Done, and not as written.** This line asked for
      a timer-triggered Function App plus a protected endpoint on the API for it to call; an earlier
      revision of `design/deploy.md` 5.2 replaced that with a Container Apps Job on a cron. The
      scheduler is now **Celery beat and a Celery worker inside the application**, on the Redis that
      was already provisioned for the throttle counters, and it covers all three of the jobs nothing
      was running — `lapse_memberships`, `purge_email_dispatches` and `purge_campaign_touches`.
      What the two external schedulers shared and Celery does not: the schedule lived in platform
      configuration rather than in a commit, a failed run was visible only in that platform's own
      logs, and neither could be exercised locally or in CI. The schedule is now
      `CELERY_BEAT_SCHEDULE` in `f2c/settings.py`, every run leaves a `scheduling.ScheduledRun` row
      in the admin, and `compose.yaml` runs the same two processes a deployment runs. No new
      authenticated endpoint was needed either way. See `f2c/queue.py` and `design/deploy.md` 5.2 —
      C31
- [ ] Build the API image in CI. **`ci.yml` runs the suite and never runs `docker build`**, so the
      only thing that exercises the `collectstatic` line in `Dockerfile` is a person running
      compose — which is how a build that had been broken since the encryption keys became
      mandatory was found. Fixed for now by putting throwaway keys on that RUN line
      (`design/deploy.md` 5.6), but the next settings-time requirement will break it the same way
      and be found the same way. One `docker build` step closes the class
- [ ] Provision the worker and beat Container Apps, off the API image, with
      `deploy/entrypoint.sh worker` and `... beat` as their arguments. **Beat must be capped at one
      replica** — it publishes on a timer with no coordination, so two of it means every scheduled
      job published twice and a `ScheduledRun` history that cannot be read. Neither app serves
      traffic and neither needs ingress — C31
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

### Access and blocks — C32

Built while closing this block, because the question *"which statuses stop a member and what are
they told"* had to be answered before the destinations could be. **C32** records the decision and
the table of the three levels.

- [x] **A blocked member reaches a screen that says so** — `/blocked`, over `clubGateFor`. It was
      the marketing landing page: no explanation, and a sign-up form they cannot use. The screen
      derives its own reason from the session rather than from a query parameter, so a visitor
      cannot choose which situation it describes, and the rule stays in one place
- [x] **A membership awaiting verification gets its own wording** rather than being lumped in with a
      block. `GateReason` went from three values to four; `not-settled-by-payment` had been doing
      duty for a conduct block, an unfinished check and a placeholder, and one reason covering three
      cases could only say something vague
- [x] **The member is emailed, and the screen states no reason** — `accounts.notifications`, two
      messages: a club suspension, club-branded, and a platform revocation that says both sites.
      Sent on commit, and a mail failure is logged rather than raised — the only place in this
      project that suppresses a send, because the block is already committed and failing the admin
      action after the fact would report a suspension that did happen as one that did not
- [x] **`SUSPENDED` out of `ACTIVATABLE_STATUSES` and out of the frontend's `PAYABLE`** — **P7**. A
      member suspended for conduct could pay the fee and be restored to Active, around
      `reinstate_member`. Nothing asserted the old behaviour, which is how it survived: 438 tests
      passed with the value removed before a single test was written for it
- [x] **`GET /api/payments/me/checkout` no longer answers 500 to the member it exists for** —
      **P8**. It called `open_subscription` unconditionally against a member who already has one.
      Found by the first test the endpoint has ever had
- [ ] **`SUPPORT_EMAIL` needs a production value** for the club deployment — a build argument on
      `frontend/club/Dockerfile`, refused if absent. The address the blocked screen offers. Belongs
      with the deployment configuration below
- [ ] **None of the mail above has been seen in a real mailbox.** It is tested against Django's
      outbox; whether it arrives, renders and survives a spam filter is not known. **No longer
      blocked** — P1 has configured a provider and both mailboxes authenticate on 587 — so this
      is one `sendtestemail` per storefront and a look at what lands. **The market half no longer
      waits on anything**: the mailbox that was failing AUTH now succeeds
- [ ] Account-level revocation is still a Django admin action with no tests of its own. The
      notification it sends is tested directly — `test_notifications` — but `suspend_accounts`
      itself, and the other two actions beside it, are not

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
      - `SUPPORT_EMAIL` is the club frontend's, not Django's — a **build argument** on
        `frontend/club/Dockerfile`, which refuses a build without it. The mailbox the blocked
        screen offers, and not the same thing as the `EMAIL_CC_FROM` sender — C32
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

**C6 was decided: a sharing member is a placeholder, not a person.** Acted on here rather than
deferred, because the deletion is free exactly once — see C6 and `verticals.md` §5.

> **Superseded.** C6 has since been **reversed**: a sharing member is a real person who does not
> transact. Everything ticked below was done, and now has to be undone. The list is kept because the
> work is real history and the restoration list points at it. See *C6 reversed* immediately after
> this block.

- [x] Drop `sharing_consent_attested_by`, `_at` and `_version` from `ClubMembership`
- [x] `sharing_member_is_complete` becomes `sharing_member_has_a_cultivator` — orphaned stock was
      always the real failure, and the swap zone can tighten it against a defined feature
- [x] Drop `erased_at` and the erasure exemption. A placeholder has no personal data to erase
- [x] `registered_by` and the nickname stay
- [x] `accounts.services.register_sharing_member` stops collecting an identity number and stops
      validating the age rule. Done under *Retire the role column* — the signature is now
      `(*, actor, producer, nickname)` and nothing else

### C6 reversed — restore the person. **Not started, and the window is open**

**The decision above was reversed on 31 August 2026.** A sharing member is a real person who does not
transact: name, identity number, nickname, an attestation by the cultivator, and — later — a
read-only login. The "no login" in `member-roles.md` was a cost control against a per-user licence on
the platform this one replaces, not a definition. See **C6**, and **C33** for who transacts on their
behalf.

**Do this while the database is still disposable.** The argument that made the deletion free — one
`0001_initial` per app and nothing to migrate — is the same argument that makes the restoration free,
and it expires the moment real sharing members exist. The read-only login does *not* expire that way
and is deliberately not in this list.

- [ ] `ClubMembership` regains `sharing_consent_attested_by`, `sharing_consent_attested_at` and
      `sharing_consent_version`, edited into `0001_initial` rather than added by a migration
- [ ] `sharing_member_has_a_cultivator` becomes `sharing_member_is_complete` again — the cultivator,
      the attestation and a nickname, with erased rows exempt
- [ ] `erased_at` and the erasure exemption come back. A sharing member is a data subject
- [ ] `accounts.services.register_sharing_member` takes `(*, actor, producer, first_name, last_name,
      id_number, nickname, attested_version)`. It validates the identity number, applies the same
      eighteen-year rule as sign-up, and refuses a duplicate in words that name no record
- [ ] `IdentityNumberUnavailable` becomes reachable again — it is defined and dead today
- [ ] `MembershipStatus.SHARING`'s label stops saying "no sign-in" as though it were permanent
- [ ] The attestation wording covers **two** facts, not one: the POPIA basis for holding the identity
      number, *and* the mandate for the cultivator to offer that person's plants — C33. Version it
- [ ] `accounts/tests/test_sharing_members.py` — `AbsenceTests` asserted the removals and must invert.
      Restore the tests deleted with C6: the attestation without which nothing is written, the age
      rule, the vague refusal, erasure
- [ ] `membership`'s `sharing_member` fixture takes a person again
- [ ] The Django admin sharing-member panel regains the attestation fields, write-only identity number
      included
- [ ] `frontend/club/components/Admin/MemberForm.tsx` — check what it collects for a sharing member
- [ ] Module and model docstrings across `accounts/services.py` and `membership/models.py` currently
      argue for the placeholder at length. They argue the wrong case now

**Deferred by decision, not forgotten:** the read-only login — sign in, see the plants you own, and
nothing that moves a plant or spends money. It costs the same whenever it is built. When it lands,
the account moves to `ACTIVE`, `UserStatus.NON_AUTHENTICATING` needs no renaming, and risk 5 closes
because the person can consent for themselves.


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
      `ClubMembership` at `SHARING`, in one transaction. **C6 is since reversed — this is undone by
      *C6 reversed — restore the person*
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
- [x] `membership`'s `sharing_member` fixture reduced to a nickname and a producer, per **C6**.
      **Reversed — the fixture takes a person again**

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

**Re-verified 1 September 2026, against the work landed since**: `manage.py test` runs **1666 tests**
and all pass; the club frontend runs **1974 tests in 107 files** and the store **353 in 23**, all
passing. The counts here and in `design/frontend.md` are the 1 September figures; the 28 August ones
above are kept because they are what closed the block.

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
      with 353 colocated tests in 23 files. Runs on port 3001. `design/frontend.md` section 11 is
      the design
- [x] **A customer registration endpoint — done.** `POST /api/customers/register`, unauthenticated,
      over `app/core/accounts/registration.py` and `registration_api.py`, mounted at `/customers`.
      **The store now takes accounts**: sign-up, then a sign-in code, then the account area, working
      end to end against a real server. 53 new tests; frontend suite unchanged at 353 and its
      contract needed no edit, which was the point of writing it first.

      It lives in `accounts` rather than in `app/market`, and the contrast with `club/membership` is
      the argument: that app owns no models and exists because its write spans two apps that must not
      know about each other, while this write is one row in this app. **A `market` app holding it
      would be an app whose only content is a function about `User`.** `app/market` stays empty.

      Four decisions inside it, each of which could have gone the obvious way and been wrong:

      - **A duplicate address is emailed a sign-in code too**, because the confirmation screen sends
        everybody to the sign-in screen to enter one — so a customer who had forgotten their account
        would otherwise be told to wait for something that never arrives. It reaches the mailbox
        rather than whoever filled in the form, which is the same channel the club uses to email a
        duplicate their outstanding payment link. A duplicate matched on the **handset** under a
        different address is sent nothing, and a **suspended** account is sent nothing: a code would
        be an invitation to nothing. The response body is byte-identical in every case, asserted on
        the bytes
      - **Publishing a market document at `agreement=at_registration` stops registration dead** with
        a 503 — `registration.ConsentRequired` — rather than creating customers recorded as having
        agreed to nothing. That publication is one action in the Django admin taken by whoever writes
        the terms, not by whoever writes the endpoint, and without the guard it would begin quietly:
        a condition no screen would show and no test would fail on. **The storefront it checks is
        named, not resolved from the host** — the club's own three seeded documents demand agreement
        at registration, so a host-scoped check would 503 the store on every unmapped host, which is
        every development machine and every preview deployment. The mirror image of the line
        `membership.services` already carries
      - **A mail outage answers 503 and keeps the account.** See the Block 0 line below — this is the
        one endpoint where that failure lands differently, and it was found by running the thing
        rather than by reading it
      - **The refusal body carries machine codes, not sentences**, which is the one place this API
        does that. The store renders its own wording keyed on the code and drops what it does not
        recognise, so prose would show a customer a blank form. `REFUSAL_CODES` is the table where
        the two vocabularies meet, and a contract test asserts every value it can emit is one the
        store renders

      The `unavailable` branch in the frontend stays, but its meaning has changed: a 404 is now a
      routing fault rather than an unbuilt endpoint, and its copy no longer promises a future opening
- [x] **A customer may manage their own profile — done, by retiring a codename.**
      `platform.manage_own_profile` was granted by an active club membership, a storefront
      appointment or a producer appointment, which was every account that could sign in until the
      market arrived. **A store customer holds none of the three, so every profile endpoint answered
      403 to a shopper asking for their own name and photograph.**

      The fix was not a wider grant. `roles.py` already said why — *a permission that everybody holds
      and nobody can be refused is not a permission* — and that is what it had become: every endpoint
      behind that screen is scoped to `request.user`, with no account identifier in any of their
      paths, so there was no object to authorise and nothing for a codename to decide. It is gone
      from the catalogue and from all three sets; `accounts.profile._require_own_account` checks for
      an active account instead, as a floor for the shell and management commands, since Django's
      session authentication has already refused an inactive account before an endpoint runs.

      - **A club member at *pending payment* gained their own profile too**, which is a correction
        rather than a side effect: they held no permissions, so they were refused their own details
        along with everything else, and somebody who has not paid should still be able to fix the
        mobile number the club will ring
      - `club-navigation.ts` grew a second legal value for `permission` — **`null`, meaning every
        signed-in account.** Exactly one destination has it and a contract test pins that list at
        one, so it cannot become a way around a missing permission. The navigation contract test
        failed the moment the codename left `roles.py`, which is the same test doing the same job it
        did for **C29**
      - `DestinationSections`' empty state is no longer reachable from `sectionsFor`: every signed-in
        account holds at least *Your account*. The branch stays and is now tested by handing the
        component no bands, because a component that renders an empty list as a blank page is worse
        than one that says the list is empty
      - Held by 13 new tests: a bare account editing its name, its avatar and reading its profile
        back, at both the service and the endpoint, plus the absence of the codename from the
        catalogue and from every granting set. `roles-and-permissions.md` §6.7 is the record
- [ ] **`platform.submit_support_request` is the same shape and was deliberately left alone.** A
      store customer cannot raise a support request either, and by the argument above raising one is
      something any account holder does rather than something a relationship grants. Not changed
      with the profile because Block 11 is unbuilt and neither storefront shows a support route, so
      nothing is refused that anybody can reach. **Decide it with Block 11 rather than in passing**,
      and the question is one line: is support a platform-level entitlement like a profile, or does
      the club answer its members and the store answer its customers through different queues — in
      which case it stays a permission and gains a market twin
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
      statement about a legal obligation.

      **Read this before publishing any of them.** Registration now refuses outright if any market
      document carries `agreement=at_registration`, so publishing the store's terms that way closes
      sign-up until `POST /api/customers/register` grows a `consents` field and the form grows the
      checkboxes to fill it. That is the intended behaviour and not a bug — the alternative is
      customers recorded as having agreed to nothing — but it makes the order compulsory: **extend
      the contract first, publish second.** A privacy notice at `agreement=none` is unaffected and
      may be published on its own today, which is the sequence to prefer
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
- [x] **How the levels of finished-product-type selection relate — decided, C18.** Four levels, not
      three: the platform catalogues the types, a cultivator's listing selects a subset, Block 3's
      plant inherits that subset with **no per-plant override**, and the member chooses one of them at
      harvest as the form the plant is delivered in — Block 6. Three narrow, one selects. The build
      already matched, so nothing changed here; the override is now closed rather than deferred, and
      the one question the entry left — reading the set live versus snapshotting it — is ruled in
      Block 5's favour of a snapshot
- [~] Administrator screens for strain and product type CRUD. Endpoint work is Block 9; the models
      are here. **Strains are done** — `/admin/strains` and the three routes under it, over
      `app/club/strains/api.py`. **Finished product types are not**, and neither is the cultivator's own
      listing screen: staff still write a listing in the Django admin
- [ ] **The cultivator's own listing screen shows that producer's listings and no other's — C12.**
      Ruled: a cultivator cannot buy, and the drawio story's "includes other cultivators' offers" is
      struck. `platform.browse_catalogue` is unchanged and still held by every appointed cultivator;
      what changes is the rows it returns to one, which is the object-level rule below and the same
      shape as `plant.stock._authorise`
  - [ ] **The price indicator that replaces the competitor view.** Each of the grower's own listings
        carries an above / in line / below marker against comparable listings site-wide. It has to be
        an aggregate **by construction**, because the alternative is a price-signalling facility
        between competitors under Competition Act s4(1)(b): a minimum cohort of independent producers
        before the marker appears at all, a cohort defined by strain, grade or product type rather
        than by cultivator, a band and never the mean or a rank, and a period average rather than a
        live one. The threshold and the period are open — **C12**

---

## Block 2 — Cultivator organisation

**The models landed early, in Block 0.5**, because the identity decomposition needed them. `Producer`,
`ProducerMembership` and the primary appointment are built, so **C13 and `roles-and-permissions.md`
risk 9 are closed** — under the role column, *only the primary may appoint staff* was an object-level
rule the catalogue could not express, and it is a column now. What is left of this block is the
endpoints and the object-level rules that arrive with them. Still a retrofit across every endpoint,
and still built after the models it scopes.

**C13 also closed the rest of the organisation, and the structure is written up in
`features/cultivator-organisation.md`.** Three rulings landed: the farm's public identity is the
primary's alone (`manage_own_cultivator_profile` moved out of the full-rights set), "as permitted by
the primary" **is** the `full`/`limited` tier rather than a per-appointment grant table, and every
plant carries a verifiable owner with a trail from capture — the ownership half is in Block 3.

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
      listings and allocation to sharing members, as against moving stock — and the primary holding
      them too, because being the primary is more than full rights rather than an alternative to
      them. **The public profile is no longer among them — C13**: the farm's identity moved to
      `PRODUCER_PRIMARY_PERMISSIONS`, because a staff appointment that can rename the farm or take it
      off the storefront is a delegation nobody asked for. The tier **is** what "as permitted by the
      primary" means, and there is deliberately no per-appointment grant beside it — that would be a
      second authorisation system every screen has to ask twice.
      **There is still no endpoint.** `platform.appoint_cultivator_staff` is in the catalogue and
      held by primaries, and the only way to exercise it is the Django admin
- [x] Collection address on the farm — `drawio`, cultivator story
- [x] Bank details on the farm — `drawio`. Encrypted through the same helper the identity number
      uses and **not** blind-indexed, because an identity number is searched and an account number is
      only ever read back; the admin renders it write-only. Settlement itself is Block 12, **C10** —
      and these are the fields a manual EFT payment run reads, which is the likely payout mechanism
- [~] **Object-level permission rules.** `RoleBackend` still refuses object-level questions outright,
      and that is now a **recorded decision rather than a gap**: a role is a fact about an account,
      not about that account's relationship to one record, so answering an object-level question from
      it would come back yes for every listing on the platform. The rules arrive with the models they
      are scoped to, and two of them have:
  - [ ] A cultivator's own listings, stock and pricing. **Now load-bearing twice over**: it is what
        scopes the cultivator's catalogue view to their own rows under **C12**, not only what stops
        one grower editing another's listing
  - [~] The sharing members that cultivator registered. **Creation is checked** —
        `register_sharing_member` refuses a primary of one farm creating a placeholder for another,
        with a superuser exemption and a test covering both. Read, update and withdraw are not, and
        cannot be until the endpoints below exist
  - [ ] A member's own inventory. **Now answerable rather than merely unwritten — C13**:
        `owner=request.user` is the holding and `tenure_by_owner` is everything that member has ever
        held. Arrives with the member-facing inventory endpoint in Block 9
  - [x] Primary versus appointed staff — the `role` column on the appointment, read in
        `permissions_for`
  - [x] The farm's own identity — `manage_own_cultivator_profile` is the primary's, so the profile
        endpoint asks the codename and then asks `ProducerMembership` whether the caller is the
        primary *of this farm*. **C13**
- [~] Sharing member registration — `accounts.services.register_sharing_member`. Built **without the
      POPIA attestation** under the superseded reading of C6. **The reversal puts it back**, widened
      to evidence the cultivator's mandate as well as the POPIA basis — C33. The signature
      `(*, actor, producer, nickname)` is not the final one
- [ ] An endpoint for registering a sharing member. The service authorises its own caller **including
      the object-level half**, so it is already the right shape to put a router in front of.
      Reachable from the admin and the shell only
- [ ] Sharing member read, update and withdraw — `platform.manage_sharing_members`
- [x] ~~Decide whether an administrator may CRUD sharing members~~ — **decided by C14: read yes,
      write no.** The product owner could name no reason for the create, the update or the delete,
      and named one for the read. §3.7's "exactly one route into a person's record" stands
      unchanged, the register's refusal to edit a sharing member stops being provisional, and the
      read is granted as `platform.view_member_inventory` — §3.8, and the build item below
- [ ] **The administrator's holdings view — `platform.view_member_inventory`, C14.** What each
      member and sharing member holds, and the `PlantOwnership` trail behind each plant. Granted in
      `ADMINISTRATOR_ACTIONS`, held by the club administration alone, and neither endpoint nor
      screen exists. `member-holdings` is its `planned` destination in `club-navigation.ts`
  - [ ] **Any holder, never a kind of holder.** The query filters on plants and their owners and
        does not ask whether the owner is a sharing member — **C33** requires the role to be
        droppable, and a branch here would be one of the branches retiring it has to delete. It is
        also what closes the older gap the decision exposed: `disable_plant` was granted with no
        screen on which to see the plant being disabled
  - [ ] **Nicknames only, and the projection is where that is enforced.** No name, no identity
        number, no blind-index reach — POPIA minimality, since oversight of stock needs no
        identity. Identity stays on the member's own record under `platform.disable_user`, where a
        full read already writes an `IdentityNumberDisclosure` row first. A serializer that selects
        `first_name` here is the defect, so the test asserts the absence
  - [ ] **The trail, not only the holding.** `tenure_by_owner` reads back to the `cultivation` row
        C13 opens at capture, so a plant reads *farm → member → member*. A view that showed the
        current holder and not how they became one would settle no dispute

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
      **C18**, and the override is now closed rather than deferred. **It reads live, and C18 has ruled
      that it should not**: the set is snapshotted onto the order in Block 5, so the docstring on
      `Plant.finished_product_types` saying the question is open is behind the register until then
- [x] Status: preflowering, in bloom, harvested, processed, shipped — `member-roles`. Plus the actual
      harvest date from `harvest.md`, tied to the status by a check constraint
- [x] Derived: cultivator pseudonym, leaf rating, days to bloom, days to harvest. The day counts are
      properties, not columns — a stored one is wrong by one every midnight
- [x] Ownership, and an ownership history that survives every transfer — `Plant.owner` for the reads,
      `PlantOwnership` as the append-only tenure log, both written by `transfer_to` in one transaction
- [x] **Every plant has a verifiable owner, and the trail starts at the farm — C13.** The ledger used
      to open at the first sale, so "who held this yesterday" was an inference from
      `Plant.listing.cultivator` rather than a record. The farm now holds a `cultivation` tenure of
      its own, opened by `Plant.save` on insert — not by the upload service, because the admin form, a
      management command and a fixture create plants too — and closed by the first transfer.
      `PlantOwnership.owner` is nullable with a nullable `producer` beside it, one of the two enforced
      by `tenure_has_one_holder`, and the reason has to agree with the holder
      (`tenure_reason_matches_holder`). `adjustment` is free in both directions so **C9**'s
      substitution can return a plant to the farm. Migration `plant/0003` backfills, and refuses to
      guess a capture date it cannot place before the first transfer
- [x] `Plant.holder` and `PlantOwnership.holder_name` — the read a screen, an export or a certificate
      uses. `owner` answers the narrower question *which member*, which is what keeps `available()` a
      one-column filter
- [x] **The four-plant statutory limit, enforced — C15.** `MEMBER_PLANT_HOLDING_LIMIT` is `4`,
      `Plant.assert_may_be_held_by` refuses a fifth, and `transfer_to` calls it — the only place
      `owner` is written, so purchase, swap, allocation and adjustment all meet one refusal. Excludes
      the plant being transferred from its own count, and never asks what kind of member holds it
      (**C33**). `accounts.SHARING_MEMBER_PLANT_ALLOCATION` now imports the same constant — C7 made
      the four the person's own ceiling, and two constants could drift. A count in Python, not a
      constraint: SQL cannot express *at most four rows per owner*, and the concurrent-transfer race
      is named and accepted
- [x] **What the four is counted over, decided and rebuilt — C16.** `HOLDING_LIMIT_STATUSES` is
      `preflowering`, `in_bloom`, `harvested` and `processed`: every plant the club is still holding
      for the member, released at `shipped`. **This reverses the reading C15 shipped** — a harvested
      plant keeps its place until it goes out for delivery, because until then it is stock the club
      has custody of and can see. `shipped` stands in for the delivery-confirmed event **C9.1** has
      not chosen; when it lands it replaces `processed` as the boundary and nothing else changes.
      `FLOWERING_STATUSES` survives and now means only what may be swapped (`harvest`), and the two
      tuples are kept apart on purpose
- [x] `Plant.objects.held_against_limit(member)` and `Plant.objects.holding_allowance_for(member)` —
      the count and *how many more may you take on*, floored at zero. What Block 5's quantity step and
      Block 10's swap screens read so a member is told before they are refused. Renamed off
      `flowering_*` with C16, because a name saying *flowering* over a count that includes harvested
      plants is the drift C15 spent a section refusing over a duplicated `4`

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
- [x] **An endpoint for either** — `app/club/plant/api.py`, mounted at `/api/stock`. `POST /plants`
      captures one, `POST /uploads` takes a workbook with a `dry_run` that validates and writes
      nothing, and `GET /template` serves the per-cultivator template so a cultivator no longer needs
      staff to run `plant_template` and email them the file. Capture only: no read, no export and no
      withdrawal, because the cultivator-facing read model is the same rows Block 5 browses for a
      different audience and deciding it here would pre-empt that
- [x] Four outcomes, four status codes. **400 for a file that is not a template** and **422 for one
      whose rows were refused** — `spreadsheet` is emphatic that a renamed heading is not a row
      anybody can fix, and one code for both would show an empty error report for the wrong file.
      A refused upload answers the *same* report shape as a successful one, so the screen has one
      renderer
- [x] The permission check for capture, and it is **two questions**. `platform.manage_plant_stock` is
      granted by every producer appointment, so on its own it would let one farm's staff load plants
      into another's inventory — the exact path `spreadsheet` says must not exist. The object-level
      half is asked against `ProducerMembership` in `plant.stock`, which is the first service to use
      what **C13** said had nothing to point at. `plant.services` stays unauthorised on purpose: it
      is what `manage.py upload_plants` shares with the endpoint, and a check inside it would have
      the command line inventing a user to satisfy
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
- [x] Set the floor. A grow price under R250 would round to **0.0**, which has no swap value at all,
      so a rating **floors at 0.1** instead — not a multiple of 0.5, so it reads as below swap value
      wherever it appears. A plant under one whole step cannot enter the swap zone:
      `Plant.assert_swappable` raises `below_swap_value` and `Plant.objects.swappable()` excludes it.
      Answered in `swap-zone.md`: pricing sits around R1,000, so this is a guard on the unexpected
      rather than a price band anybody expects to use

### Administration

- [x] Disable or remove a plant — `platform.disable_plant`. A `disabled_at` timestamp and a batch
      action, which refuses any plant a member holds: withdrawing stock is taking it off sale, and
      taking a paid-for plant back is now a **substitution** where an equivalent plant exists and a
      refund of held funds where it does not — **C9**. The refusal stands either way: withdrawal is
      not the route, because both remedies belong to the cultivator's failure path, not to an
      administrator's batch action
- [x] Disable or remove a batch — `platform.disable_batch`. Does not withdraw the batch's plants; a
      mis-numbered crop must not void stock a member has bought
- [x] Trace serials and batches — `drawio`, administrator stories. The plant admin searches on both
      identifiers, and the ownership ledger is read-only throughout
- [ ] The permission checks themselves. `platform.disable_plant` and `platform.disable_batch` are in
      the catalogue and the admin actions exist, but **nothing calls `has_perm` on either** — the
      admin authorises on `is_staff` like every other Django admin page. Waits on the endpoints in
      Block 9. The object-level half is no longer blocked on **C13**: `plant.stock._authorise` is the
      pattern, asking the codename and then the `ProducerMembership` row, and a withdrawal endpoint
      would follow it — though withdrawal is an administrator's act over any farm, so the second
      question there is a different one from capture's

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
- [ ] **The quantity step is capped by the member's remaining allowance — C15.** Four plants is a
      statutory ceiling and `transfer_to` refuses the fifth, so a member holding three who orders two
      would pay and then be refused. Read `Plant.objects.holding_allowance_for(member)` and say so on
      the step; never let the refusal first appear at the payment page
- [ ] **The step has to explain the number, not just enforce it — C16.** A harvested plant keeps its
      place until it goes out for delivery, so a member can be at the ceiling with nothing growing.
      "You may take on 0 more" with no reason attached will be read as a bug on that screen more often
      than anywhere else in the journey
- [ ] **Cart and checkout — a single full-price payment.** The member pays the whole grow price at
      order. No deposit, no balance at harvest, no receivables ledger — **C9**
- [!] **This checkout does not run on the built gateway.** The money goes to the Cultivators
      Collective's account through PayGate or Stitch, not to F2C through Payfast, and neither is
      built or chosen. It gates this block's checkout — **C10**, **C10.1**
- [ ] **Held or released state on the order**, with the event and timestamp that changed it. The club
      holds the member's money until delivery is confirmed and releases it to the cultivator then.
      Where the funds actually sit is a commercial matter and out of scope for the application; the
      state and the reporting are not — **C9**, **C10**
- [ ] **Snapshot the finished product types onto the order — C18.** What a member may choose from at
      harvest is fixed when they buy, copied off the cultivator's listing, on the same precedent as
      `payments.Subscription`: what a member agreed to is copied onto the member's own row. Today
      `Plant.finished_product_types` reads live, so a cultivator editing a listing changes what an
      existing owner may choose — including narrowing it to nothing. This is the line that makes that
      docstring's open question closed — **C18**
- [ ] **Crop failure: substitute first.** An equivalent plant — same strain, a leaf rating no lower,
      the next available harvest date. Ownership moves to the substitute serial and the held funds
      follow it, so no money moves. Refund only where no equivalent exists or the member declines —
      **C9**
- [ ] **Refund a held order, full or partial.** Moved here from Block 12 by **C11**: a refund exists
      only while the funds are held, so it operates on the same held-or-released state two lines up
      and belongs with it. Takes the order out of the hold, records amount, reason and the
      authorising administrator, returns the money. Object-level, so it needs C13 —
      `platform.refund_transaction` — **C11**, **C13**
- [ ] Order confirmation and order history

### Filters — `drawio`, member story

- [ ] By strain
- [ ] By cultivator
- [ ] By estimated harvest date
- [ ] By rating
- [ ] By top sales
- [ ] By price
- [ ] Promotions only — Block 4

### Copy this block creates — `landing`, `sign-up`

- [ ] **Say the guarantee.** The cultivator guarantees delivery and the club holds the money until it
      arrives. That is the reason a member is asked for the full price of something that does not
      exist yet, and it is said nowhere today. It belongs in the introductory copy and the sign-up
      journey — **C9**
- [ ] **Put it in the club documents, not only in the copy.** A delivery guarantee is a term of sale,
      and the sign-up documents are already versioned with a record of what a member agreed to.
      Landing copy is governed — `landing` §4 and **C20** — so the wording goes through that review
      — **C9**

### Open before this block starts

- [!] How a substitution is offered: how it reaches the member, how long they have to answer, and
      what happens in the silence. C9 decided the remedy, not the mechanic. **Answer it with the same
      rule as C8's unanswered harvest notification**, not a second one — **C9**, **C8**
- [!] Whether a substitute may come from a **different cultivator**. It changes who the held funds
      release to, which makes it a settlement question — **C9**, **C10**
- [!] **How long the funds stay held after delivery** — **C11.1**. Release is now the moment the
      member's refund right ends. Released on the courier scan, a member who opens the box to a dead
      plant has no refund at all. Recommendation: a short hold, 72 hours in shape, with a dispute able
      to suspend it. Decide with C9.1 — **C11**, **C9.1**

---

## Block 6 — Ownership, harvest and fulfilment

- [ ] Member plant inventory — plants owned, and where each is in its cycle
- [ ] Cultivator converts an estimated harvest date to an actual one — `harvest`
- [ ] Harvest notification to the owner to finalise the transaction — needs Block 8
- [ ] **Member chooses the finished product type at harvest — `product-types`, C18.** The choice is
      the fourth and last level of C18: the platform catalogues, the listing selects, the plant
      inherits, the member picks one. It is recorded **on the finalisation record, not as a column on
      the plant** — a choice has a time, an actor and a status. The list offered is the set
      snapshotted onto the order in Block 5, **intersected with the live catalogue**: a cultivator's
      later listing edit cannot reach a closed sale, but a type the platform has retired is gone for
      everyone — **C18**, **C35**
- [ ] **Delivery address model.** Does not exist. Members need to manage several — `drawio`
- [ ] Member confirms the delivery address at harvest. Months can pass between order and harvest,
      so the address is confirmed here rather than reused from the order — **C8**
- [ ] **Nothing is payable at harvest.** The finalisation screen takes no money: courier sits inside
      the price paid at order and the launch product types carry no manufacturing charge — **C8**
- [ ] Courier booking against **Pargo**, triggered by the confirmation. The booking happens here; the
      fee does not — it is separated out at settlement and remitted — **C8**, **C10**
- [ ] **Confirmation makes ownership final and removes the plant from the swap zone.** A plant is
      swappable up to harvest and not after — **C8**, and a constraint on Block 10
- [ ] Build the finalisation as a zero-total transaction with its own status, not as a form writing
      two fields. A priced product type puts a real charge on this screen — **C35**
- [ ] Plants for processing — confirmed product type and address, awaiting confirmation — `drawio`
- [ ] Ready for collection
- [ ] Delivered, proofs of delivery, delivery tracking, escalations — `drawio`
- [ ] **Delivery releases the cultivator's money.** The held funds from the order are released on
      confirmed delivery — **C9**, **C10**
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
- [!] What happens when the owner never confirms. Harvest to delivery is the longest silence in
      the journey and nothing ships without an address, so the plant sits in a cultivator's
      storage. Reminders then default, reminders then administrator escalation, or an
      indefinite hold — three different products. Answer before specifying this block — **C8**
- [!] **Which event confirms delivery** — it releases the held funds and, since **C16**, frees a
      place on the member's four. One event, two consumers, and an argument for one column rather than
      two — **C9.1**. Preference: Pargo's
      delivery or collection scan, because it needs no member action. Fallbacks are a member
      confirmation, which strands a cultivator's payment in silence, or automatic release after a
      fixed window with a dispute path that does not exist. Cannot be fixed until the Pargo
      integration is understood. **C11 has raised the stakes** — release ends the member's refund
      right, so the window and its dispute path are the member's protection rather than a courtesy —
      **C9**, **C11.1**
- [!] How a priced finished product type is paid for. Not in the MVP, but it lands on this
      screen the moment oil or gummies are listed — **C35**. It is a second payment for something
      delivered later, so decide then whether the same hold-until-delivery rule applies to it — **C9**
- [!] **What happens when every type a member was sold has since been retired by the platform.** C18
      snapshots the available set onto the order and intersects it with the live catalogue at
      finalisation, so the intersection can come back empty. It is the same hold, substitute or refund
      branch C35 owns, without the money — and a silent default into whatever is left is the one
      answer that is wrong — **C18**, **C35**

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

**C5.** The brief heads its administrator section "Admin (NextJs)". **Three of the thirty
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
      (**C14** has now decided, and the answer is that they may not — read yes, write no), and an
      administrator suspending themselves — that one signs the caller out and leaves nobody able to
      undo it
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
- [x] ~~Membership cancellations — `platform.cancel_membership`~~ — **struck by C29.** The codename
      left `ADMINISTRATOR_ACTIONS` in Block 0.5 and `test_roles` asserts it is absent, so cancelling
      a membership is a Django admin operation under `is_staff` and not an endpoint. This line read
      *UC tier alone, per C2* and **contradicted the two-tiers section at the foot of this block**,
      which had already recorded the removal
- [ ] **Membership pauses — never a codename, and never a state either.** Nothing in the catalogue
      names one and `MembershipStatus` has no paused value: it carries pending, pending payment,
      active, suspended, lapsed and sharing. Suspension is a sanction and lapsing is non-payment;
      **a pause is neither**, so pausing rather than lapsing is a new decision and a new state, not
      a permission somebody forgot to build
- [ ] **A `platform.manage_members` codename.** The register is gated on `platform.disable_user`
      because that is the only action in the catalogue over a member's account — so correcting a
      mistyped address currently needs the authority to suspend one. `manage_cultivators` has no
      member-side twin. Splitting read from sanction belongs with the C2 tier work rather than
      ahead of it, and the gap is named in `membership/administration.py`

### Cultivators

- [ ] Cultivator CRUD — `platform.manage_cultivators`
- [ ] Cultivator user CRUD and collection addresses — `drawio`. **Sharing member CRUD has left this
      line: C14 grants the read and refuses the three writes**, so what an administrator gets is the
      holdings view under Members above, not a fourth CRUD screen here
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

**No longer gated.** C7 is decided as residual risk: the swap model is in use by other clubs and
treated as defendable, and a sharing member's four flowering plants consume their own statutory
allowance. A legal opinion is still worth having on the proxy leg and on where the plants physically
sit (R-C7.1, R-C7.2), and it blocks nothing.

**Both prerequisites that arrived with that answer are met.** The four-plant holding check became a
statutory ceiling rather than a convention, so it was a precondition of this block rather than a rule
inside it — and **C15 built it**, in `Plant.transfer_to`, counting plants per member and **never
branching on what kind of member** (C33 requires this role to be droppable, and a branch on owner type
is exactly what would have to be deleted to drop it). **C16 then decided what it counts, against the
reading C15 shipped**: every plant the club still holds for the member, released at dispatch rather
than at the cut.

What this block still owes the rule is the *prompt*: a member at the ceiling should be offered a trade
down, not only refused — and since C16 the prompt has to handle the case where there is no trade to
offer, because a member's four have all been harvested and a harvested plant cannot be swapped.

- [ ] Swap zone listing. **No Rand values anywhere in it** — `swap-zone`
- [ ] Leaf rating displayed on every plant in the zone
- [ ] An explanation of how the leaf rating works — `drawio`, member story
- [ ] Sharing-member stock seeds the zone. Four plants per sharing member —
      `platform.allocate_sharing_member_stock`. `SHARING_MEMBER_PLANT_ALLOCATION` is the person's own
      statutory ceiling (C7) and is now `MEMBER_PLANT_HOLDING_LIMIT` imported; allocating a fifth
      is already refused by `transfer_to` — **C15**. The allocation stays spent through harvest and
      processing, not released by the cut — **C16**
- [ ] The cultivator offers and swaps a sharing member's plants; the sharing member does neither —
      **C33**. When the read-only login lands, revisit: a person who signs in can withdraw their own
      plant, which is most of R-C7.1 gone
- [ ] Confirmed swaps for mature plants, instant swaps for everything else — **C17**. The member story
      draws the instant/confirmed distinction already, and this moves it off owner type and onto the
      plant. The cultivator confirms on a sharing member's behalf (**C33**); a member confirms their
      own. Detail in the C17 items at the end of this block
- [ ] Members offer their own plants, and withdraw them again —
      `platform.offer_inventory_for_swap`
- [ ] Equivalent leaf-value matching
- [ ] Explicit acknowledgement when a member accepts a lower-valued request and forfeits the
      difference — `swap-zone`
- [x] Four-plant holding check, enforced on the write — **C15**, in `transfer_to`, so a swap that
      would leave a member overstocked is already refused with the remedy named in the message.
      Counting harvested and processed plants too — **C16**
- [ ] Prompt a member to trade a flowering plant for a pre-flowering one before refusing —
      `stock-holding-limit`. The refusal exists and names the remedy; the screen that *offers* it,
      reading `holding_allowance_for`, is the part this block owes
- [!] **The prompt has to handle the case C16 leaves with no move.** A member holding four harvested
      plants cannot trade one out — swapping requires a flowering plant (`harvest`,
      `assert_swappable`) and the count now includes harvested ones — so the screen has to say *wait
      for your delivery* rather than offer a trade that will be refused. There is no fix inside the
      ruling: letting a harvested plant into the zone contradicts `harvest`, not counting it
      contradicts **C16**
- [!] **Sequence a swap as release-then-acquire.** `assert_may_be_held_by` excludes only the plant
      being transferred, so a member at the ceiling is refused if the incoming leg runs first and
      permitted if the outgoing leg does. True before **C16** and now biting on more swaps, because a
      flowering-for-harvested trade is a counted plant for a counted plant. It is a rule about the
      order of two writes inside one service
- [ ] No swapping after harvest for paying members — `harvest`. The trigger is the owner's harvest
      confirmation: confirming product type and address makes ownership final and takes the plant out
      of the zone — **C8**
- [ ] A sharing member's harvested item may sit in the zone; a member swapping for it locks in and
      receives the harvested plant — `harvest`. Not an exception to the line above: sharing-member
      stock has no confirming owner (**C33**), so the swap comes first and the new owner confirms
      afterwards — **C8**
- [ ] Swap audit trail, and ownership history through every swap
- [ ] Administrator oversight: manage plants in the zone, handle disputes, moderate listings

### Open before this block starts

- [x] Is a sharing member a real person or a placeholder? **Decided as a placeholder, built, then
      reversed: a real person who does not transact** — **C6**. The identity number, the age rule and
      the POPIA attestation come back; the read-only login is specified and deferred. The restoration
      list is *C6 reversed — restore the person*, in Block 0.5
- [x] **What a sharing member is, and what they hold here.** Deferred here under the placeholder
      reading and answered by the reversal instead: a real person, four flowering plants against
      their own allowance, offered on their behalf by the cultivator — C6, C7, C33. The rules above
      that read *sharing member* mean a person, and need no restating
- [ ] **C34 is the one this block should not discover for itself**: a sharing member who wants to
      join the club properly is refused at sign-up by their own record, and their allowance is
      already spent. Open, and cheap while sharing members are few
- [x] Is the scheme lawful — does allocating four flowering plants consume that person's own
      statutory allowance, where are the plants physically, and is a swap a sale in substance?
      **Decided as residual risk — C7.** Yes to the first, which makes C15 a prerequisite. The second
      is argued on private cultivation plus ownership attaching at flowering, and carried as R-C7.2.
      The third is a swap: the model is in use by other clubs and defendable, mitigated by keeping
      the leaf rating a rounding of a disclosed price and moving **no money in the zone**
- [x] Does a harvested plant count toward the four? **Decided and rebuilt — C16. It does**, until
      the plant goes out for delivery, because until then it is stock the club is holding and can
      see. This reversed the recommendation C15 had already shipped, and the check was changed with
      the ruling. The swap `harvest` permits is not thereby refused — it is refused only for a member
      already at the ceiling, which is the holding rule working. Two consequences are accepted: a
      member's grow cycle no longer overlaps their delivery window, and a member holding four
      harvested plants has no swap available and waits. `shipped` stands in for the delivery-confirmed
      event **C9.1** has yet to choose
- [x] Equal-value matching versus maturity. Leaf rating derives from grow price alone, so a plant
      three weeks from harvest and a seedling of the same price trade at par, and everyone wants the
      mature side. **Decided — C17. Maturity stays out of the leaf rating** and a mature plant is
      swapped for by request and confirmation. The formula in `swap-zone` is untouched, because the
      rating being a rounding of a disclosed price is the whole of R-C7.3's mitigation and a
      multiplier would have taken it away — while still not deciding which of four members gets the
      plant. Nothing was built, so nothing is rebuilt: this is a rule this block is written against
- [ ] **Confirmation reads the plant, not its owner — C17.** Harvested stock, or a plant close to its
      estimated harvest date, is confirmed; everything else is instant. The member story drew that
      line on owner type — instant for sharing members' plants, confirmed for members' — and C33
      forbids owner-type branching here so the role stays droppable. Same shape as the holding count:
      per plant and per member, never per kind of member
- [ ] **The cultivator confirms, not the sharing member — C33.** The read-only login gains no swap
      action, no withdrawal and no approval queue; the confirmer is the cultivator who allocated the
      stock, holds it and attested at registration. This widens **R-C7.1**: the proxy now chooses the
      counterparty as well as making the offer. Held by two things — a confirmation is a yes or no on
      a swap the member proposed, never a price or a counterparty the cultivator sets, and a decline
      is recorded
- [ ] **A swap request holds the offered plant rather than transferring it**, so the same plant cannot
      sit in two live requests. Release-then-acquire on confirmation, per C16 above
- [ ] **An unanswered request lapses** and the offer returns to the zone. C8's unanswered harvest
      notification is the same failure on a longer clock, and it is open there too
- [ ] **C17.1 — where "mature" starts, and how long a request may sit.** This block's own number to
      set, not a question for the business. Recommendation: harvested always, otherwise within 21 days
      of the estimated harvest date off `Plant.days_to_harvest`; a club rule rather than a constant if
      it will be argued about. **It is the dial between an instant path that exists and one that does
      not** — a sharing member's four plants are *flowering* plants, so a threshold set at "in bloom"
      confirms every swap in the zone and costs the liquidity C33 protected
- [x] Household and dried-weight limits are not modelled. **Decided and built — C15.** Four
      flowering plants per member are enforced on the write; the household limit and the dried-weight
      limit are accepted risks (R-C15.1, R-C15.2) with a third named beside them (R-C15.3: the four
      is per adult, not per club). The reason is stated rather than engineered around — the platform
      cannot observe what a member holds off-platform, the household version cannot be attempted
      without collecting a third party's personal information POPIA §10 does not permit, and a check
      that only catches the honest produces a record of a control that never ran. The club rules
      carry it, and the copy is drafted in `conflict.md`

---

## Block 11 — Support

- [ ] Support tickets, raised by members and by cultivators —
      `platform.submit_support_request`
- [ ] Ticket status tracking and responses
- [ ] Contact us page
- [ ] Rules and guidelines page. **It carries the two limits the platform does not enforce — C15.**
      Four plants are enforced; the household limit, the dried-weight limit and plants held through
      any other club are the member's own responsibility, and the page says so plainly rather than
      implying the club polices them. **Two paragraphs of C15's drafted copy are superseded by C16**
      and the replacement is in the C16 entry: a harvested plant keeps counting until it goes out for
      delivery, harvesting frees no place, and the page says out loud that this is the club's own rule
      and stricter than the law requires. Drafted copy is in `conflict.md`; it is a
      club document under the copy-governance rules, not a hero paragraph
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

**Substantially answered by the product owner, and the remainder is smaller.** The money map: the
membership fee is collected by **F2C** through Payfast and split 40% F2C / 60% Cultivators Collective;
everything else a member buys is collected by the **Cultivators Collective** through PayGate or Stitch,
with a **15% commission** to F2C. The ratios themselves are out of scope for the application. Still a
launch blocker for cultivators, because nothing here pays one.

- [x] Does the platform collect and remit, or introduce and invoice a commission? — **both.** It
      collects and remits the membership fee; it invoices a commission on everything else — **C10**
- [x] What is the platform's take — **15% of a member transaction, 40% of the membership fee** — **C10**
- [!] **Is the commission visible to the cultivator?** Recommendation: yes, and as an amount rather
      than a rate. A statement showing gross, commission, courier and net is the only kind that
      reconciles — **C10**
- [!] **What base is the 15% taken on?** C8 puts courier inside the price the member pays, so 15% of
      the delivered price and 15% of the price net of courier are different sums. Same question for
      VAT-inclusive versus exclusive — **C8**, **C10**
- [ ] **Record the commission as an amount on the transaction**, at the time it is taken. A fact, not
      a policy: no rate table, no configuration screen, no split engine, and the statement still adds
      up — **C10**
- [ ] **Record which gateway and which account took the money.** Two legal entities reconcile their
      banking off the same table — **C10**, **C10.1**
- [x] When does a cultivator earn — **at delivery**. The member pays in full at order and the club
      holds the money until delivery is confirmed — **C9**. Which event counts as confirmed is still
      open: **C9.1**, in Block 6
- [ ] **Statement of account carries three lines, not one: held, releasable, paid.** Funds held
      against a plant still in the ground are not a cultivator's earnings and must never be shown as
      them — **C9**
- [ ] **Reconciliation to whatever account holds the cash is a finance process the platform reports
      into.** The escrow arrangement itself is out of scope for the application — **C9**
- [!] What else does a payout need on the producer record? Block 0.5 put a collection address and
      encrypted bank details on `Producer` and **stopped there on purpose** — a tax number or a
      mandate reference would have been inventing a commercial model in a schema. Whatever this
      section decides is what adds the fields
- [ ] Statement of account, payments due, record payments made — `drawio`
- [!] **Payout mechanism — the whole of the remaining gap.** Payfast collects and does not disburse;
      PayGate and Stitch are candidates for collection, not payout — **C10**
- [ ] **Build the payment run, not a payout integration.** On the working assumption of a manual EFT
      run: a payable list per cultivator per period, the released orders behind each line, and a
      recorded payment against it. That is `drawio`'s "record payments made", and the encrypted bank
      details Block 0.5 put on `Producer` are what it reads — **C10**
- [!] **When the commission is earned, forced by C11.** Refunds are possible only before release, so
      a commission earned at order means the club pays 15% on money it gives back. **Recommendation:
      earned on release**, the same event that pays the cultivator. Free now, expensive later —
      **C10**, **C11**
- [ ] **An adjustment line on the payment run** — amount, reason, authorising administrator. C11's
      post-release remedy is the Collective withholding from what it owes a cultivator. Without a
      line for it somebody edits a total by hand the first time it happens — **C10**, **C11**
- [!] **The market's leg is not answered at all.** The money map is written in club terms. A farmer
      selling honey is not a club member and the Collective is not an obvious party to that sale —
      whose account collects, whether the 15% applies, and who is the seller of record for
      mostly zero-rated produce. The market trades first — **C10**, **C26**

### The second gateway — C10.1

**Build work, not a question about the brief.** Payfast is the only money path in the system and it
bills exactly one thing. Member purchases settle into a **different legal entity's** account. Belongs
in Block A with the payment intent — deciding it later means writing the checkout twice.

- [!] **PayGate or Stitch — decide.** Not interchangeable: PayGate is a hosted card gateway of the
      Payfast kind, Stitch is API-first and leads with pay-by-bank. The choice decides the checkout's
      shape and how much ledger the platform holds itself. **It no longer gates refunds** — C11 keeps
      them inside the hold, and an EFT out of the club's own account works where a reversal does not —
      **C10.1**
- [ ] Second merchant account, second credential set, second notification endpoint. `payfast_config`
      is a single-gateway assumption with one merchant identity in it — **C10.1**
- [ ] The payment layer stops being "the Payfast integration" and becomes a gateway per money flow —
      **C10.1**
- [ ] Not scoped. No integration document for either candidate has been read — **C10.1**

### Refunds — C11

**Decided, and most of this section was deleted rather than done.** A refund exists only while the
money is still in the Cultivators Collective's account — before it is released to the cultivator.
After release there is no refund in the application. The build that is left moved to **Block 5 →
Block A**, beside the hold it operates on.

- [x] **Who refunds — the Cultivators Collective**, which holds the money and is the seller of record
      — **C10**, **C11**
- [x] ~~Partial reversal with transaction and platform fees withheld~~ **A partial refund is a partial
      release of a held amount**, not a reversal of a settlement. "Fees withheld" now means the
      collecting gateway's own fee, which is sunk. `amount_fee` and `amount_net` are already stored
      for it — **C11**
- [x] ~~Who carries a refund when the cultivator has already been paid~~ **Nobody: it cannot happen.**
      A refund never touches released money, so there is no clawback and no negative settlement line
      — **C9**, **C11**
- [x] ~~A member account credit ledger~~ **Not built.** Where the Collective compensates a member
      after release it does so directly, off the platform. No balance per member, no expiry position,
      no POPIA record to survive erasure, no liability on the books — **C11**
- [x] ~~The mechanism waits on C10.1~~ **It does not.** A refund lands on a recent unsettled
      transaction in the club's own account; where the gateway will not reverse, an EFT out of the
      same account does it — **C10.1**, **C11**
- [ ] **The refund action itself** — full or partial, on a held order, recording amount, reason and
      the authorising administrator. Tracked in Block 5 → Block A, not here —
      `platform.refund_transaction` — **C11**, **C13**
- [!] **How long the funds stay held after delivery** — **C11.1**. The open residue, and it carries
      the risk. Instant release on the courier scan leaves the ordinary complaint with no refund.
      Recommendation: a short hold, 72 hours in shape. Decide with **C9.1**
- [!] **A dispute has to suspend the release.** No dispute path exists, and it is now the member's
      protection rather than a tidy-up on the auto-release option — **C9.1**, **C11.1**
- [!] **Never publish "no refunds after delivery" as a term.** The CPA gives a six-month implied
      warranty with the choice of refund, repair or replacement, and section 51 forbids contracting
      out of it. The rule is a settlement design and is fine to build; as a published term it is void
      and it invites a complaint. Club documents say how to raise a problem and how long an answer
      takes — **C11**
- [!] **The post-release path needs an owner, a response time and a written outcome.** "The NPC could
      withhold" is a discretion, and a consumer right is not discretionary. Residual risk in the
      manner of C7 — **C11**
- [!] **The market's leg is the exposed one.** Honey is delivered in days, so the hold is short and
      produce is perishable food. And C10 has still not named who collects on the market, so there is
      no account for a market refund to come out of — **C10**, **C26**, **C11**

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
      number, no age rule and no POPIA attestation: C6 decided a sharing member is not a person.
      **C6 has since been reversed** and this has to be undone — *C6 reversed — restore the person*
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

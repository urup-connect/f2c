# Deploying to QA

What has to exist on Azure before anybody outside the team can see this platform, which
configuration entry carries which fact, and where each one is stored.

This document describes a deployment that **does not exist yet**. Every other document in this set
describes the system as it stands; this one is the exception, and it is written as a runbook rather
than as a description. It is the expansion of Block 0 in [`todo.md`](todo.md), which counts the
outstanding items but does not say how to discharge them.

The target is decided and recorded in [`conflict.md`](conflict.md) **C31**: Azure in West Europe,
three Container Apps, an Azure Database for MySQL Flexible Server 8.4, an Azure Managed Redis. The
hostname split is **C30**. Neither is reopened here.

---

## 1. What is left, and what shape it is

Block 0's remaining lines split three ways, and the proportions are worth stating because they
decide who does the work:

- **Provisioning.** None of the Azure resources exist. This is an afternoon with a subscription and
  a credit card, plus DNS propagation.
- **Configuration.** Roughly fifty-five entries across three containers. Sections 3 and 4 are the
  list.
- **Code.** Four small items, in section 5. None is more than an hour, and one of them is not in
  `todo.md` at all.

**The critical path is not any of them.** It is a mailbox. `noreply@f2c.co.za` times out during
`AUTH` against the same cPanel server that `noreply@f2c-cannabis.co.za` authenticates against, and
`f2c/settings.py` builds `MAILERS` for **both** storefronts unconditionally — `_mailer` refuses a
deployed environment naming no `EMAIL_F2C_HOST`, and `_from_email` does the same for the sender.
So the API container does not start until the market mailbox works, **whether or not the market
frontend is deployed at all**. The store being on the back burner does not move this off the path;
it only makes it look as though it should be. Raise it with the provider first, because it is the
one item that sits in somebody else's queue.

---

## 2. The resources

One resource group per environment, `rg-f2c-qa-weu`, West Europe throughout.

| Resource | Sizing and notes |
| --- | --- |
| Container Registry | One registry shared by QA and production. Basic tier. Geo-replication is a Premium feature and there is one region |
| Azure Database for MySQL Flexible Server 8.4 | Burstable B2s for QA. Database `f2c`. `require_secure_transport` stays **ON** — `f2c/database.py` refuses a deployment that names neither a CA bundle nor an explicit disable |
| Azure Managed Redis | **Not** Azure Cache for Redis. The Basic, Standard and Premium tiers retire on 30 September 2028, and provisioning onto a retiring product to save a week is a migration bought on credit. TLS only, port 10000 |
| Storage account | Two blob containers, `cc-documents-qa` and `cc-avatars-qa` |
| Container Apps environment | With a Log Analytics workspace |
| Container App — API | `min-replicas 1`, pinned |
| Container App — club frontend | Port 3000 |
| Container App — market frontend | Optional in QA. See section 7 |
| Container Apps Job | Cron, running the API image. See section 5.2 |

**`min-replicas 1` is not a performance setting.** Scale-to-zero plus the four DNS lookups in
`payfast_addresses` risks timing out an inbound Payfast notification, and a dropped notification is
a member who paid and was not switched on — C31. The cost of a warm replica is smaller than the
cost of one unactivated membership.

**Two blob containers, not one, and they may not be merged.** `avatars_storage_config` refuses a
configuration where `DJANGO_AVATAR_STORAGE_CONTAINER` equals `DJANGO_DOCUMENT_STORAGE_CONTAINER`.
The documents container is fronted by a CDN and serves unsigned, permanently cacheable URLs; an
avatar is only ever streamed by an endpoint that checked the session first. Putting them together
publishes every member's photograph, and the refusal is there because the mistake is quiet.

**Blob storage is not optional here, although the code treats it as optional.** Both storage
modules fall back to the local filesystem when no container is named, which is what lets the whole
upload, crop and serve feature be developed with no cloud account. A Container Apps filesystem is
ephemeral: on that fallback every uploaded document and avatar disappears with the revision that
wrote it.

### Hostnames

Four for a full QA, all inside the two production registrable domains:

```
qa.f2c-cannabis.co.za        club frontend
qa-api.f2c-cannabis.co.za    API, club host
qa.f2c.co.za                 market frontend
qa-api.f2c.co.za             API, market host
```

Both `qa-api` names are custom domains on the **same** API container app; `DJANGO_STOREFRONT_HOSTS`
is what maps each to a storefront.

**The API has to sit inside each frontend's registrable domain, and that is C30 rather than a
preference.** The session cookie is `SameSite=Lax`. A club frontend at `qa.f2c-cannabis.co.za`
calling an API at `qa-api.f2c.co.za` makes every authenticated request cross-site, the cookie is
not sent, and the symptom is that sign-in appears to succeed and nothing after it works. A QA
environment on a single throwaway domain would reproduce nothing and would fail in exactly the way
production must not.

### Storage credentials: managed identity, not keys

`azure-identity` is already a dependency, and both `documents/storage.py` and `accounts/storage.py`
fall back to `DefaultAzureCredential` when a container and an account are named and no secret is.
Give the API container app a system-assigned managed identity and grant it **Storage Blob Data
Contributor** on the storage account.

That is the path the code prefers and the reason is in its own docstring: an account key in
application settings is a key that has to be rotated, copied between environments, and kept out of
screenshots. It also removes four entries from section 4.

---

## 3. Where configuration lives

Four stores, and nothing new in the repository. `.env` stays local and untracked; `.env.example`
remains the documentation and needs no change for this.

| Store | Holds | Why there |
| --- | --- | --- |
| **Azure Key Vault** | `DJANGO_FIELD_ENCRYPTION_KEY`, `DJANGO_BLIND_INDEX_PEPPER` | These two are Block 0 P4. Key Vault gives versioning, soft delete and purge protection, which is most of the backup and rotation procedure P4 asks for. Referenced from the container app through the same managed identity that reaches blob storage |
| **Container App secrets** | Every other secret: database password, Redis URL, mail passwords, Payfast key and passphrase, `DJANGO_SECRET_KEY` | Referenced from environment variables as `secretref:`. A second Key Vault hop for these buys little — they are all rotatable without touching stored data, which is exactly what the two above are not |
| **Container App environment variables** | Everything else: hosts, origins, flags, amounts, addresses | Non-secret, and visible in the portal is the right property for them. A wrong `DJANGO_ALLOWED_HOSTS` should be readable by whoever is debugging it |
| **GitHub Actions environment `qa`** | The frontend **build arguments**, plus registry credentials | `SITE_URL`, `APP_ENV`, `CDN_BASE_URL` and `SUPPORT_EMAIL` are evaluated by `lib/site.ts` when the module is first loaded, which happens during prerendering. They belong to the build, not to the container app |

**The consequence of that last row is worth stating rather than discovering.** Because those four
are build arguments, **a QA frontend image cannot be promoted to production** — each environment
builds its own. The API image is environment-agnostic and can be promoted, which is what Block 0 P6
bought when `NEXT_PUBLIC_DJANGO_API_URL` became `DJANGO_API_PUBLIC_URL`. The frontends did not get
the same treatment because `SITE_URL` is wrong in a way that shows up in a canonical tag, and the
API address was wrong in a way that broke every request after sign-in.

---

## 4. The configuration entries

### 4.1 The API container

**Core**

```
DJANGO_ENV=qa
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=                                              secret
DJANGO_ALLOWED_HOSTS=qa-api.f2c-cannabis.co.za,qa-api.f2c.co.za
DJANGO_BEHIND_PROXY=true
DJANGO_CSRF_TRUSTED_ORIGINS=https://qa.f2c-cannabis.co.za,https://qa.f2c.co.za
DJANGO_CORS_ALLOWED_ORIGINS=https://qa.f2c-cannabis.co.za,https://qa.f2c.co.za
```

**`DJANGO_ENV` takes `qa` or `prod`. The frontend's `APP_ENV` takes `local`, `qa` or
`production`.** Two vocabularies one letter apart, on two containers in the same environment, and
each fails somewhere different: `database_config` raises on an unrecognised value, `readAppEnv`
throws during prerendering. There is no good reason for the divergence; it is recorded here because
correcting it now would touch the CI workflow, `compose.yaml` and both frontends for cosmetic gain.

**`DJANGO_BEHIND_PROXY=true` is the single highest-consequence entry in this document.** Container
Apps ingress is a reverse proxy, so `REMOTE_ADDR` is Envoy; without this, `verify_notification`
refuses the source address of every Payfast notification and no membership ever activates. It is
one variable rather than two because Django's `SECURE_PROXY_SSL_HEADER` and the Payfast source check
are the same deployment fact. **Forgetting it no longer reaches production** — `payments.W001`
fires on `check --deploy`, and `deploy/entrypoint.sh` runs that at `--fail-level WARNING` before
uvicorn starts, so the revision never serves. Recognise the failure for what it is: the container
will not start, and that is the gate working.

**Database**

```
DJANGO_DB_HOST=<server>.mysql.database.azure.com
DJANGO_DB_PORT=3306
DJANGO_DB_NAME=f2c
DJANGO_DB_USER=
DJANGO_DB_PASSWORD=                                             secret
DJANGO_DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt
```

The runtime image installs `ca-certificates`, which carries the DigiCert roots Flexible Server
chains to, so that path is correct as written and needs nothing mounted. `tls_options` reads it and
sets `VERIFY_IDENTITY`.

**Leave `DJANGO_DB_SSL_DISABLED` unset.** Setting it is how a server with no certificate is
reached; on Flexible Server it downgrades a verified connection to an unverified one, which is the
state the connection was in before this was fixed — encrypted, unverified, and saying so nowhere.

**Cache**

```
DJANGO_REDIS_URL=rediss://:<access-key>@<name>.westeurope.redis.azure.net:10000/0    secret
```

`rediss://`, not `redis://`. `f2c/cache.py` refuses the plaintext scheme in a deployed environment
because the Azure access key is in the URL and would travel in clear. Leave
`DJANGO_CACHE_ALLOW_PLAINTEXT` unset — it exists for the local compose stack.

**Storefronts and passkeys**

```
DJANGO_STOREFRONT_HOSTS=qa-api.f2c-cannabis.co.za=club,qa-api.f2c.co.za=market
DJANGO_DEFAULT_STOREFRONT=club
DJANGO_WEBAUTHN_RP_ID=qa.f2c-cannabis.co.za
DJANGO_WEBAUTHN_RP_IDS=club=qa.f2c-cannabis.co.za,market=qa.f2c.co.za
DJANGO_WEBAUTHN_RP_NAME=Cultivators Collective (QA)
DJANGO_WEBAUTHN_ORIGINS=https://qa.f2c-cannabis.co.za,https://qa.f2c.co.za
DJANGO_DEFAULT_FROM_EMAIL=no-reply@f2c-cannabis.co.za
```

`DJANGO_STOREFRONT_HOSTS` names the hosts **Django** answers on — the API hostnames. The
`WEBAUTHN` entries name the hosts the **browser** shows — the frontend hostnames. They are
different lists in this deployment, and swapping them produces a system where sign-in fails and the
unauthenticated document endpoints serve the wrong storefront's documents.

**Set the RP IDs to the QA hostnames rather than to the bare registrable domains.** Both validate —
an RP ID may be a parent of the frontend host — but a passkey enrolled against
`f2c-cannabis.co.za` is presentable at the production frontend. Scoping QA credentials to QA costs
nothing now and is not recoverable later, because the enrolments already exist by then. Suffixing
the RP name means a tester's authenticator says which environment is asking.

**Field-level encryption — Key Vault**

```
DJANGO_FIELD_ENCRYPTION_KEY=
DJANGO_BLIND_INDEX_PEPPER=
```

**Generate fresh values for QA and never copy production's down.** The field key is the only thing
between a QA database restore and every identity number the club holds. Generate them with
`design/tools/generate_keys.py`, which emits both plus `DJANGO_SECRET_KEY` in `.env` form and
checks each against the rules `crypto._decode_key` enforces:

```
python design/tools/generate_keys.py              # all three, .env format
python design/tools/generate_keys.py --field      # one value, bare, for piping
python design/tools/generate_keys.py --self-test  # prove the generator, print no secret
```

The equivalent single value, if the script is not to hand — it is what the settings' own refusal
message tells you to run:

```
python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

**Storage**

```
DJANGO_DOCUMENT_STORAGE_CONTAINER=cc-documents-qa
DJANGO_DOCUMENT_STORAGE_ACCOUNT=stf2cqaweu
DJANGO_AVATAR_STORAGE_CONTAINER=cc-avatars-qa
DJANGO_AVATAR_STORAGE_ACCOUNT=stf2cqaweu
DJANGO_CDN_BASE_URL=
```

No account keys, no SAS tokens, no connection strings — naming an account and no secret is what
selects the managed-identity path.

`DJANGO_CDN_BASE_URL` is left blank in QA unless the documents container is actually fronted. If it
is set it must be `https` outside local development, and its path must be either empty or exactly
the container name: an Azure blob URL always carries the container as its first path segment, and
django-storages replaces only the host. A base whose path names something else describes an address
that does not exist, and the symptom is every document link 404ing after a deploy.

**Email — eight entries per storefront**

```
EMAIL_CC_HOST=            EMAIL_F2C_HOST=
EMAIL_CC_PORT=587         EMAIL_F2C_PORT=587
EMAIL_CC_USER=            EMAIL_F2C_USER=
EMAIL_CC_PASSWORD=        EMAIL_F2C_PASSWORD=                   secret
EMAIL_CC_USE_TLS=true     EMAIL_F2C_USE_TLS=true
EMAIL_CC_FROM=            EMAIL_F2C_FROM=
EMAIL_DISPATCH_RETENTION_DAYS=365
CAMPAIGN_TOUCH_RETENTION_DAYS=730
```

587 with STARTTLS, which was established by probing rather than by assumption: 465 on this provider
presents a certificate with no subject, issuer or SANs and fails verification, while 587 presents
the cPanel certificate covering the mail host and verifies.

**Do not set `USE_SSL` alongside `USE_TLS`.** `_mailer` refuses the pair, and the earlier fault was
worse than a refusal: port 465 with `USE_TLS=true` opens a plaintext conversation on a port
expecting a handshake and sits there until the ten-second timeout.

**`EMAIL_*_FROM` is required and has no useful fallback.** Absent, `_from_email` falls back to
`DEFAULT_FROM_EMAIL` under `DEBUG` and raises otherwise. Under `DEBUG` that fallback is the
*market's* address, which is how every club email came to be set to send as a domain the club's
provider does not own.

**The `F2C` block is section 1's blocker.** Both prefixes are read at settings load, so the API
does not boot without them.

**Payfast**

```
DJANGO_PAYFAST_MERCHANT_ID=                                     secret
DJANGO_PAYFAST_MERCHANT_KEY=                                    secret
DJANGO_PAYFAST_PASSPHRASE=                                      secret
DJANGO_PAYFAST_SANDBOX=true
DJANGO_PAYFAST_RETURN_URL=https://qa.f2c-cannabis.co.za/signup/paid
DJANGO_PAYFAST_CANCEL_URL=https://qa.f2c-cannabis.co.za/signup/cancelled
DJANGO_PAYFAST_NOTIFY_URL=https://qa-api.f2c-cannabis.co.za/api/payments/payfast/notify
DJANGO_MEMBERSHIP_CHECKOUT_URL=https://qa.f2c-cannabis.co.za/pay
DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT=150.00
DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY=monthly
DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES=0
DJANGO_MEMBERSHIP_SUBSCRIPTION_ITEM_NAME=Club membership
DJANGO_MEMBERSHIP_SUBSCRIPTION_DESCRIPTION=Cultivators Collective membership subscription
```

The return and cancel URLs are **frontend** addresses; the notify URL is the **API's** public
address and must be reachable from the internet, because it is the only thing that activates a
membership. The passphrase is required rather than optional and not only for the signature: Payfast
will not accept a subscription from a merchant with no passphrase set, so an integration without one
fails at the checkout instead of at startup.

`DJANGO_PAYFAST_SANDBOX` defaults to sandbox when unset, in every environment. Live is never reached
by leaving a variable blank.

### 4.2 The club frontend container

**Build arguments**, set in the pipeline, baked into the image:

```
SITE_URL=https://qa.f2c-cannabis.co.za
APP_ENV=qa
CDN_BASE_URL=<static host>
SUPPORT_EMAIL=members@f2c-cannabis.co.za
```

Built from the `frontend/` context, not from `frontend/club/` — that is where the lockfile and the
hoisted `node_modules` live, and `next.config.ts` pins `outputFileTracingRoot` to the same place.
`SITE_URL` and `SUPPORT_EMAIL` are both hard-checked in the Dockerfile so the failure names the
build argument the operator actually set.

**Runtime**, on the container app:

```
DJANGO_API_URL=https://f2c-api.internal.<env-name>.westeurope.azurecontainerapps.io
DJANGO_API_PUBLIC_URL=https://qa-api.f2c-cannabis.co.za
PORT=3000
```

`DJANGO_API_URL` is how the Next.js server reaches Django over the container network.
`DJANGO_API_PUBLIC_URL` is what the root layout renders into the document for the browser, and it
must sit inside the same registrable domain as `SITE_URL` — section 2's hostname rule, C30.

Omitting `DJANGO_API_PUBLIC_URL` answers 500 on the first request that names it, rather than
defaulting to localhost as the pre-P6 code did.

### 4.3 The market frontend container

The same shape, with two differences. `SITE_URL=https://qa.f2c.co.za`,
`DJANGO_API_PUBLIC_URL=https://qa-api.f2c.co.za`, and **no `CDN_BASE_URL` or `SUPPORT_EMAIL` build
arguments** — the market Dockerfile takes neither, because the club film and the
blocked-membership screen are both the club's.

---

## 5. What has to be built or changed first

### 5.1 The Django admin had no static files — done

There was no WhiteNoise in `MIDDLEWARE` and no `collectstatic` in the API Dockerfile.
`django.contrib.staticfiles` serves `/static/` only under `DEBUG`, and it does so by overriding the
`runserver` command rather than by adding a URL — so under uvicorn with `DEBUG=False`, every admin
stylesheet and the whole brand skin in `static/cc_admin/` answered 404. `STATIC_ROOT`'s own comment
said as much, and nothing wrote to it.

**Under C29 the Django admin is the operator tier**, so this was not cosmetic: it is the surface the
UC administrators work on, and the fallback for everything the twenty-seven unbuilt destinations do
not cover yet.

What was done, four files:

- `whitenoise[brotli]` in `pyproject.toml`, `requirements.txt` and `poetry.lock`. The extra is what
  writes `.br` files at collect time; without it the same backend writes gzip only.
- `whitenoise.middleware.WhiteNoiseMiddleware` directly below `SecurityMiddleware` in `MIDDLEWARE`,
  which is the only correct position — above it a static response would skip the SSL redirect and
  the HSTS header, further down every stylesheet request would run sessions, auth and CSRF.
- `STORAGES['staticfiles']` is now `whitenoise.storage.CompressedManifestStaticFilesStorage`, so
  each file is served under a content-hashed name with a one-year immutable cache header and a
  changed asset changes its URL. Nothing has to be invalidated at the CDN, and nothing is served
  stale. Under `DEBUG` Django hands back the unhashed name, so a developer who never runs
  `collectstatic` is unaffected.
- `collectstatic --noinput --clear` in the Dockerfile's runtime stage, after `USER f2c`, so the
  tree is owned by the user that serves it and is baked into the image rather than rebuilt on every
  container start. It runs with a throwaway `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=1` — not because
  `collectstatic` reads either, but because `f2c/settings.py` refuses to import without the key and,
  with `DEBUG` off, without every Payfast variable as well. A `RUN`-line variable does not persist
  into the image.

`whitenoise.runserver_nostatic` is in `INSTALLED_APPS` above `django.contrib.staticfiles` so local
development is served by the same middleware as QA, and `deploy/entrypoint.sh`'s `dev` branch now
collects before it starts `runserver` — compose mounts a named volume over the image's
`staticfiles/`, so without that the local admin would be the thing rendering unstyled.

**It also turned up a fault in the suite, which is fixed.** Django's test runner turns `DEBUG` off,
which makes the manifest backend strict, and no test run writes a manifest — so `f2c/test_runner.py`
pins the plain backend for the duration. That alone left two tests failing and only in some orders,
which is how the real problem showed itself: `DocumentsTestCase` enabled a `MEDIA_ROOT` /
`MEDIA_URL` / `STORAGES` override in `setUpClass` and disabled it inside `tearDownClass`, while the
`@override_settings(PAYFAST=…)` on `PaymentsTestCase` — a subclass of it — is entered by Django on
unittest's class-cleanup stack and unwound *after* `tearDownClass`. Disabling out of order restored
a snapshot taken while the documents override was live, so it came back and stayed: **every test
that ran afterwards was reading a temporary `MEDIA_ROOT` and a storages dict nobody had asked
for.** Invisible while both staticfiles backends were the same object, and a decision about what
was being tested once they were not.

The override now goes on the same stack via `cls.enterClassContext(...)`, and the runner fails the
run if `settings._wrapped` is not the object it was before the tests. Verified by putting the old
code back: the guard names `MEDIA_ROOT, MEDIA_URL, STORAGES` and exits non-zero.

Recorded here rather than in `todo.md` because it was found while writing this document, and
because it is a deployment fault rather than a product one: nothing about it was visible locally,
where `DEBUG` is on and the file is served.

### 5.2 The scheduler is a Container Apps Job, not a Function App

`todo.md` carries a timer-triggered Function App plus **a protected endpoint on the API for the
Function to call**, on the reasoning that packaging Django into the Function App would mean a second
deployment artefact on a preview Python runtime. Both halves of that are avoidable.

`deploy/entrypoint.sh` already passes any unrecognised argument straight through to `manage.py`. So
a **Container Apps Job** on a cron schedule, running the same API image with the command as its
argument, is the whole mechanism: one artefact, no preview runtime, and no new authenticated
endpoint to write, test and defend.

```
lapse_memberships          daily
purge_email_dispatches     nightly
purge_campaign_touches     nightly
```

Until something runs the first of these, an unpaid membership keeps access indefinitely — Block 0
P2. The other two are the retention periods `EMAIL_DISPATCH_RETENTION_DAYS` and
`CAMPAIGN_TOUCH_RETENTION_DAYS` name; neither enforces itself.

**This supersedes the Function App line in `todo.md` and the docstring in `lapse_memberships`**,
which still says "a daily cron or an Azure App Service WebJob".

### 5.3 The founding administrators, granted by hand

After the first successful migration: `is_staff` for the UC tier, and a club `StorefrontStaff` row
for each club administrator. **No migration can guess which accounts belong in which tier**, and
until somebody does it a deployed environment has nobody who can administer it. This was Block 2's
*promote the existing administrator accounts*; C29 turned it from a role change into a deployment
step.

### 5.4 The flaky nickname test — C25

`frontend/club/app/api/nickname/availability/route.test.ts` asserts that a random hex string does
not contain `500`, `503`, `429` or `422` — all valid hex — so it fails about one run in thirty. Fix
it before CI starts gating deployments, because a pipeline that goes red at random is a pipeline
nobody reads.

### 5.5 The mail-outage 500s — not a QA blocker, but QA will meet them

`POST /auth/login/start` and the club's duplicate-registration path both answer 500 when the SMTP
server is configured and not answering, because nothing in this project sends with `fail_silently`.
Both are retryable and lose nothing, which is why they were left alone: whether a sign-in code that
cannot be sent is a 500 or a 503 is a contract question for those endpoints' own callers, and
customer registration was fixed only because its send follows a row that has already committed.

A QA environment standing up against a provider still being argued with will hit both.

---

## 6. The order

1. **Raise the `noreply@f2c.co.za` mailbox with the provider.** Section 1. It is on the critical
   path and it is in somebody else's queue, so it starts first regardless of what else is ready.
2. Provision the resource group, registry, MySQL, Managed Redis, storage account and Log Analytics.
   No containers yet.
3. Fix the flaky test (5.4), wanted before the first deploy rather than after it. The static files
   (5.1) are done.
4. Create the Key Vault, generate the QA encryption keys, load the secrets.
5. **Deploy the API container app alone**, with `min-replicas 1`. The entrypoint gate reports each
   misconfiguration by name — that is what it is for, and it is cheaper to meet it with one
   container running than with three.
6. DNS and TLS for the two club hostnames. Build and deploy the club frontend.
7. Grant the founding administrators (5.3). Then walk the whole journey: emailed sign-in code,
   passkey enrolment, sign-up, Payfast sandbox checkout, membership activation, profile edit,
   `/admin/members` and `/admin/strains`.
8. Add the Container Apps Job (5.2).
9. Market hostnames and container, if QA is to carry the market at all — section 7.
10. Write up the key procedure (R-D2) and the transborder disclosure (R-D1) before any environment
    holds a real member.

Steps 1 to 8 are about a week of elapsed time, most of it waiting on DNS, TLS and the provider
rather than on work.

---

## 7. Open decisions

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | The QA hostnames | `qa.` and `qa-api.` inside the two production registrable domains, as section 2 sets out. Anything that puts the API outside the frontend's registrable domain breaks the session cookie and reproduces nothing — C30 |
| D2 | Whether QA carries the market storefront at all | **Skip it while the store is on the back burner.** It saves a container app, two DNS records and a certificate. It saves **none** of the `EMAIL_F2C_*` entries — the API needs those to boot either way, which is section 1 |
| D3 | Payfast sandbox or live in QA | **Sandbox.** Live in QA moves real money on a test environment. The cost is that the production credentials are first exercised in production, which is an argument for one deliberate live transaction at cutover rather than for a live QA |
| D4 | Key Vault, or container app secrets alone | **Key Vault for the two encryption keys**, container app secrets for everything else. It is one resource and a role assignment, and it discharges most of P4 |
| D5 | Whether the frontends' `APP_ENV` and Django's `DJANGO_ENV` should share a vocabulary | Leave them. Correcting `prod` to `production` touches the CI workflow, `compose.yaml` and both frontends for no behavioural gain. Documented in 4.1 instead |

---

## 8. Risks

- **R-D1. West Europe puts members' identity numbers outside South Africa.** Lawful under POPIA
  s72(1)(a), but it has to appear in the privacy notice and the PAIA manual before real members are
  on the environment. QA with synthetic data does not need it; the promotion to production does —
  C31. **Open.**
- **R-D2. Losing `DJANGO_FIELD_ENCRYPTION_KEY` destroys every stored identity number with no
  recovery path** — Block 0 P4. Key Vault with purge protection covers storage and versioning. What
  it does not cover, and what still has to be written down, is who holds break-glass access, how a
  rotation re-encrypts existing rows, and what the recovery drill is. **Open.**
- **R-D3. Migrations run in the API container's entrypoint, and Container Apps starts a new
  revision before retiring the old one.** So a schema change has to be readable by the revision
  still serving traffic. This is a real constraint on what may go in a migration and it is taken
  knowingly: a separate migration job is a second deployment artefact and a second thing to forget.
  Revisit when there is more than one replica starting at once. **Accepted.**
- **R-D4. A QA frontend image cannot be promoted to production**, because `SITE_URL`, `APP_ENV`,
  `CDN_BASE_URL` and `SUPPORT_EMAIL` are build arguments — section 3. What is deployed to production
  is therefore not the artefact that was tested, only the same commit rebuilt. **Accepted**, and the
  mitigation is that the three values which differ are all addresses rather than behaviour.
- **R-D5. The QA environment has its own encryption keys, so a production backup cannot be restored
  into it to reproduce a fault.** That is the point of separate keys and the trade is deliberate:
  reproducing a production data fault in QA would mean QA holding production identity numbers.
  **Accepted.**

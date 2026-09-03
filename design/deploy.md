# Deploying to QA, and promoting to UAT and production

What has to exist on Azure before anybody outside the team can see this platform, which
configuration entry carries which fact, where each one is stored, and how a release moves from
one environment to the next.

**For the steps and the configuration entries alone, see [`deploy-quickstart.md`](deploy-quickstart.md).** This document is the reasoning behind them, and is the place to look when a value seems arbitrary or a step seems skippable.

This document describes a deployment that **does not exist yet**. Every other document in this set
describes the system as it stands; this one is the exception, and it is written as a runbook rather
than as a description. It is the expansion of Block 0 in [`todo.md`](todo.md), which counts the
outstanding items but does not say how to discharge them.

The target is decided and recorded in [`conflict.md`](conflict.md) **C31**: Azure in West Europe,
three Container Apps, an Azure Database for MySQL Flexible Server 8.4, an Azure Managed Redis. The
hostname split is **C30**. Neither is reopened here.

---

## 1. What is left, and what shape it is

Block 0's remaining lines split four ways, and the proportions are worth stating because they
decide who does the work:

- **Provisioning.** None of the Azure resources exist. This is an afternoon with a subscription and
  a credit card, plus DNS propagation.
- **Configuration.** Roughly fifty-five entries across three containers. Sections 3 and 4 are the
  list.
- **Code.** Four small items, in section 5. None is more than an hour, and one of them is not in
  `todo.md` at all.
- **Delivery.** Three GitHub Actions workflows and three shell scripts, in section 6. **Written,
  and the only part of this document that describes something that exists.** What it still needs
  is the one-time Azure and GitHub setup that 6.5 and 6.6 set out, which cannot be done before
  the registry in step 1 exists.

**The critical path used to be none of them, and that has changed.** It was a mailbox.
`noreply@f2c.co.za` timed out during `AUTH` against the same cPanel server that
`noreply@f2c-cannabis.co.za` authenticates against, and `f2c/settings.py` builds `MAILERS` for
**both** storefronts unconditionally — `_mailer` refuses a deployed environment naming no
`EMAIL_F2C_HOST`, and `_from_email` does the same for the sender. So the API container could not
start until the market mailbox worked, **whether or not the market frontend was deployed at all**,
and it sat in the provider's queue rather than the team's.

**It authenticates now.** Re-probed on 2 September 2026: EHLO, STARTTLS and `AUTH` against
`mail.f2c.co.za:587` answer `235 Authentication succeeded` in under a second, with the credentials
already in `.env` and no repository change. **Nothing on this deployment now waits on anybody
outside the team**, so the items above are the whole of it and the order in section 7 is
decided by what the team can do first, not by what it is waiting for. The dependency itself has not
gone away — the API container still refuses to start without a working market mailer, deployed
market frontend or not — so a mailbox that stops authenticating stops the API, and that is worth
knowing before it is diagnosed as a container fault.

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
| Container App — market frontend | Optional in QA. See section 8 |
| Container App — Celery worker, mail worker and beat | Three more, off the API image, and none of them serves traffic. Superseded the Container Apps Job earlier revisions named — see section 5.2 |

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
| **GitHub Actions environments `qa`, `uat` and `production`** | The container app names, the resource group, and the three Azure identifiers the federated credential is minted against | Everything here names something a *workflow* has to address; nothing here is read by a running container. It used to hold the frontend build arguments as well — see below. Section 6.6 is the list, and there are no registry credentials among them — 6.5 |

**Every artefact is environment-agnostic, and the third row is where all three get their
environment.** `f2c/api`, `f2c/club` and `f2c/market` each read what distinguishes a QA deployment
from a production one out of their own container app at start-up or at render time, so one image
serves all three environments and a promotion moves it unchanged.

**This is recent, and the previous arrangement is worth recording because the pipeline still carries
its shape.** The API got there first, under Block 0 P6, when `NEXT_PUBLIC_DJANGO_API_URL` — inlined
into the browser bundle by `next build` — became `DJANGO_API_PUBLIC_URL`, read on the server per
request. The frontends did not follow at the time, and kept `SITE_URL`, `APP_ENV`, `CDN_BASE_URL`
and `SUPPORT_EMAIL` as build arguments, because `lib/site.ts` read them at module load and
`next build` loads every module to analyse the route tree. So a QA frontend image could not be
promoted; each environment built its own. That was R-D4, and it is now closed: `lib/site.ts` exports
`siteConfig()`, called during render, and the four are container app environment variables in 4.2
and 4.3.

**What the closure cost, and where it was put back.** A build argument that nobody set failed the
build, named itself, and never reached a registry. A container setting that nobody sets fails at
whichever request first reads it — and for `SUPPORT_EMAIL` that is the blocked-membership screen,
reached by a member the club has already shut out and by nobody else, so the container could look
healthy for weeks. `frontend/deploy/entrypoint.sh` closes that: it checks the names in `REQUIRED_ENV`
and refuses to start the server without them, which is what `deploy/entrypoint.sh` already does for
Django. Container Apps then holds the previous revision serving traffic while the new one fails.

**What it did not buy back is a check on a value that is set and wrong.** `APP_ENV` decides
indexing, so a production container carrying `qa` serves `noindex` and a QA container carrying
`production` invites the crawlers in — neither of which fails anything. That is the same class of
exposure as a wrong `DJANGO_ALLOWED_HOSTS`, and it is handled the same way: by checking after a
promotion rather than by refusing to deploy. `deploy-quickstart.md` step 12 carries the two `curl`
lines.

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
throws during render. There is no good reason for the divergence; it is recorded here because
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

**No build arguments.** The image takes none, which is what makes it the same image in every
environment. Built from the `frontend/` context, not from `frontend/club/` — that is where the
lockfile and the hoisted `node_modules` live, and `next.config.ts` pins `outputFileTracingRoot` to
the same place.

**Runtime**, on the container app — all of it:

```
DJANGO_API_URL=https://f2c-api.internal.<env-name>.westeurope.azurecontainerapps.io
DJANGO_API_PUBLIC_URL=https://qa-api.f2c-cannabis.co.za
SITE_URL=https://qa.f2c-cannabis.co.za
APP_ENV=qa
CDN_BASE_URL=<static host>
SUPPORT_EMAIL=members@f2c-cannabis.co.za
PORT=3000
```

The last four were build arguments until R-D4 closed; `lib/site.ts` reads them during render now.
**The container refuses to start without any of them**, naming the one it is missing —
`frontend/deploy/entrypoint.sh`, and `REQUIRED_ENV` in the Dockerfile is the list. The gate checks
presence only: whether `SITE_URL` is an origin rather than a path, whether `CDN_BASE_URL` is `https`
outside local development and whether `SUPPORT_EMAIL` could be an address are all judged by
`lib/site.ts`, and a second copy of those rules in shell would be a second thing to keep in step.

`DJANGO_API_URL` is how the Next.js server reaches Django over the container network.
`DJANGO_API_PUBLIC_URL` is what the root layout renders into the document for the browser, and it
must sit inside the same registrable domain as `SITE_URL` — section 2's hostname rule, C30.

Omitting `DJANGO_API_PUBLIC_URL` answers 500 on the first request that names it, rather than
defaulting to localhost as the pre-P6 code did. **Neither API address is in `REQUIRED_ENV`**, and
the difference is how loudly each fails: the root layout reads `DJANGO_API_PUBLIC_URL` on every
page, so an unset one is a 500 on the first request anybody makes and a start-up gate would announce
nothing that was not about to announce itself.

### 4.3 The market frontend container

The same shape, with two differences. `SITE_URL=https://qa.f2c.co.za`,
`DJANGO_API_PUBLIC_URL=https://qa-api.f2c.co.za`, and **no `CDN_BASE_URL` or `SUPPORT_EMAIL`** —
`market/lib/site.ts` reads neither, because the club film and the blocked-membership screen are both
the club's. Its `REQUIRED_ENV` is `SITE_URL APP_ENV`.

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

### 5.2 The scheduler is Celery inside the application, not a Function App and not a job

Three things on this platform are computed rather than driven by an event, and none of them runs
itself:

```
lapse_memberships          daily     02:30 UTC / 04:30 SAST
purge_email_dispatches     nightly   01:00 UTC / 03:00 SAST
purge_campaign_touches     nightly   01:20 UTC / 03:20 SAST
```

Until something ran the first, an unpaid membership kept its access indefinitely — Block 0 P2. The
other two are the retention periods `EMAIL_DISPATCH_RETENTION_DAYS` and
`CAMPAIGN_TOUCH_RETENTION_DAYS` name; neither enforces itself, and a retention policy nobody runs is
a retention policy nobody has.

**This section has now been wrong twice.** `todo.md` carried a timer-triggered Function App plus a
protected endpoint on the API for the Function to call, on the reasoning that packaging Django into
the Function App would mean a second deployment artefact on a preview Python runtime. This section
then replaced that with a **Container Apps Job** on a cron schedule running the same API image with
the command as its argument — one artefact, no preview runtime, no new authenticated endpoint. That
was a real improvement and it was still the wrong shape, for three reasons that the Function App
and the Job share:

* **The schedule lives outside the repository.** In both designs, *when* a member loses access is a
  cron expression in platform configuration. It is not in a commit, it is not in a review, and it
  does not appear in a diff. `git log` cannot answer "when did we change the lapse time, and why".
* **A failed run is visible only in that platform's own logs.** A Job that exits non-zero at 02:30
  is an exit code in Container Apps' execution history, retained on that platform's terms. Nobody
  taking a call from a member who says "I was switched off and I had paid" is going to find it, and
  there is nothing to hand a POPIA enquiry that asks how the retention window is enforced.
* **Neither can be exercised anywhere but a deployment.** No developer and no CI run has ever
  executed a Container Apps Job. The first real run of a schedule nobody can rehearse is in
  production, against members' access.

**Celery replaces all three properties.** The schedule is `CELERY_BEAT_SCHEDULE` in
`f2c/settings.py`, reviewed as code. Every run writes a `scheduling.ScheduledRun` row — task,
started, finished, outcome, how many rows it touched — readable in the admin months later by
whoever takes the call. And `compose.yaml` runs the same worker and the same beat a deployment runs,
so a task can be written, triggered and watched on a developer's machine.

`f2c/queue.py` carries the argument at length, including why the broker is Redis database 1 derived
from `DJANGO_REDIS_URL` rather than a separate managed service: the Redis is already there for the
throttle counters, so the queue costs nothing new to provision.

**And then email joined the queue, which is the second reason this section exists.** Sends used
to happen in the request that asked for them: a ten-second SMTP timeout inside the sign-in path,
against a provider nobody here operates, on the one route into an account that has no passkey
yet. A refused message got no second attempt. `app/core/storefronts/mail.py` carries that
argument; what it means for a deployment is a third container and one hard rule about which
queue consumes what.

**What this needs from the platform.** Three more Container Apps off the same image, and none of
them serves traffic:

```
worker       deploy/entrypoint.sh worker       1..n replicas   consumes: scheduled
mail-worker  deploy/entrypoint.sh mail-worker  1..n replicas   consumes: mail
beat         deploy/entrypoint.sh beat         exactly 1 replica
```

**Two queues, and the reason is a login outage rather than tidiness.** A worker runs one task at
a time — `CELERY_WORKER_PREFETCH_MULTIPLIER` is 1 — and the two nightly purges are long delete
passes bounded at twenty-five minutes, running at 01:00 and 01:20 UTC. On a single shared queue,
a sign-in code requested at 01:05 waits behind the housekeeping. That is not a slow email; it is
a member who cannot get in. `CELERY_TASK_ROUTES` sends `storefronts.deliver_email` to `mail` and
everything else to `scheduled`, and each container names its queue with `--queues` so neither
can quietly start eating the other's work.

**`mail-worker` is on the critical path for authentication, and nothing else in the stack will
say so when it is down.** That is the cost of moving the send off the request: the API answers
normally, `/auth/otp/start` returns 200, and `EmailDispatch` rows accumulate on `queued` while no
member without a passkey can sign in. `EmailDispatch.objects.pending()` is the query that shows
it — a count that is nonzero and rising, rather than a handful of rows a second old — and it is
the one worth alerting on. Watching `failed()` alone would show nothing at all.

**All three worker apps need the API's full configuration, not a subset.** It is tempting to give a
process that serves no traffic a trimmed environment — no `ALLOWED_HOSTS`, no CORS origins, no
Payfast variables. That fails at start-up, because all three run `check --deploy --fail-level
WARNING` and Django's deployment checks do not know or care that these processes have no ingress.
It would also be wrong if it worked: a worker writes to the same tables the API does, and every
value that decides *what* it writes — the database, `DJANGO_DEFAULT_STOREFRONT`, both retention
windows, and for `mail-worker` the whole of `MAILERS` and `STOREFRONT_FROM_EMAIL` — is read from
the environment. A worker configured differently from the API is a worker doing the wrong thing to
real records, quietly and overnight; a mail worker configured differently is one sending a club
sign-in code through the market's provider, which is the single thing a member is taught to
distrust about a one-time code. `compose.yaml` enforces this locally with a YAML anchor: the three
services take the API's environment block verbatim rather than a copy that can drift.

**`mail-worker` may be scaled, and unlike the scheduled worker it probably should be.** Its
concurrency is `CELERY_MAIL_CONCURRENCY`, defaulting to 4: the work is a blocking socket read
rather than a database pass, so one process waiting out an unresponsive provider should not stop
three others sending. Replicas are safe for the same reason — every task carries one message and
settles one row.

**`beat` must be capped at one replica, and that is a hard constraint rather than a preference.**
Beat publishes on a timer with no coordination between instances, so two of it means every job
published twice. Nothing is corrupted — all three scheduled tasks are idempotent, which is also
what makes `CELERY_TASK_ACKS_LATE` safe — but each duplicate writes its own `ScheduledRun` row and
the history stops being readable, which is the one thing the table exists for.

**`storefronts.deliver_email` is the exception to that idempotence, and it says so at the task.**
Sending the same message twice is a member receiving two sign-in codes or two suspension notices,
so it sets `acks_late=False` on itself against the global default: a worker killed mid-hand-over
loses the send rather than repeating it. The loss is visible — the row stays `queued` — and a
duplicate would not be, because two rows would both look correct. Beat never publishes it, so the
replica cap above has nothing to do with this one.

Both processes run `check --deploy --fail-level WARNING` before starting, exactly as `serve` does.
That is the reason they live in `deploy/entrypoint.sh` rather than being given their own command
lines in platform configuration: the worker reads the same settings the API reads and is wrong in
the same ways, and it is the process that changes member access with nobody watching.

Neither runs `migrate`. The API container applies migrations; a worker that also ran them would be a
second process racing the first through the same schema change on every deployment.

**This supersedes both the Function App line in `todo.md` and the Container Apps Job described in
earlier versions of this section**, along with the docstring in `lapse_memberships`, which used to
say "a daily cron or an Azure App Service WebJob".

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

### 5.6 The API image could not build — done

`docker compose up --build` failed on the `collectstatic` line in `Dockerfile`, with:

```
DJANGO_FIELD_ENCRYPTION_KEY and DJANGO_BLIND_INDEX_PEPPER must both be set
```

**Three correct decisions produced a broken build between them**, which is why this went unnoticed
and is worth recording rather than just fixing:

* `f2c/settings.py` refuses to load without both encryption keys, **unconditionally — there is no
  `DEBUG` exemption**. That is right: a backend that boots with encryption misconfigured writes
  plaintext or crashes at the first identity capture (`backend.md` section 3.3).
* `.dockerignore` excludes `.env` from the build context. Also right — `settings.py` calls
  `load_dotenv` at import, so a `.env` inside the image is live configuration, and a developer's
  holds real SMTP passwords and real storage keys.
* The `collectstatic` RUN line supplied `DJANGO_SECRET_KEY` and `DJANGO_DEBUG` and nothing else, on
  a comment that said those were the only two settings.py needs to import. That comment was wrong,
  and nothing tested it: **CI never builds the image.** It runs the suite on MySQL and does not
  `docker build`, so the only thing that exercises this line is a person running compose.

Fixed by giving the build its own throwaway pair of 32-byte keys on the RUN line, beside the
throwaway secret key that was already there — not by weakening the refusal, and not by letting `.env`
into the image. A RUN-line variable does not persist into the image, and none of the four is what a
container runs with.

**The gap this left open was that CI did not build the image, and that is now closed.**
`release.yml` builds and pushes all three on every merge to trunk — section 6 — so the next
settings-time requirement breaks a build in CI rather than on the machine of whoever next runs
compose. It is still not caught on the pull request that introduces it: the build runs after the
merge, because pushing to the registry from a workflow triggered by a fork is the permission this
pipeline deliberately does not grant (6.1). A build-only job on pull requests, pushing nothing,
would close that too and is not written.

---

## 6. The pipeline

Three workflows and three shell scripts, and one fact shapes all of them: **every image can be
promoted between environments, so a release is built once and moved.** Section 3 has why — nothing
environment-specific is baked into any of the three — and everything below is a consequence.

This was not always true, and the shape of what follows is partly the shape of what it replaced.
Until R-D4 closed, the frontends baked four values and had to be rebuilt per environment, so
`promote.yml` took a commit rather than an image and the frontend tags named an environment. The
commit input stayed; the environment prefix did not. Where a paragraph below explains why something
is the way it is, the reason may be the old constraint rather than a current one, and it says so.

| File | Trigger | What it does |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Pull requests, pushes to trunk, and a call from the two below | The whole suite against MySQL 8.4. Unchanged except for the `workflow_call` trigger that lets the other two reuse it |
| `.github/workflows/release.yml` | Push to trunk, or dispatch | Works out which of the three images the commit changed, builds and pushes those, deploys them to QA |
| `.github/workflows/promote.yml` | Dispatch only, taking a commit SHA and a target environment | Moves all three digests to UAT or production. Nothing is rebuilt |
| `.github/scripts/deploy-api.sh` | Called by both | Rolls one API digest across the four container apps that run it, in the one order that works |
| `.github/scripts/acr-digest.sh` | Called by both | Resolves a tag to the digest it points at |
| `.github/scripts/azure-oidc-setup.sh` | By hand, once per environment | The application registration, the federated credential, the two role assignments and the GitHub variables |

**Trunk-based, with the environments as the gates rather than the branches.** A merge to `master`
builds and deploys QA on its own; UAT and production are `promote.yml` dispatches behind GitHub
environment reviewers. **The `qa` branch is redundant under this and should go** — a long-lived
environment branch drifts from trunk, and what eventually reaches production is then a merge commit
nothing ever tested as one. Worth noting in passing that `ci.yml` has never run on that branch
anyway: its push trigger is `[main, master]`.

### 6.1 The build is a second workflow, not more jobs in `ci.yml`

Three reasons, and none of them is a preference:

- **`ci.yml` runs on `pull_request`, forks included.** Pushing to the registry needs
  `id-token: write` and an `AcrPush` role assignment, and that pairing does not belong on a workflow
  whose trigger includes code nobody has reviewed yet.
- **`ci.yml` sets `cancel-in-progress: true`.** That is right for a test run and wrong for a push: a
  build cancelled halfway through leaves partly pushed layers and an environment tag pointing at
  neither the old image nor the new one. Weakening it for the build would weaken it for the tests,
  which is the one place it earns its keep.
- **The triggers do not overlap.** Tests want every pull request; images want a merge to trunk. One
  file means every job carries an `if:` guard, and the guards are where a pipeline like this rots.

**The tests still gate the build, and there is still only one definition of green.** `ci.yml` gained
a `workflow_call` trigger; `release.yml` calls it, and every build job is `needs: test`. Nothing is
copied between the two files, so what CI proves cannot fall out of step with what a release proves.

**One footgun, recorded because it costs an hour to diagnose.** In a called workflow
`${{ github.workflow }}` evaluates to the *caller's* name. `ci.yml` groups its concurrency on that
expression, so a caller declaring the same group would sit waiting on a group it was itself holding
until the run timed out. Both callers use a literal prefix — `release-`, `promote-` — for that
reason and no other.

### 6.2 What the registry holds

One registry for every environment, as section 2 sets out. Three repositories:

```
f2c/api      :<sha>   plus the moving tags :qa :uat :production
f2c/club     :<sha>   plus the moving tags :qa :uat :production
f2c/market   :<sha>   plus the moving tags :qa :uat :production
```

**Every tag names only the commit, and the three repositories are now the same shape.** They were
not: an `f2c/club` image built for QA was not a production artefact and never could be — R-D4 — so
the frontend tags carried a `qa-`, `uat-` or `production-` prefix, because an unprefixed one would
have looked promotable and would eventually have shipped a production storefront rendering QA
canonical tags. With R-D4 closed the prefix would be a claim about an image that is not true of it,
so it is gone. **A prefixed frontend tag still in the listing is from before that change**; nothing
builds one now, none of them is promotable, and each can be deleted once no revision references its
digest.

**Every deployment pins a digest, and the moving tags are labels for people.** The registry is Basic
tier and tag immutability is a Premium feature, so a tag here *can* be moved — which makes a
container app revision pinned to `:qa` a revision whose contents can change with no deployment and
no record of one. `deploy-api.sh` refuses a tag reference outright rather than trusting its caller to
pass a digest. What `:qa`, `:uat` and `:production` buy is that "what is running in UAT" is
answerable from the registry listing instead of from the portal, and the ladder check in 6.4 depends
on that. **The frontends carry them now too, and could not before:** while every `f2c/club` tag was
already environment-prefixed there was no single digest to follow up the ladder, so production could
receive a storefront nobody had seen in UAT and nothing in the registry would have said so.

**Every image carries `org.opencontainers.image.revision`.** Without it, "which commit is running in
production" becomes archaeology the first time somebody needs the answer during an incident. It used
to do a second job — the label on the API image being promoted named the commit the frontends had to
be rebuilt from — which nothing needs now that there is one image per artefact per commit.

The `za.co.f2c.environment` label went with the prefix. There is no environment to name.

Two build settings worth knowing about. `provenance: false`, because a provenance attestation turns
the push into an OCI index with a second, platform-less manifest inside it and nothing here consumes
the attestation — a single manifest is one less thing between a digest and a running revision. And
the GitHub Actions layer cache, scoped per image, which keeps a frontend build on trunk from being
a cold `npm ci`. It used to matter at promotion time as well, and no longer does: a promotion builds
nothing.

### 6.3 Deploying one service, or two, or all three

**A commit builds only the images it changed.** `release.yml` takes a plain `git diff` against the
commit the push replaced — no marketplace action, because this job decides what reaches a deployed
environment and one fewer third party in that path is worth ten lines of shell:

| Image | Rebuilt when the commit touches |
| --- | --- |
| `f2c/api` | `Dockerfile`, `.dockerignore`, `manage.py`, `pyproject.toml`, `poetry.lock`, `requirements.txt`, `app/`, `f2c/`, `deploy/`, `templates/`, `static/` |
| `f2c/club` | `frontend/club/`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/.dockerignore` |
| `f2c/market` | `frontend/market/`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/.dockerignore` |

**The shared lockfile counts as a change to both frontends**, because `frontend/package-lock.json`
is one file for the whole npm workspace and `npm ci` resolves every member from it. A dependency
bump touching nothing under `club/` still changes what a club image contains.

**When there is no usable base commit, everything is built.** An empty or all-zero
`github.event.before` — a new branch, a force push, a rewritten history — means there is no diff to
take, and building everything is the only answer that cannot silently skip an image that needed it.
For the first run against an empty registry, use the dispatch and its per-service ticks rather than
relying on a diff at all.

**`DEPLOY_MARKET` gates the market storefront in every environment**, which is decision D2 stated
once instead of in six places. It saves nothing in the API's configuration — the API refuses to start
without a working market mailer whether the market frontend is deployed or not, which is section 1.

**"Deploy the backend" is four container apps and not one, and the order is a constraint rather than
a style.** Section 5.2 puts `api`, `worker`, `mail-worker` and `beat` all on the same image, chosen
between by the first argument to `deploy/entrypoint.sh`. Only `api` runs `migrate` — the workers
deliberately do not, because a second process racing the first through the same schema change on
every deployment is worse than a slightly longer start-up. So the API goes first, `deploy-api.sh`
waits for its revision to provision, and only then do the three that serve no traffic follow. A
worker started against a schema the API has not moved yet is the overnight-wrong-writes failure 5.2
is written against.

That wait is also where a bad migration surfaces, which is R-D3 arriving in practice. When it times
out, or the revision reports unhealthy, the script prints the `az containerapp logs show` command for
that exact revision — the entrypoint gate names the check it refused on, and reading that is faster
than reading the portal.

**Nothing in an image update changes the scale rules**, so `beat` stays capped at one replica through
every deployment. That matters: two beats publish every job twice, and while all three scheduled
tasks are idempotent, each duplicate writes its own `ScheduledRun` row and the history stops being
readable — which is the one thing that table exists for.

### 6.4 Promotion moves images, and the input names them by commit

**Nothing is rebuilt at promotion.** All three artefacts are moved the same way: `az acr import`
retags the image inside the registry — server-side, no pull, no push — and the container apps are
updated to that same digest. What ran in QA is bit-for-bit what runs in production, for the
storefronts as well as for the API.

**This section used to be called "Promotion is a commit, not an image", and the input is still a
commit — but it is now a choice rather than a constraint.** The old reason was that one kind of
artefact could be moved and the other had to be rebuilt: the API had been made environment-agnostic
by Block 0 P6, while the frontends baked `SITE_URL`, `APP_ENV`, `CDN_BASE_URL` and `SUPPORT_EMAIL`,
so an image tag as the input would have worked for the API and been meaningless for the frontends.
A commit worked for both. With R-D4 closed a tag would work for all three.

The SHA is kept anyway, on two smaller arguments. It names all three artefacts at once, where a tag
names one. And it reads the same in a promotion run as it does in `git log`, which is where anyone
asking "what is going to production" starts.

**What stands in for re-running the tests, and why they are not re-run.** A called workflow runs at
the *caller's* ref, so calling `ci.yml` from here would test trunk rather than the commit being
promoted, and report green for the wrong code. The gate is the registry instead: `f2c/api:<sha>`
exists only because `release.yml` built it, and that job is `needs: test`. **An image in the registry
is therefore a commit that passed against MySQL 8.4.** A SHA with no image is refused with that
explanation rather than built here. The frontends are gated the same way, against
`f2c/club:<sha>` and `f2c/market:<sha>`.

**The ladder is enforced, not assumed.** A promotion to production checks that the digest being
promoted is the one that environment's `:uat` tag points at, and refuses when it is not — the
alternative being production receiving a release UAT never saw. **Each artefact is checked against
its own `:uat` tag**, which is newly possible: a frontend had no promotable digest to follow up the
ladder until R-D4 closed, so a rebuilt production storefront was accepted on the strength of the
API's check alone. The tag is written as the *last* step of a successful
UAT promotion, so it means "this is running there" rather than "somebody tried to put this there".
`skip_ladder_check` overrides it for the case that will eventually arise; it takes a deliberate tick,
emits a warning annotation, and is recorded in the run.

**Rollback is the same mechanism run backwards, and nothing about it needs a rebuild:** dispatch the
previous SHA, or pin the previous Container Apps revision. That is now true of the frontends as well
— a frontend rollback used to be a rebuild of the previous commit, minutes rather than seconds, and
was one of the things R-D4 cost.

### 6.5 The credential is federated, and there is one per environment

**No passwords anywhere.** GitHub mints a short-lived OIDC token, Entra ID exchanges it for an access
token, and nothing is stored in the repository. It is the same argument section 2 makes for reaching
blob storage with a managed identity: a key is a thing that has to be rotated, copied between
environments and kept out of screenshots.

**One application registration per environment, and the reason is production.** A single registration
with rights over all three resource groups would mean the QA build job holding write access to
production. The GitHub environment approval would still gate the *workflow*, but the credential
itself would not be limited — and a credential is worth what it can reach rather than what it is
usually used for.

Each registration gets a federated credential whose subject is
`repo:<owner>@<owner id>/<repo>@<repo id>:environment:<name>`. **That subject is what turns the
reviewer requirement into an enforced gate rather than a convention:** a job that does not declare
`environment: production` cannot mint a production token at all, however much repository access its
author has.

The numeric IDs alongside the names are the immutable identifiers of the owner and the repository,
and they are the reason `azure-oidc-setup.sh` reads the subject out of the GitHub API rather than
composing it from the name it was given. A credential carrying the names alone is refused with
`AADSTS700213` — the same failure a repository transfer produces, since the names in an existing
credential are then stale and nothing in Azure notices.

Two role assignments per environment. `AcrPush` on the shared registry — push and not merely pull,
because `az acr import` writes the moving environment tag at the end of a promotion. And `Contributor` scoped to that environment's resource
group and nothing wider. **The second is broader than this pipeline needs**, which only ever calls
`containerapp update`; narrowing it to a custom role carrying `Microsoft.App/containerApps/read` and
`/write` is the obvious hardening step, recorded here rather than done because a custom role
definition is a fourth thing to keep in step across three environments.

**The container apps pull with their own identities, which is a separate grant from the above.** Each
of the six gets a system-assigned identity with `AcrPull` on the registry, and
`az containerapp registry set --identity system`. Then the registry's admin user goes off:

```
az acr update --name <registry> --admin-enabled false
```

An admin user left enabled is a username and password that works from anywhere, for every repository
in the registry, and outlives whoever last used it.

### 6.6 The GitHub side

Three environments — `qa`, `uat`, `production` — with **required reviewers on the last two**. That is
the approval, and it is also the audit trail: who released what, to which environment, and when.
Worth having before R-D1 and R-D2 are written up rather than after.

`azure-oidc-setup.sh` writes the first three rows; the rest are values only the operator knows.

| Variable | Scope | What it is |
| --- | --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Environment | Written by the setup script |
| `AZURE_RESOURCE_GROUP` | Environment | `rg-f2c-qa-weu` and its siblings |
| `ACR_NAME` | Repository | One registry for all three environments — section 2 |
| `CONTAINERAPP_API`, `CONTAINERAPP_WORKER`, `CONTAINERAPP_MAIL_WORKER`, `CONTAINERAPP_BEAT` | Environment | The four names from 5.2 |
| `CONTAINERAPP_CLUB`, `CONTAINERAPP_MARKET` | Environment | The two storefronts |
| `DEPLOY_MARKET` | Environment | `true` to deploy the market storefront — D2 |

**`APP_ENV`, `CLUB_SITE_URL`, `CLUB_CDN_BASE_URL`, `CLUB_SUPPORT_EMAIL` and `MARKET_SITE_URL` were
on this table and are not any more.** They were frontend build arguments, so a workflow had to carry
each one from a GitHub variable into `docker build`. They are container app environment variables
now, under their unprefixed names — 4.2 and 4.3 — and can be deleted from the three GitHub
environments. Nothing on this table is read by a running container.

**Variables rather than secrets, the three Azure identifiers included.** None of them is usable on
its own: without the federated trust, and without a job running in this repository under that
environment, a client ID is not a way in. Keeping them readable means whoever is debugging a failed
deployment can see which subscription it was aimed at — the same argument section 3 makes for the
container app's non-secret environment variables.

**`APP_ENV` and the GitHub environment name are two different strings and are allowed to disagree.**
The environment is `production` because that is the GitHub convention and it is what the frontend
image tag is prefixed with; `APP_ENV` is whatever the frontends expect, which D5 declined to change.
The tag prefix is the environment name and never `APP_ENV`, so the two never have to be reconciled —
but somebody reading `f2c/club:production-<sha>` on an image whose `APP_ENV` is `prod` should know
that is deliberate.

---

## 7. The order

1. Provision the resource group, registry, MySQL, Managed Redis, storage account and Log Analytics.
   No containers yet. **This is now the first step.** It used to be raising the
   `noreply@f2c.co.za` mailbox with the provider, which authenticates as of 2 September 2026 —
   section 1.
2. Fix the flaky test (5.4), wanted before the first deploy rather than after it. The static files
   (5.1) are done.
3. Create the Key Vault, generate the QA encryption keys, load the secrets.
4. Run `.github/scripts/azure-oidc-setup.sh` for `qa`, create the three GitHub environments with
   reviewers on `uat` and `production`, and set the variables in 6.6. The registry from step 1 has
   to exist first; nothing else here does.
5. **Deploy the API container app alone**, with `min-replicas 1`. The entrypoint gate reports each
   misconfiguration by name — that is what it is for, and it is cheaper to meet it with one
   container running than with three.

   That first deployment is a `release.yml` dispatch with only `api` ticked, not a hand-run
   `az containerapp update` — the first thing worth proving about the pipeline is that it can
   reach one container app.
6. DNS and TLS for the two club hostnames. Build and deploy the club frontend.
7. Grant the founding administrators (5.3). Then walk the whole journey: emailed sign-in code,
   passkey enrolment, sign-up, Payfast sandbox checkout, membership activation, profile edit,
   `/admin/members` and `/admin/strains`.
8. Add the worker, mail worker and beat container apps (5.2). Redeploy through the pipeline, which
   is where `deploy-api.sh` first rolls all four in order rather than one.
9. Market hostnames and container, if QA is to carry the market at all — section 8.
10. Write up the key procedure (R-D2) and the transborder disclosure (R-D1) before any environment
    holds a real member.
11. Repeat steps 1 and 3 to 6 for UAT, and then for production, in that order. Each needs its own
    resource group, its own hostnames and certificates, its own encryption keys (R-D5), its own
    application registration (6.5) and its own GitHub environment. The registry is shared and is
    not repeated, and neither is step 2. From then on a release reaches those two environments
    through `promote.yml` and 6.4, and never through a build off trunk.

Steps 1 to 8 are about a week of elapsed time, most of it waiting on DNS and TLS rather than on
work. The provider used to be on that list and no longer is.

---

## 8. Open decisions

| # | Decision | Recommendation |
| --- | --- | --- |
| D1 | The QA hostnames | `qa.` and `qa-api.` inside the two production registrable domains, as section 2 sets out. Anything that puts the API outside the frontend's registrable domain breaks the session cookie and reproduces nothing — C30 |
| D2 | Whether QA carries the market storefront at all | **Skip it while the store is on the back burner.** It saves a container app, two DNS records and a certificate. It saves **none** of the `EMAIL_F2C_*` entries — the API needs those to boot either way, which is section 1 |
| D3 | Payfast sandbox or live in QA | **Sandbox.** Live in QA moves real money on a test environment. The cost is that the production credentials are first exercised in production, which is an argument for one deliberate live transaction at cutover rather than for a live QA |
| D4 | Key Vault, or container app secrets alone | **Key Vault for the two encryption keys**, container app secrets for everything else. It is one resource and a role assignment, and it discharges most of P4 |
| D5 | Whether the frontends' `APP_ENV` and Django's `DJANGO_ENV` should share a vocabulary | Leave them. Correcting `prod` to `production` touches the CI workflow, `compose.yaml` and both frontends for no behavioural gain. Documented in 4.1 instead, and in 6.6 for what it means when the GitHub environment is called `production` and `APP_ENV` is not |
| D6 | Whether a promotion is a branch merge, a git tag or a dispatch | **Settled, in section 6: trunk-based, with a dispatch.** A merge to `master` deploys QA on its own; UAT and production are dispatches of a named commit behind environment reviewers. Branch-per-environment was the alternative and it drifts — what reaches production is then a merge commit nothing tested as one |

---

## 9. Risks

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
- **R-D4. A QA frontend image could not be promoted to production**, because `SITE_URL`, `APP_ENV`,
  `CDN_BASE_URL` and `SUPPORT_EMAIL` were build arguments — `lib/site.ts` read them at module load,
  and `next build` loads every module to analyse the route tree. What reached production was
  therefore not the artefact that had been tested, only the same commit rebuilt. **Closed.**
  `lib/site.ts` exports `siteConfig()`, called during render; both root layouts build their metadata
  in `generateMetadata` rather than in an object evaluated at import; and both proxies read it per
  request, which works because Next 16 runs proxy on the Node.js runtime where `process.env` is the
  container's. Verified rather than assumed: both applications build with all four variables, and
  both API addresses, unset. Section 3 and 4.2.

  Two things moved rather than disappeared. **The build's fail-fast is now the container's** —
  `frontend/deploy/entrypoint.sh` refuses to start without the names in `REQUIRED_ENV`, so a
  misconfigured revision never serves traffic. And **`APP_ENV` set to the wrong valid value is a
  new exposure**: it decides indexing, so a typo in a container setting can make production
  `noindex` or QA indexable without failing anything. **Accepted**, as the same class as a wrong
  `DJANGO_ALLOWED_HOSTS`, and mitigated by the `/robots.txt` and `X-Robots-Tag` check written into
  `deploy-quickstart.md` step 12 rather than by keeping the value in the build. Keeping `APP_ENV` as
  the one remaining build argument was considered and rejected: it would have left the images
  environment-specific — the whole cost of R-D4 — to remove one of the four ways this can be set
  wrong.
- **R-D5. The QA environment has its own encryption keys, so a production backup cannot be restored
  into it to reproduce a fault.** That is the point of separate keys and the trade is deliberate:
  reproducing a production data fault in QA would mean QA holding production identity numbers.
  **Accepted.**
- **R-D6. The ladder check reads a mutable tag.** A promotion to production refuses a digest that
  `f2c/api:uat` does not point at — 6.4 — but tag immutability is a Premium registry feature and
  this registry is Basic, so anyone holding `AcrPush` can move that tag. The check therefore guards
  against a mistake and not against intent. **Accepted:** the population that can move the tag is
  the population that can approve the promotion, and the GitHub environment approval is the control
  that matters.
- **R-D7. A rebuild has to be byte-identical to what was tested.** `npm ci` installs exactly what
  the committed lockfile says, so the dependency tree was never the exposure — but both frontend
  Dockerfiles named `node:24-slim`, a floating tag, and a base image republished between two builds
  of the same commit changes the operating system packages underneath an application whose own code
  and dependencies are identical.

  **Closed.** All four Dockerfiles pin by digest through a single `ARG` each — `node:24-slim` at
  Node 24.20.0 and `python:3.14-slim` at Python 3.14.7, both resolved 2 September 2026 — so what a
  commit describes is a fixed image rather than whatever the tag pointed at on the day it was
  rebuilt. One `ARG` per file rather than a digest on each `FROM` is deliberate: a digest copied
  three times is a digest that can be bumped twice, and a build stage on one Node with a runtime
  stage on another surfaces as something else entirely. `Dockerfile.dev` is pinned too, not for
  reproducibility — nothing is promoted from it — but so that a developer and a deployment are on
  the same Node.

  **This risk is narrower than it was, and the narrowing is worth stating.** It was written when a
  frontend promotion *rebuilt*, so the two builds being compared were the QA one and the production
  one, minutes or days apart, and the pin was what made "the same commit" mean "the same image"
  across environments. R-D4 closed and a promotion now moves the image it was given, so no two
  builds of one commit are compared across environments any more. What remains is reproducibility
  over *time*: rebuilding an older commit — to bisect a fault, or to ship a fix from a release
  branch — should land on the operating system packages that commit was tested against rather than
  on whatever the tag points at that day.

  Two consequences worth stating rather than discovering. **A pinned base is a base that stops
  receiving operating system security updates**, so bumping it is now a task somebody owns rather
  than something that happens by itself; `docker buildx imagetools inspect node:24-slim` gives the
  next one, and it is the *top-level* index digest that is wanted rather than one platform's
  manifest. And **the service containers in `ci.yml` are deliberately not pinned** — `mysql:8.4`
  and `redis:7-alpine` stay on tags, because Azure Database for MySQL patches itself within 8.4
  and a CI job frozen behind it would prove the schema against a server production no longer runs.
  That is section 2's argument for `8.4` over `8`, and it stops at the minor version on purpose.
- **R-D8. The four API container apps are updated one after another, so there is a window in which
  the API runs the new revision and the workers still run the old one.** `deploy-api.sh` orders it
  that way on purpose — only the API migrates, and a worker must not start against a schema that
  has not moved — but it means a migration has to be readable by the *previous* worker code as well
  as by the previous API revision, which is R-D3 with a second reader. **Accepted**, and it is the
  same constraint rather than a new one: a migration that satisfies R-D3 satisfies this.

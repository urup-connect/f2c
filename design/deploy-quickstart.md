# Deploy quickstart

The steps, in order, and every configuration entry that has to exist. No rationale — when a value
looks arbitrary or a step looks skippable, the reason is in [`deploy.md`](deploy.md), and the
section numbers below point at it.

Target: Azure, West Europe, one resource group per environment. QA is `rg-f2c-qa-weu`.

---

## Part 1 — Steps

### 1. Provision Azure (QA)

One resource group, `rg-f2c-qa-weu`. Inside it:

| Resource | Sizing |
| --- | --- |
| Container Registry | Basic. **Shared by all three environments** — created once, never repeated |
| MySQL Flexible Server 8.4 | Burstable B2s. Database `f2c`. `require_secure_transport` ON |
| Azure Managed Redis | Not Azure Cache for Redis. TLS only, port 10000 |
| Storage account | Two blob containers: `cc-documents-qa` and `cc-avatars-qa` |
| Log Analytics workspace | For the Container Apps environment |
| Container Apps environment | — |

No container apps yet.

### 2. Fix the flaky nickname test

`frontend/club/app/api/nickname/availability/route.test.ts` fails about one run in thirty. Fix it
before CI gates a deployment. (deploy.md 5.4)

### 3. Key Vault and secrets

Create the Key Vault with soft delete and purge protection. Generate **fresh** QA encryption keys —
never copy production's down:

```
python design/tools/generate_keys.py
```

Load `DJANGO_FIELD_ENCRYPTION_KEY` and `DJANGO_BLIND_INDEX_PEPPER` into Key Vault. Everything else
secret goes into Container App secrets in step 5. (Tables A and B)

### 4. GitHub and Azure OIDC

```
.github/scripts/azure-oidc-setup.sh          # once per environment
```

Requires the registry from step 1. It creates the application registration, the federated
credential (`repo:<owner>@<owner id>/<repo>@<repo id>:environment:qa`), the two role assignments (`AcrPush` on the
registry, `Contributor` on the resource group), and writes the three `AZURE_*` variables.

Needs the Azure CLI **and** the GitHub CLI, both signed in — `winget install --id GitHub.cli` then
`gh auth login`, since `gh` is not on a Windows box by default. Whichever subscription `az` is
pointed at is the one written into `AZURE_SUBSCRIPTION_ID`, so run `az account set` first. Creating
the role assignments needs **Owner** or **User Access Administrator** on the registry and the
resource group, on top of rights to create app registrations.

**On Windows, run it from a shell you can read.** There is no `bash` on PowerShell's path and
double-clicking it closes the window on the first missing variable:

```powershell
$env:ENVIRONMENT="qa"; $env:ACR_NAME="<acr>"; $env:RESOURCE_GROUP="<qa rg>"
& "C:\Program Files\Git\bin\bash.exe" .github/scripts/azure-oidc-setup.sh
```

It is safe to re-run: it reuses an existing registration, and corrects a federated credential whose
subject has gone stale — which is what a repository transfer leaves behind.

Then, by hand:

- Create GitHub environments `qa`, `uat` and `production`, with **required reviewers on `uat` and
  `production`**.
- Set the variables in Table F.

### 5. Create the API container app and deploy it alone

Create the container app with `min-replicas 1`, a system-assigned managed identity, and:

- **Storage Blob Data Contributor** on the storage account
- **AcrPull** on the registry, plus `az containerapp registry set --identity system`
- Key Vault references for the two keys in Table A
- Secrets from Table B, environment variables from Table C

Deploy it through the pipeline, not by hand:

```
Actions -> release.yml -> Run workflow -> api [x]  club [ ]  market [ ]  deploy [x]
```

The entrypoint runs `check --deploy --fail-level WARNING`, so a misconfigured revision refuses to
start and names what is wrong. Meet that with one container running rather than four.

### 6. DNS, TLS and the club frontend

Custom domains and managed certificates on the Container Apps environment:

```
qa.f2c-cannabis.co.za        club frontend container app
qa-api.f2c-cannabis.co.za    API container app
```

Create the club frontend container app (port 3000, Table D), then dispatch `release.yml` with
`club` ticked.

### 7. Grant the founding administrators

After the first migration, by hand: `is_staff` for the UC tier, and a club `StorefrontStaff` row per
club administrator. No migration can do this. (5.3)

Then walk the journey end to end: emailed sign-in code, passkey enrolment, sign-up, Payfast sandbox
checkout, membership activation, profile edit, `/admin/members`, `/admin/strains`.

### 8. Add the three worker container apps

Same image as the API, same **full** environment (Tables B and C verbatim, not a subset), no
ingress:

| App | Command | Replicas |
| --- | --- | --- |
| worker | `deploy/entrypoint.sh worker` | 1..n |
| mail-worker | `deploy/entrypoint.sh mail-worker` | 1..n |
| beat | `deploy/entrypoint.sh beat` | **exactly 1** |

Set the four `CONTAINERAPP_*` variables in Table F, then redeploy through `release.yml`.
`deploy-api.sh` now rolls all four in order: API first, because it migrates; workers after.

### 9. Market storefront — optional in QA

Two more DNS records, a certificate, one container app (Table E), and `DEPLOY_MARKET=true`. Skipping
it saves none of the `EMAIL_F2C_*` entries — the API will not boot without them either way.

### 10. Write up the two POPIA items

Transborder disclosure (R-D1) and the key-handling procedure (R-D2), before any environment holds a
real member.

### 11. Repeat for UAT, then production

Repeat steps 1, 3, 4, 5, 6 — and 8, 9 — per environment. Each gets its own resource group,
hostnames and certificates, encryption keys, application registration and GitHub environment.
**The registry is shared and is not repeated.** Step 2 is not repeated.

Production hostnames drop the prefix: `f2c-cannabis.co.za`, `api.f2c-cannabis.co.za`, `f2c.co.za`,
`api.f2c.co.za`.

### 12. From then on: releases and promotions

| Action | How |
| --- | --- |
| Deploy to QA | Merge to `master`. `release.yml` builds only the images the commit changed |
| Promote to UAT | `promote.yml` dispatch: `sha`, `to_env: uat` |
| Promote to production | `promote.yml` dispatch: `sha`, `to_env: production`. Refuses a digest `f2c/api:uat` does not point at, unless `skip_ladder_check` is ticked |
| Roll back the API | Dispatch the previous SHA, or pin the previous Container Apps revision |
| Roll back a frontend | Dispatch the previous SHA, or pin the previous Container Apps revision |

All three artefacts are promoted by moving a digest. Nothing is rebuilt: `SITE_URL`, `APP_ENV`,
`CDN_BASE_URL` and `SUPPORT_EMAIL` are container app settings (Tables D and E), not build
arguments. Section 3.

**After every promotion, check the storefront is indexable the way you meant.** `APP_ENV` decides
that, and it is a container setting now, so a typo makes production `noindex` — or QA indexable —
without anything failing:

```
curl -sI https://<host>/ | grep -i x-robots-tag     # production: absent. QA and UAT: noindex
curl -s  https://<host>/robots.txt                  # production: Allow. QA and UAT: Disallow: /
```

Both come from `APP_ENV` alone, so one wrong value shows in both. If they disagree with the
environment, fix `APP_ENV` on the container app and deploy a new revision — no rebuild.

Once every container app pulls with its own identity, close the registry's admin account:

```
az acr update --name <registry> --admin-enabled false
```

---

## Part 2 — Configuration

Four stores. QA values shown; substitute per environment. Nothing below goes in the repository.

### Table A — Azure Key Vault

Referenced from the API container apps through their managed identities.

| Entry | Value |
| --- | --- |
| `DJANGO_FIELD_ENCRYPTION_KEY` | From `generate_keys.py`. Fresh per environment |
| `DJANGO_BLIND_INDEX_PEPPER` | From `generate_keys.py`. Fresh per environment |

### Table B — Container App secrets

On all four API-image apps — api, worker, mail-worker, beat — referenced as `secretref:`.

| Entry | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | From `generate_keys.py` |
| `DJANGO_DB_PASSWORD` | Application user's MySQL password |
| `DJANGO_REDIS_URL` | `rediss://:<access-key>@<name>.westeurope.redis.azure.net:10000/0` — `rediss`, not `redis` |
| `EMAIL_CC_PASSWORD` | Club mailbox password |
| `EMAIL_F2C_PASSWORD` | Market mailbox password |
| `DJANGO_PAYFAST_MERCHANT_ID` | Sandbox in QA and UAT, live in production |
| `DJANGO_PAYFAST_MERCHANT_KEY` | As above |
| `DJANGO_PAYFAST_PASSPHRASE` | Required, not optional — Payfast refuses subscriptions from a merchant without one |

### Table C — Container App environment variables (api, worker, mail-worker, beat)

All four apps take this block identically. A trimmed environment fails `check --deploy` at start-up.

| Entry | QA value |
| --- | --- |
| `DJANGO_ENV` | `qa` — or `prod`, not `production` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `qa-api.f2c-cannabis.co.za,qa-api.f2c.co.za` |
| `DJANGO_BEHIND_PROXY` | `true` — without it no Payfast notification is accepted and no membership activates |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://qa.f2c-cannabis.co.za,https://qa.f2c.co.za` |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `https://qa.f2c-cannabis.co.za,https://qa.f2c.co.za` |
| `DJANGO_DB_HOST` | `<server>.mysql.database.azure.com` |
| `DJANGO_DB_PORT` | `3306` |
| `DJANGO_DB_NAME` | `f2c` |
| `DJANGO_DB_USER` | Application user |
| `DJANGO_DB_SSL_CA` | `/etc/ssl/certs/ca-certificates.crt` |
| `DJANGO_STOREFRONT_HOSTS` | `qa-api.f2c-cannabis.co.za=club,qa-api.f2c.co.za=market` — **API** hostnames |
| `DJANGO_DEFAULT_STOREFRONT` | `club` |
| `DJANGO_WEBAUTHN_RP_ID` | `qa.f2c-cannabis.co.za` — **frontend** hostnames from here down |
| `DJANGO_WEBAUTHN_RP_IDS` | `club=qa.f2c-cannabis.co.za,market=qa.f2c.co.za` |
| `DJANGO_WEBAUTHN_RP_NAME` | `Cultivators Collective (QA)` |
| `DJANGO_WEBAUTHN_ORIGINS` | `https://qa.f2c-cannabis.co.za,https://qa.f2c.co.za` |
| `DJANGO_DEFAULT_FROM_EMAIL` | `no-reply@f2c-cannabis.co.za` |
| `DJANGO_DOCUMENT_STORAGE_CONTAINER` | `cc-documents-qa` |
| `DJANGO_DOCUMENT_STORAGE_ACCOUNT` | `stf2cqaweu` |
| `DJANGO_AVATAR_STORAGE_CONTAINER` | `cc-avatars-qa` — must differ from the documents container |
| `DJANGO_AVATAR_STORAGE_ACCOUNT` | `stf2cqaweu` |
| `DJANGO_CDN_BASE_URL` | Blank unless the documents container is actually fronted. If set: `https`, and its path empty or exactly the container name |
| `EMAIL_CC_HOST` | Club mail host |
| `EMAIL_CC_PORT` | `587` |
| `EMAIL_CC_USER` | Club mailbox |
| `EMAIL_CC_USE_TLS` | `true` |
| `EMAIL_CC_FROM` | Required — no useful fallback |
| `EMAIL_F2C_HOST` | `mail.f2c.co.za` |
| `EMAIL_F2C_PORT` | `587` |
| `EMAIL_F2C_USER` | Market mailbox |
| `EMAIL_F2C_USE_TLS` | `true` |
| `EMAIL_F2C_FROM` | Required. The API does not boot without the `F2C` block, deployed market or not |
| `EMAIL_DISPATCH_RETENTION_DAYS` | `365` |
| `CAMPAIGN_TOUCH_RETENTION_DAYS` | `730` |
| `DJANGO_PAYFAST_SANDBOX` | `true` in QA and UAT |
| `DJANGO_PAYFAST_RETURN_URL` | `https://qa.f2c-cannabis.co.za/signup/paid` |
| `DJANGO_PAYFAST_CANCEL_URL` | `https://qa.f2c-cannabis.co.za/signup/cancelled` |
| `DJANGO_PAYFAST_NOTIFY_URL` | `https://qa-api.f2c-cannabis.co.za/api/payments/payfast/notify` — the **API** address, and internet-reachable |
| `DJANGO_MEMBERSHIP_CHECKOUT_URL` | `https://qa.f2c-cannabis.co.za/pay` |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT` | `150.00` |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY` | `monthly` |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES` | `0` |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_ITEM_NAME` | `Club membership` |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_DESCRIPTION` | `Cultivators Collective membership subscription` |

Leave unset: `DJANGO_DB_SSL_DISABLED`, `DJANGO_CACHE_ALLOW_PLAINTEXT`, `EMAIL_CC_USE_SSL`,
`EMAIL_F2C_USE_SSL`, and every storage account key, SAS token and connection string. Each one
downgrades or overrides something that is correct as it stands.

### Table D — Club frontend container app

Everything the club reads. There are no build arguments: the image is the same one in every
environment, and this table is what makes it a QA one. Section 3.

| Entry | QA value |
| --- | --- |
| `DJANGO_API_URL` | `https://f2c-api.internal.<env-name>.westeurope.azurecontainerapps.io` |
| `DJANGO_API_PUBLIC_URL` | `https://qa-api.f2c-cannabis.co.za` — same registrable domain as `SITE_URL` |
| `SITE_URL` | `https://qa.f2c-cannabis.co.za` — scheme and host only, no path |
| `APP_ENV` | `qa`. Takes `local`, `qa` or `production` — a different vocabulary from `DJANGO_ENV`, deliberately. Decides indexing |
| `CDN_BASE_URL` | Static host, `https` outside local development |
| `SUPPORT_EMAIL` | `members@f2c-cannabis.co.za` — the mailbox on the blocked-membership screen |
| `PORT` | `3000` |

The container **refuses to start** without `SITE_URL`, `APP_ENV`, `CDN_BASE_URL` or `SUPPORT_EMAIL`,
and names the missing one in its log. `frontend/deploy/entrypoint.sh`.

### Table E — Market frontend container app

| Entry | QA value |
| --- | --- |
| `DJANGO_API_URL` | `https://f2c-api.internal.<env-name>.westeurope.azurecontainerapps.io` |
| `DJANGO_API_PUBLIC_URL` | `https://qa-api.f2c.co.za` |
| `SITE_URL` | `https://qa.f2c.co.za` — scheme and host only, no path |
| `APP_ENV` | `qa`. Decides indexing |
| `PORT` | `3000` |

No `CDN_BASE_URL` and no `SUPPORT_EMAIL`: the club film and the blocked-membership screen are both
the club's. The container refuses to start without `SITE_URL` or `APP_ENV`.

### Table F — GitHub Actions variables

**All variables, no secrets** — the federated credential replaces every password. Nothing here is
usable outside a job running in this repository under that environment.

| Variable | Scope | QA value |
| --- | --- | --- |
| `ACR_NAME` | Repository | Registry name, without `.azurecr.io` |
| `AZURE_CLIENT_ID` | Environment | Written by `azure-oidc-setup.sh` |
| `AZURE_TENANT_ID` | Environment | Written by `azure-oidc-setup.sh` |
| `AZURE_SUBSCRIPTION_ID` | Environment | Written by `azure-oidc-setup.sh` |
| `AZURE_RESOURCE_GROUP` | Environment | `rg-f2c-qa-weu` |
| `CONTAINERAPP_API` | Environment | API container app name |
| `CONTAINERAPP_WORKER` | Environment | Worker container app name |
| `CONTAINERAPP_MAIL_WORKER` | Environment | Mail worker container app name |
| `CONTAINERAPP_BEAT` | Environment | Beat container app name |
| `CONTAINERAPP_CLUB` | Environment | Club frontend container app name |
| `CONTAINERAPP_MARKET` | Environment | Market frontend container app name |
| `DEPLOY_MARKET` | Environment | `true` to deploy the market storefront |

Twelve entries, and every one of them names something GitHub Actions has to address: a credential,
the registry, a resource group, a container app. **Nothing here is read by a running container.**

`APP_ENV`, `CLUB_SITE_URL`, `CLUB_CDN_BASE_URL`, `CLUB_SUPPORT_EMAIL` and `MARKET_SITE_URL` used to
be on this table as frontend build arguments, which is what stopped a frontend image being
promotable. They are container app settings now — Tables D and E, under their unprefixed names —
and can be deleted from the GitHub environments. Section 3, R-D4.

---

## Registry contents

```
f2c/api      :<sha>   plus the moving tags :qa :uat :production
f2c/club     :<sha>   plus the moving tags :qa :uat :production
f2c/market   :<sha>   plus the moving tags :qa :uat :production
```

One image per artefact per commit, promoted unchanged. Every deployment pins a digest —
`deploy-api.sh` refuses a tag reference — so the moving tags are labels for people, and the
production ladder check reads `f2c/api:uat`, `f2c/club:uat` and `f2c/market:uat`.

**A `f2c/club:qa-<sha>` or `f2c/market:production-<sha>` in the listing is from before R-D4 closed.**
Nothing builds those any more, and none of them is promotable. They can be deleted once no revision
references their digest.

---

## If something will not start

| Symptom | First thing to check |
| --- | --- |
| Container will not start and `check --deploy` names a setting | That is the gate working. Fix the named entry |
| Frontend container will not start and the log reads `entrypoint: <NAME> is not set` | The same gate, for the frontends. Add the entry from Table D or E and deploy a new revision |
| Production is missing from search, or QA has been indexed | `APP_ENV` on that container app. Check `/robots.txt` and the `X-Robots-Tag` header — step 12 |
| No membership activates after payment | `DJANGO_BEHIND_PROXY=true` |
| API will not start, mail-related | Both `EMAIL_CC_*` and `EMAIL_F2C_*` blocks are read at settings load, whatever is deployed |
| Sign-in appears to succeed and nothing after it works | API and frontend are not in the same registrable domain, so the `SameSite=Lax` cookie is not sent |
| Every document link 404s | `DJANGO_CDN_BASE_URL` path is not the container name |
| Uploads disappear on redeploy | No storage container named, so the code fell back to the ephemeral container filesystem |
| `/auth/otp/start` returns 200 but nobody can sign in | `mail-worker` is down. Watch `EmailDispatch.objects.pending()` rising, not `failed()` |
| Duplicate `ScheduledRun` rows | `beat` is running more than one replica |
| Revision unhealthy, or the deploy wait times out | `deploy-api.sh` prints the `az containerapp logs show` command for that exact revision |

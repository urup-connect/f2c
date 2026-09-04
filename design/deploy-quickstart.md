# Deploy quickstart

The steps, in order, and every configuration entry that has to exist. No rationale — when a value
looks arbitrary or a step looks skippable, the reason is in [`deploy.md`](deploy.md), and the
section numbers below point at it.

Target: Azure, West Europe, one resource group per environment for what this project owns. QA is
`rg-f2c-qa-weu`.

**The MySQL server is not in it.** QA's is `qa-urupconnect` in `qa-urupconnect`, UAT's is
`uat-urupconnect` in `uc-uat`, production's is `prod-urupconnect` in `prod-urupconnect-rg` — shared
servers, each carrying an `f2c` database. Nothing in a running container knows this: MySQL is
reached by hostname and blob storage by account name. Only
`deploy/provision-container-apps.sh`'s preflight is told, through `MYSQL_RESOURCE_GROUP` and
`STORAGE_RESOURCE_GROUP`.

---

## Part 1 — Steps

### 1. Provision Azure (QA)

One resource group, `rg-f2c-qa-weu`. Inside it:

| Resource | Sizing |
| --- | --- |
| Container Registry | `crf2cweu`, Standard. **Shared by all three environments** — created once, never repeated. Admin user **off** |
| Storage account | Two blob containers: `cc-documents-qa` and `cc-avatars-qa` |

Elsewhere, and only the `f2c` database and its application user are yours to create:

| Resource | Where |
| --- | --- |
| MySQL Flexible Server 8.4 | `qa-urupconnect` in resource group `qa-urupconnect`. Database `f2c`, `require_secure_transport` ON — encrypted, but not certificate-verified: the firewall admits only Azure services and named IPs, and the user authenticates with a password. **Production is 8.0.21** — above the 8.0.16 floor `common/checks.py` enforces, below the 8.4 CI tests against |

**No Redis, no Log Analytics workspace and no Key Vault here.** Redis is a container app — conflict.md
**C36** — created in step 5. The workspace is created by whichever of steps 3 and 5 runs first, under
the same name in the same resource group, and reused by the other. The vault and the identity are
step 3.

No container apps yet.

**The registry's admin user stays off.** The Portal's container app "Continuous deployment" wizard
turns it back on and writes a username and password into GitHub secrets; if that has happened,
`az acr update --name crf2cweu --admin-enabled false` and delete the secrets.

### 2. Fix the flaky nickname test — done

`frontend/club/app/api/nickname/availability/route.test.ts` failed about one run in twenty-three, on
a random hex reference that spelled one of the status codes the test scanned for. Fixed; nothing to
do here before CI gates a deployment. (deploy.md 5.4, conflict.md C25)

### 3. Key Vault, the identity, and the grants

Generate **fresh** QA encryption keys — never copy production's down — into the values file:

```
python design/tools/generate_keys.py
```

Then one script, and it has to run **before** step 5:

```powershell
Copy-Item deploy/values.env.template deploy/qa.values.env   # then fill it in
$env:ENVIRONMENT="qa"; $env:RESOURCE_GROUP="rg-f2c-qa-weu"
$env:ACR_NAME="crf2cweu"; $env:VALUES_FILE="deploy/qa.values.env"
$env:DRY_RUN="1"
& "C:\Program Files\Git\bin\bash.exe" deploy/provision-key-vault.sh
```

It creates the vault, the one user-assigned identity all six container apps present, the Log
Analytics workspace, an `AuditEvent` diagnostic setting, and five role assignments — then loads the
two keys. `DRY_RUN=1` prints every command and changes nothing; read it once, then drop it.

| Setting | Value | Why |
| --- | --- | --- |
| Permission model | **Azure RBAC** | Under RBAC the pipeline's `Contributor` on the resource group grants no data-plane access. Under access policies it could add itself to the policy list and read the field key |
| Purge protection | **On**, 90-day retention | R-D2. Irreversible once on, and it reserves the vault name for the full window, so get the name right first |
| Public network access | **Enabled from all networks** | The managed environment has no infrastructure subnet, so there is nowhere for a private endpoint to terminate. Container Apps is not a "trusted Microsoft service", so that bypass does not help either |
| Audit | `AuditEvent` → `log-rg-f2c-qa-weu` | The compensating control. Every read of the field key, with the principal that made it |

Roles, all at vault scope: **Key Vault Secrets User** for the identity, **Key Vault Secrets Officer**
for you. The GitHub application registrations get nothing — a deployment never reads the key.
deploy.md 3.1 has the reasoning; deploy.md 8 D4 has the alternative.

**Two things the script cannot do.** Add a second Secrets Officer so break-glass is not one person,
and **delete the two keys from `deploy/qa.values.env`** once they are in the vault — the container
apps reference the vault rather than holding a copy, so that file is the last plaintext. Both are
R-D2.

Everything else secret goes into Container App secrets in step 5, which the provisioning script sets
from the values file. (Tables A and B)

### 4. GitHub and Azure OIDC

```
'.github/scripts/azure-oidc-setup (win).sh'   # once per environment
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
& "C:\Program Files\Git\bin\bash.exe" ".github/scripts/azure-oidc-setup (win).sh"
```

It is safe to re-run: it reuses an existing registration, and corrects a federated credential whose
subject has gone stale — which is what a repository transfer leaves behind.

Then, by hand:

- Create GitHub environments `qa`, `uat` and `prod`, with **required reviewers on `uat` and
  `prod`**. The names are exact: `promote.yml`'s `to_env` choices, the federated credential subject
  `ENVIRONMENT` above writes, and the moving registry tags are all the same three strings, and a
  workflow naming an environment that does not exist gets an empty one with no reviewers rather than
  an error.
- Set the variables in Table F.

### 5. Create the environment and the seven container apps

One script. It creates the Container Apps environment and its Log Analytics workspace if they are
absent, then Redis, the four API-image apps, and the storefronts — each presenting the user-assigned
identity from step 3, which already holds `AcrPull`, and each carrying the settings from Tables B
to E.

```powershell
$env:ENVIRONMENT="qa"; $env:RESOURCE_GROUP="rg-f2c-qa-weu"
$env:CONTAINERAPP_ENV="cae-f2c-qa-weu"; $env:ACR_NAME="crf2cweu"
$env:USER_IDENTITY="id-f2c-qa"
$env:IMAGE_TAG="<a commit release.yml has built>"
$env:MYSQL_RESOURCE_GROUP="qa-urupconnect"; $env:STORAGE_RESOURCE_GROUP="rg-f2c-qa-weu"
$env:VALUES_FILE="deploy/qa.values.env"; $env:DRY_RUN="1"
& "C:\Program Files\Git\bin\bash.exe" deploy/provision-container-apps.sh
```

**`USER_IDENTITY` is required, and step 3 has to have run.** The script refuses if the identity is
absent, and refuses if either encryption key is missing from the vault: a revision resolves its Key
Vault references at start-up, so apps created against an empty vault never provision a first
revision and report it as a revision failure rather than as the missing secret it is.

`DRY_RUN=1` prints every command and changes nothing — read it once, then drop it. Re-running is
safe: an app that exists is reported and left alone.

**`IMAGE_TAG` means `release.yml` has to have run first.** The apps are created against image
digests, so dispatch a build with `deploy` unticked to get images into the registry without
attempting a deployment that has nowhere to land.

**`deploy/qa.values.env` is gitignored and must stay that way.** It holds the MySQL password, both
Payfast credentials, two mailbox passwords, and — until step 3 has loaded them into the vault — the
two encryption keys whose loss is unrecoverable. Delete it once the apps exist; from then on Azure
is where those values are read back from.

**Quote any value containing a space or a bracket.** The file is sourced by `bash`, so an unquoted
`(` or `{` is a syntax error and an unquoted `#` starts a comment — both fail the whole file at the
line they are on, before any check in the script runs.

The script sets `DJANGO_REDIS_URL`, `DJANGO_CACHE_ALLOW_PLAINTEXT` and `AZURE_CLIENT_ID` itself and
**refuses a value for any of the three in the file** rather than overriding it: the Redis URL names
an app at the environment's internal domain and `AZURE_CLIENT_ID` belongs to the identity, so
neither value exists until the resource does.

It refuses to run at all if the MySQL server or storage account cannot be found. That is deliberate
— the API entrypoint waits for the database before it serves anything, so creating the apps without
one gives four crashlooping containers rather than an error anybody reads. `FORCE=1` overrides;
`SKIP_MARKET=1` creates six apps instead of seven.

**Nothing is left by hand after this step any more.** `Storage Blob Data Contributor` and the Key
Vault references both used to be, and both moved: the grant is on the one identity step 3 creates,
and the references are built by this script from the vault and that identity.

### 6. Deploy the API alone

Through the pipeline, not by hand:

```
Actions -> release.yml -> Run workflow -> api [x]  club [ ]  market [ ]  deploy [x]
```

The entrypoint runs `check --deploy --fail-level WARNING`, so a misconfigured revision refuses to
start and names what is wrong. Meet that with one container running rather than four.

### 7. DNS, TLS and the club frontend

Custom domains and managed certificates on the Container Apps environment:

```
qa.f2c-cannabis.co.za        club frontend container app
qa-api.f2c-cannabis.co.za    API container app
```

The club frontend container app already exists (port 3000, Table D — step 5 created it). Dispatch
`release.yml` with
`club` ticked.

### 8. Grant the founding administrators

After the first migration, by hand: `is_staff` for the UC tier, and a club `StorefrontStaff` row per
club administrator. No migration can do this. (5.3)

Then walk the journey end to end: emailed sign-in code, passkey enrolment, sign-up, Payfast sandbox
checkout, membership activation, profile edit, `/admin/members`, `/admin/strains`.

### 9. Bring the three workers into the rollout

Same image as the API, same **full** environment (Tables B and C verbatim, not a subset), no
ingress:

| App | Command | Replicas |
| --- | --- | --- |
| worker | `deploy/entrypoint.sh worker` | 1..n |
| mail-worker | `deploy/entrypoint.sh mail-worker` | 1..n |
| beat | `deploy/entrypoint.sh beat` | **exactly 1** |

The three apps already exist — the provisioning script created all seven — so this step is setting
the four `CONTAINERAPP_*` variables in Table F and redeploying through `release.yml`.
`deploy-api.sh` then rolls all four in order: API first, because it migrates; workers after.

### 10. Market storefront — optional in QA

Two more DNS records, a certificate, the container app (Table E — already created unless step 5 ran
with `SKIP_MARKET=1`), and **`DEPLOY_MARKET=true` as a repository variable**. On the environment
alone it does nothing: see Table F. Skipping the market saves none of the `EMAIL_F2C_*` entries —
the API will not boot without them either way.

### 11. Write up the two POPIA items

Transborder disclosure (R-D1) and the key-handling procedure (R-D2), before any environment holds a
real member.

### 12. Repeat for UAT, then production

Repeat steps 1, 3, 4, 5, 6, 7 — and 9, 10 — per environment. Each gets its own resource group,
hostnames and certificates, encryption keys, application registration and GitHub environment.
**The registry is shared and is not repeated.** Step 2 is not repeated.

Production hostnames drop the prefix: `f2c-cannabis.co.za`, `api.f2c-cannabis.co.za`, `f2c.co.za`,
`api.f2c.co.za`.

### 13. From then on: releases and promotions

| Action | How |
| --- | --- |
| Deploy to QA | Merge to `master`. `release.yml` builds only the images the commit changed |
| Promote to UAT | `promote.yml` dispatch: `sha`, `to_env: uat` |
| Promote to production | `promote.yml` dispatch: `sha`, `to_env: prod`. Refuses a digest `f2c/api:uat` does not point at, unless `skip_ladder_check` is ticked |
| Roll back the API | Dispatch the previous SHA, or pin the previous Container Apps revision |
| Roll back a frontend | Dispatch the previous SHA, or pin the previous Container Apps revision |

**From the command line instead of the Actions tab.** `deploy/promote.ps1` dispatches `promote.yml`
and `deploy/whereis.ps1` reads the environment tags. They add pre-flight, not capability: the
approval gates, the OIDC credential, the `promote-<env>` lock and the audit trail stay in the
workflow, which is why neither script holds an Azure credential.

```
.\deploy\whereis.ps1                              # what is in qa, uat, prod
.\deploy\promote.ps1 -To uat                       # HEAD, api + club
.\deploy\promote.ps1 -To uat -Sha 6bff916 -Artefacts api
.\deploy\promote.ps1 -To prod -Artefacts api,club
```

The check worth having is the artefact one. `release.yml` builds only what a commit changed, so a
SHA does not necessarily name all three images — promoting `api,club` at an API-only commit rolls
the API and *then* fails on the club. `promote.ps1` refuses before dispatch and names the last
commit that did build the missing artefact.

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

Once every container app pulls with the user-assigned identity, close the registry's admin
account:

```
az acr update --name <registry> --admin-enabled false
```

---

## Part 2 — Configuration

Four stores. QA values shown; substitute per environment. Nothing below goes in the repository.

### Table A — Azure Key Vault

`kv-f2c-<env>-weu`. RBAC authorisation, purge protection on, 90-day retention, public endpoint,
`AuditEvent` to the environment's Log Analytics workspace — deploy.md 3.1.

Both are loaded by `provision-key-vault.sh` and referenced from the four API-image apps as
`keyvaultref:<vault>/secrets/<name>,identityref:<identity>`, resolved through the user-assigned
identity's **Key Vault Secrets User** grant. The reference carries no version: a rotation is a vault
operation plus a new revision, not an edit on four apps.

| Entry | Secret name in the vault | Value |
| --- | --- | --- |
| `DJANGO_FIELD_ENCRYPTION_KEY` | `django-field-encryption-key` | From `generate_keys.py`. Fresh per environment |
| `DJANGO_BLIND_INDEX_PEPPER` | `django-blind-index-pepper` | From `generate_keys.py`. Fresh per environment |

### Table B — Container App secrets

On all four API-image apps — api, worker, mail-worker, beat — referenced as `secretref:`.

**`DJANGO_REDIS_URL` is not on this table any more.** It was, because on Azure Managed Redis the
access key travels inside the URL. Redis is a container app reached over the environment's internal
network with no credential in the URL at all, so there is nothing in it to protect — and the
provisioning script sets it rather than asking for it. conflict.md **C36**.

| Entry | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | From `generate_keys.py` |
| `DJANGO_DB_PASSWORD` | Application user's MySQL password |
| `EMAIL_CC_PASSWORD` | Club mailbox password |
| `EMAIL_F2C_PASSWORD` | Market mailbox password |
| `DJANGO_PAYFAST_MERCHANT_ID` | Sandbox in QA and UAT, live in production |
| `DJANGO_PAYFAST_MERCHANT_KEY` | As above |
| `DJANGO_PAYFAST_PASSPHRASE` | Required, not optional — Payfast refuses subscriptions from a merchant without one |

### Table C — Container App environment variables (api, worker, mail-worker, beat)

Two entries are set by `provision-container-apps.sh` and appear on the apps rather than in the
values file: `DJANGO_REDIS_URL`, which names the Redis app at the environment's internal domain, and
`DJANGO_CACHE_ALLOW_PLAINTEXT=true`, which `f2c/cache.py` requires because Container Apps terminates
TLS for HTTP ingress and not for the TCP ingress a Redis connection needs. deploy.md 3 has the
argument and its limits.

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
| `DJANGO_DB_SSL_DISABLED` | `true` — and it must be set, not omitted. It turns off certificate *verification*, not encryption: `tls_options` returns nothing, mysqlclient applies `ssl_mode=PREFERRED`, and the connection is still TLS. Naming it makes the downgrade a decision on the record; leaving it blank gives the same connection with nobody having chosen it, and the container refuses to start. To verify instead, clear it and set `DJANGO_DB_SSL_CA=/etc/ssl/certs/ca-certificates.crt` — already in the image. conflict.md **C37** |
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

Leave unset: `DJANGO_DB_SSL_CA`, `DJANGO_CACHE_ALLOW_PLAINTEXT`, `EMAIL_CC_USE_SSL`,
`EMAIL_F2C_USE_SSL`, and every storage account key, SAS token and connection string. Each one
downgrades, overrides or contradicts something that is correct as it stands — `DJANGO_DB_SSL_CA`
alongside `DJANGO_DB_SSL_DISABLED` is refused outright rather than resolved.

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
| `AZURE_CLIENT_ID` | Environment | Written by `azure-oidc-setup (win).sh` |
| `AZURE_TENANT_ID` | Environment | Written by `azure-oidc-setup (win).sh` |
| `AZURE_SUBSCRIPTION_ID` | Environment | Written by `azure-oidc-setup (win).sh` |
| `AZURE_RESOURCE_GROUP` | Environment | `rg-f2c-qa-weu` |
| `CONTAINERAPP_API` | Environment | API container app name |
| `CONTAINERAPP_WORKER` | Environment | Worker container app name |
| `CONTAINERAPP_MAIL_WORKER` | Environment | Mail worker container app name |
| `CONTAINERAPP_BEAT` | Environment | Beat container app name |
| `CONTAINERAPP_CLUB` | Environment | Club frontend container app name |
| `CONTAINERAPP_MARKET` | Environment | Market frontend container app name |
| `DEPLOY_MARKET` | **Repository** | `true` to deploy the market storefront. **Environment scope does not work** — see below |

Twelve entries, and every one of them names something GitHub Actions has to address: a credential,
the registry, a resource group, a container app. **Nothing here is read by a running container.**

**`DEPLOY_MARKET` must be a repository variable.** `release.yml`'s `changes` job declares no
`environment:`, and `vars` in a job without one sees repository and organisation variables only. Set
on `qa` alone it reads as empty, every run skips the market image, and the log says
`vars.DEPLOY_MARKET is not 'true': skipping the market image` — which looks like a decision rather
than a misconfiguration. `ACR_NAME` is repository-scoped for the same reason: the workflow-level
`env:` block that builds `REGISTRY` is evaluated outside any job.

Set it to `false` explicitly on `uat` and `prod`. `promote.yml`'s `verify` job *does* declare an
environment, so the environment value wins there — and without an explicit `false` those two would
inherit the repository's `true` and lose the per-environment gate D2 asks for.

`APP_ENV`, `CLUB_SITE_URL`, `CLUB_CDN_BASE_URL`, `CLUB_SUPPORT_EMAIL` and `MARKET_SITE_URL` used to
be on this table as frontend build arguments, which is what stopped a frontend image being
promotable. They are container app settings now — Tables D and E, under their unprefixed names —
and can be deleted from the GitHub environments. Section 3, R-D4.

---

## Registry contents

```
f2c/api      :<sha>   plus the moving tags :qa :uat :prod
f2c/club     :<sha>   plus the moving tags :qa :uat :prod
f2c/market   :<sha>   plus the moving tags :qa :uat :prod
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

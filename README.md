# Cultivators Collective and Farm to Consumer

Django 6.1 on Python 3.14 (ASGI, Uvicorn) serving a JSON API, with **two** Next.js 16
applications that render every page — one per storefront. The club is Cultivators
Collective; the produce market is Farm to Consumer (F2C).

## Architecture

```
Browser ──> Next.js :3000  the club  ┐          Django :8000
            Next.js :3001  the store ┴────────> /api/...   JSON API (django-ninja)
            (App Router, SSR/RSC)               /api/docs  OpenAPI (DEBUG only)
                                                /admin/    Django admin
```

One API, one database, two storefronts on separate registrable domains. Which storefront
a request belongs to is a property of the host it arrived on, not of the member — see
[Two mail servers, one per storefront](#two-mail-servers-one-per-storefront).

Django renders no user-facing pages. Authentication is Django's own session
cookie: signing in sets an HttpOnly `sessionid`, the browser returns it on every
API call, and unsafe methods additionally carry a CSRF token. Next.js server
components forward the incoming cookies to Django so server-rendered pages know
who is signed in.

Members sign in with a passkey, falling back to a code emailed to them. See
[Authentication](#authentication).

The Django side is one app per feature, grouped by what each feature serves. The routers are
mounted on a single API instance in `f2c/api.py`, which is the only module that knows about all of
them. Adding a feature means adding one `add_router` line.

```
app/core/       accounts  authn  common  storefronts  documents  payments
app/commerce/   producers
app/club/       membership  strains  finished_product  plant
app/market/     nothing yet
```

| App | Owns |
| --- | --- |
| `core/accounts/` | The identity (`User`, this project's `AUTH_USER_MODEL`), the permission catalogue over it, a member's own profile and photograph, and the admin |
| `core/authn/` | Passkeys, emailed codes, sessions, rate limits — how somebody proves who they are |
| `core/storefronts/` | The club and the market, who administers one, and which storefront a request is for |
| `core/documents/` | Documents, their revisions, and the agreements given — scoped per storefront |
| `core/payments/` | The subscription, Payfast, and what a payment does to a membership |
| `core/common/` | Field encryption, RSA ID checks. No models, no endpoints |
| `commerce/producers/` | The farm as a record: trading name, appointed people, collection address, bank details |
| `club/membership/` | Club membership, the nickname, and turning a sign-up submission into a member |
| `f2c/` | Settings, URLs, and the API root the features mount on |

`core` knows nothing about what is sold; `commerce` is what both storefronts sell through; `club` is
the cannabis vertical. `market` is the produce vertical and is empty. Every app sets `label`
explicitly, so the tables are flat — `accounts_user`, not `core_accounts_user` — which is what made
the grouping a package move rather than a rename of every table.

Dependencies run one way: `authn`, `documents` and `payments` depend on `accounts`, `membership`
depends on all three, `accounts` depends on `common`, and nothing depends back. The one place that
direction is bent is `User.soft_delete`, which revokes credentials it does not own — see the comment
there.

| Concern | Lives in |
| --- | --- |
| The API root and router mounting | `f2c/api.py` |
| The member model | `accounts/models.py` (`User`) |
| Roles and what each may do | `accounts/roles.py` |
| Registering a sharing member | `accounts/services.py` |
| What a member may change about themselves | `accounts/profile.py` |
| Decoding and re-encoding an uploaded avatar | `accounts/avatars.py` |
| Where avatars are stored, and why they have no URL | `accounts/storage.py` |
| What a membership costs, and what a payment does to an account | `payments/services.py` |
| The Payfast protocol: signature, checkout, notification checks | `payments/gateway.py` |
| Resolving a `platform.*` permission | `accounts/backends.py` |
| Profile and avatar endpoints | `accounts/api.py` |
| Sign-in endpoints | `authn/api.py` |
| Passkey ceremonies | `authn/webauthn.py` |
| Emailed sign-in codes | `authn/otp.py` |
| Which server an email leaves by, and the record that it did | `storefronts/mail.py`, `storefronts/models.py` |
| Rate limits | `authn/throttles.py` |
| Field encryption and blind indexes | `common/crypto.py` |
| RSA ID number checks | `common/validators.py` |
| The club's pages, layout, components | `frontend/club/app`, `frontend/club/components` |
| The store's pages, layout, components | `frontend/market/app`, `frontend/market/components` |
| The frontend workspace root | `frontend/` — one lockfile, one `node_modules`, an application per storefront |
| Everything that calls Django, per application | `<app>/lib/api.ts` (browser), `<app>/lib/server-api.ts` (server) |
| The store's registration contract, and the endpoint it waits on | `frontend/market/lib/sign-up-api.ts` |

## First-time setup

Backend:

```
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Then generate a secret key and paste it into `.env` as `DJANGO_SECRET_KEY`:

```
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Generate two more secrets for `DJANGO_FIELD_ENCRYPTION_KEY` and
`DJANGO_BLIND_INDEX_PEPPER`. Run this twice and use a different value for each:

```
.venv\Scripts\python.exe -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Django refuses to start without all three.

Apply migrations and create a user. `createsuperuser` asks for an email
address, not a username -- the member model has no username field:

```
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
```

Frontend — one install for both applications, one `.env.local` each:

```
cd frontend
npm install
copy club\.env.example club\.env.local
copy market\.env.example market\.env.local
```

## Running

ASGI (use this by default):

```
.\runasgi.ps1
```

or directly:

```
.venv\Scripts\python.exe -m uvicorn f2c.asgi:application --reload
```

The site is then on http://127.0.0.1:8000/ and the admin on http://127.0.0.1:8000/admin/.

`manage.py runserver` still works, but Django 6.1 ships a WSGI-only development
server. Anything that depends on async views, async ORM access, streaming
responses, or long-lived connections must be tested through Uvicorn.

### The two storefronts

`.
undev.ps1` starts Django and one or both frontends, each in its own window:

```
.
undev.ps1                        # Django + the club on :3000
.
undev.ps1 -Storefront market     # Django + the store on :3001
.
undev.ps1 -Storefront both       # all three
```

Or directly, from `frontend/club` or `frontend/market`: `npm run dev`. The ports are set per
application, so the two never collide.

Sign in at **http://localhost:3000** or **http://localhost:3001**, never at `127.0.0.1`. An IP
address is not a valid WebAuthn Relying Party ID, and the session cookie needs the frontend and the
API to share a hostname.

**One local trap worth knowing about the store.** The storefront a request belongs to is resolved from
the host Django sees, and both applications call it on `localhost:8000`, which is unmapped — so it
falls back to `DJANGO_DEFAULT_STOREFRONT`, the club. Working on the store's `/legal` page therefore
means setting that variable to `market`, or expecting the club's documents to appear there. In a
deployment the two hosts differ and `DJANGO_STOREFRONT_HOSTS` does the work.

## The whole stack in Docker

```
docker compose up --build
```

That brings up five containers -- MySQL, Redis, Django, the club and the store -- and is the one
command that gets a working environment on a machine with nothing installed but Docker.

| | |
| --- | --- |
| the club | http://localhost:3000 |
| the produce store | http://localhost:3001 |
| the API and admin | http://localhost:8000 |
| MySQL, for a GUI client | `localhost:3307`, user `f2c`, password `dev-password` |
| Redis, for `redis-cli` | `localhost:6379` |

Sign in at `localhost`, never at `127.0.0.1`, for the same reason as outside Docker: an IP address
is not a valid WebAuthn Relying Party ID.

The first `up` creates an empty database and applies every migration. Then:

```
docker compose exec api python manage.py createsuperuser
```

Any management command runs the same way. Source is bind-mounted, so **an edit to a Python file
restarts the Django reloader by itself** -- that half works.

**A frontend edit does not.** Turbopack's watcher does not fire over a Docker Desktop bind mount on
Windows: the container sees the saved file and its new mtime and never recompiles, logging
`watch error ... NotFound` instead. `NEXT_WATCH_POLL_MS` is wired through to
`watchOptions.pollIntervalMs`, which is the switch Turbopack actually reads, and it does not change
this on Windows -- it is there for hosts where the watcher works. Until it does, a frontend change
needs:

```
docker compose restart club     # or market
```

which takes about a second, because `next dev` is already warm. If you are working on the frontend
for any length of time, `.
undev.ps1` outside Docker is the better loop -- HMR works natively and
the API in compose serves it either way.

A dependency change needs a rebuild in both directions: `pyproject.toml`, `poetry.lock` or
`package.json` means `docker compose build`.

`docker compose down` stops everything and keeps the database. `docker compose down -v` discards it.

### What this is not

**It does not rehearse a deployment, and the difference is deliberate.** There is no TLS in front of
these containers, so `DJANGO_DEBUG` is on -- without it `SESSION_COOKIE_SECURE` and
`CSRF_COOKIE_SECURE` are both set, a plain-HTTP browser stores neither cookie, and nobody can sign
in. `DJANGO_DEBUG` on is then exactly what the deployed entrypoint's
`check --deploy --fail-level WARNING` gate refuses, so the API container runs
`deploy/entrypoint.sh dev`, which skips that gate and starts `runserver` instead of Uvicorn.

Three consequences worth knowing:

- **Uvicorn is not what serves these requests.** Anything touching async views, async ORM access,
  streaming or long-lived connections has to be checked through `.
unasgi.ps1`, not here.
  `runserver` is used because `django.contrib.staticfiles` serves `/static/` by overriding that
  command -- under Uvicorn the admin renders with no stylesheets at all.
- **The frontends run `next dev`, not the deployed images.** `frontend/club/Dockerfile` and
  `frontend/market/Dockerfile` build the standalone servers that Container Apps runs;
  `frontend/Dockerfile.dev` is what compose uses.
- **`DJANGO_ENV` is `qa` in `compose.yaml`, and that is not a mistake.** `database_config` reads it
  before anything else and `dev` returns SQLite whatever host is configured, so `dev` here would run
  the stack on `db.sqlite3` while looking exactly like MySQL. CI sets `qa` for the same reason.

### The storefront trap, again

Both frontends call Django as `api`, so `request.get_host()` is the same for both and the storefront
cannot be resolved from it. Everything falls back to `DJANGO_DEFAULT_STOREFRONT`, the club. Working
on the store's documents or legal pages means:

```
DJANGO_DEFAULT_STOREFRONT=market docker compose up -d api
```

In a deployment the two API hostnames differ and `DJANGO_STOREFRONT_HOSTS` does the work.

### Your own `.env`

`compose.yaml` sets every variable the containers need, so no `.env` is required. Where one exists
it is still read -- the working tree is mounted and `settings.py` calls `load_dotenv` -- which is
why the mail and blob-storage variables are explicitly blanked in `compose.yaml`. Without that, a
developer whose `.env` holds real SMTP credentials would get a local stack sending live email.

Anything you do want to override -- `DJANGO_SECRET_KEY`, the encryption keys, `MYSQL_HOST_PORT` if
3307 is taken -- goes in `.env` and is picked up through the `${VAR:-default}` forms in
`compose.yaml`.

## Tests

Backend, 794 tests:

```
.venv\Scripts\python.exe manage.py test
```

Each app tests what it owns, and `manage.py test <app>` runs just that app:

| Suite | Tests | Covers |
| --- | --- | --- |
| `common/tests/` | 41 | Encryption round-trips, the blind index, RSA ID checks |
| `accounts/tests/` | 244 | The member record, roles and permissions, the admin form over the encrypted ID number, a member's own profile, and the avatar pipeline |
| `authn/tests/` | 138 | The sign-in endpoints, both credential services, the rate limits |
| `documents/tests/` | 115 | Documents, revisions, agreements, storage, the publish command |
| `membership/tests/` | 88 | The registration write and the endpoints in front of it |
| `payments/tests/` | 219 | The Payfast signature and configuration, what a payment does to a membership, both endpoints, the constraints, the two commands, the read-only admin |
| `f2c/tests/` | 12 | The brand skin over the Django admin |

Frontend, 2270 tests — 1932 in the club and 338 in the store:

```
cd frontend
npm test                                  # both applications
npm test --workspace @f2c/market-web      # just the store
npm run test:watch
npm run test:coverage
```

Vitest with jsdom and Testing Library, colocated beside what they test. `npm run typecheck` is
separate and also expected to pass. Both scripts run across the workspaces, so a failure in either
application fails the command.

## Design documentation

`design/` records what this product is and why each significant decision went the way it did.
Start with [design/README.md](design/README.md).

| Document | Covers |
| --- | --- |
| `design/frontend.md` | Rendering model, routes, module layers, configuration, testing |
| `design/backend.md` | The member record, encryption, API surface, admin, testing |
| `design/features/roles-and-permissions.md` | The three roles, the action catalogue, and where each is enforced |
| `design/features/authentication.md` | Passkeys, emailed codes, sessions, rate limits |
| `design/features/sign-up.md` | Age gate, member details, club document agreements |
| `design/features/payments.md` | The membership subscription, Payfast, and what a payment does to an account |
| `design/features/landing.md` | The public landing page and its copy governance |
| `design/features/brand.md` | Colour, typography, artwork and the design tokens |

Each document ends in a numbered risk table, and each has a *What is not built* section. Two things
worth reading before planning work: the authenticated frontend is written but not routed
(`design/frontend.md` section 9), and roles are built ahead of everything they govern -- the three
roles, the action catalogue and the enforcement path all work, while plants, strains, orders, swaps
and the cultivator organisation do not exist
(`design/features/roles-and-permissions.md` section 12).

## Authentication

Members do not have a password. Two credentials get them in:

1. **A passkey.** A WebAuthn credential held by the device -- Face ID, Windows
   Hello, a security key, or a passkey synced through iCloud Keychain or Google
   Password Manager. Nothing shared is ever transmitted, so there is nothing to
   phish or reuse.
2. **A code emailed to them.** Six digits, valid for five minutes, single use,
   burned after five wrong guesses. This is the fallback when the member has no
   passkey, is on a device that does not have theirs, or simply asks for a code.

Sign-in is identifier-first. `POST /api/auth/login/start` takes an email address
and answers with either a WebAuthn challenge or `{"method": "otp"}` -- the
latter also being the answer for an address with no account, so the endpoint
cannot be used to find out who is a member.

A new account therefore always signs in by email code the first time; the
passkey is enrolled afterwards from **Security** in the member area. That makes
the code path a front door, not a back door, which is why it is rate limited
per IP and per code.

Staff sign in with a password at Django admin's own login view,
`/admin/login/`. There is no password endpoint on the API — one existed and was
deleted, because nothing called it and members hold an unusable password hash.

Only an account with status **Active** can sign in. Pending, Suspended and
erased accounts are all refused identically, and the refusal never says which.

### Endpoints

| Endpoint | Session needed | Purpose |
| --- | --- | --- |
| `POST /api/auth/login/start` | No | Resolve an email to a passkey challenge, or send a code |
| `POST /api/auth/login/passkey` | No | Verify a WebAuthn assertion and open a session |
| `POST /api/auth/otp/start` | No | Send or resend a sign-in code |
| `POST /api/auth/otp/verify` | No | Exchange a code for a session |
| `POST /api/auth/logout` | No | End the session |
| `GET /api/auth/me` | Yes | The signed-in user |
| `POST /api/auth/passkeys/options` | Yes | Options for enrolling a passkey |
| `POST /api/auth/passkeys` | Yes | Store a verified new passkey |
| `GET /api/auth/passkeys` | Yes | List the member's passkeys |
| `DELETE /api/auth/passkeys/{id}` | Yes | Revoke one |
| `GET /api/accounts/me/profile` | Yes | The member's own record, identity number masked |
| `PUT /api/accounts/me/profile` | Yes | Replace the three editable fields |
| `POST /api/accounts/me/avatar` | Yes | Store a photograph, decoded and re-encoded |
| `GET /api/accounts/me/avatar` | Yes | Stream it. The only endpoint here that is not JSON |
| `DELETE /api/accounts/me/avatar` | Yes | Take it down and delete the blob |

No endpoint under `/api/accounts/` takes an account identifier. That is the
design rather than an omission: an endpoint that took one would have to decide
whether the caller may act on it, and the only correct answer for a profile is
"only your own". Removing the parameter removes the decision.

### Passkeys have hard hosting requirements

The Relying Party ID is a registrable domain and is bound to the origin the
JavaScript runs on -- the Next.js origin, not Django's. Three consequences:

- **Locally, sign in at `http://localhost:3000`, never `http://127.0.0.1:3000`.**
  An IP address is not a valid RP ID and passkeys will not work there. The
  session cookie has the same requirement for a different reason.
- **Everywhere else needs HTTPS.** `localhost` is the only exemption the
  browser makes.
- **In production both halves must sit under one registrable domain**, e.g.
  `app.example.co.za` and `api.example.co.za` with
  `DJANGO_WEBAUTHN_RP_ID=example.co.za`.

### Two mail servers, one per storefront

The club and the produce market are separate businesses on separate domains with
separate mailbox providers, so `MAILERS` holds one SMTP mailer per storefront:
`club` from the `EMAIL_CC_*` variables, `market` from the `EMAIL_F2C_*` ones. The
aliases are the storefront codes themselves, so routing is
`.send(using=storefront)` with nothing to look up.

Nothing chooses a mailer directly. `app/core/storefronts/mail.py` is the one
place that asks, and it resolves three things together -- the server, the `From`
address and the name in the subject and signature. They have to agree: a sign-in
code sent through the store's provider but signed "Cultivators Collective" is
indistinguishable from a phishing attempt.

**The storefront comes from the host, not from the member.** A code requested at
the store's domain leaves the store's server, whatever the member belongs to --
`storefront_for_request`, the same signal `webauthn.rp_id` uses. A code has to be
sendable to an address with no account at all, so there is nothing else to ask.
Mail that is inherently one storefront's business names it outright instead; the
membership checkout link is always the club's.

There is deliberately **no fallback to the other storefront's server**. With
`DEBUG=False` a blank `EMAIL_*_HOST` or `EMAIL_*_FROM` refuses to start, because
the alternative sends successfully -- nothing looks wrong, and a storefront's
members are receiving mail from a provider that has no business holding their
address. `storefronts/checks.py` catches the same class of fault in code: a
storefront added to `Storefront` without a mailer fails `manage.py check` rather
than quietly borrowing the club's.

### Emailed codes in development

Leave both `EMAIL_*_HOST` blank and every storefront falls back to the console
backend, so codes are printed to the terminal running Uvicorn rather than sent.
Look for the message body in that output.

Django 6.1 has no async email API, so the mail hand-over -- and password
hashing, which is deliberately slow -- runs in a worker thread rather than on the
event loop. The hand-over alone: `storefronts/mail.py` keeps the database writes
on the caller's connection, because a worker thread holds one of its own and it
cannot see the transaction the request is running in.

### Every email sent is recorded

`storefronts.EmailDispatch` is one row per message: which member, which of the
platform's four emails it was, which storefront's letterhead it carried, when it
was queued, whether the mail server took it and when, and what it said if it
refused. Also **what caused it** -- the platform itself, the recipient, or a
named operator -- which is how a suspension notice is traced back to the person
who suspended the member.

Nothing can send without being recorded, because `send_storefront_email` is the
only thing in the project that builds an `EmailMessage`. The row is written
*before* the hand-over, so a process that dies mid-send leaves a row saying
`queued` rather than no trace of a message that may well have gone out.

**Two of the three stages sit empty, and that is honest rather than unfinished.**

| Stage | What this deployment knows |
| --- | --- |
| Sent | Whether the mail server accepted it, and when. Genuinely known. |
| Delivered | Nothing. SMTP does not report delivery; a relay accepting a message is not the message arriving. Needs a provider that emits events. |
| Read | Nothing, deliberately. An open is only knowable through an invisible image in the body, which is not something to put in a one-time code. |

So `delivery_status` reads *not reported* and `read_status` reads *not tracked* --
neither of which is the same statement as "no". Closing the delivery half is a
provider with webhooks, DKIM/SPF/DMARC per storefront domain, and one signed
route; `EmailDispatch.apply_provider_event` is the handler behind it and is
already written and tested. `storefronts/mail.py` already reads a provider
message id off the sent message where the backend supplies one, so the join a
webhook needs is in place.

The log holds **no email address and no message body**. Every email the platform
sends goes to a member record, so the row points at the account and the address is
read off it at send time -- which means POPIA erasure de-identifies the send
history in the same write, with no scrub step to remember. The body is excluded
because a sign-in code and a payment link both live in it.

Retention is `EMAIL_DISPATCH_RETENTION_DAYS`, twelve months by default, enforced
by `manage.py purge_email_dispatches` on a timer. `--dry-run` reports without
deleting; `0` keeps everything. The log is read at
**Storefronts → Emails sent** in the Django admin, read-only throughout.

### Rate limits

Set in `NINJA_DEFAULT_THROTTLE_RATES` and enforced through the cache. **In
production this must be a shared cache** (Redis or Memcached); the default
per-process `LocMemCache` would let each Uvicorn worker count separately.

## Members

`accounts.User` is the project's `AUTH_USER_MODEL`. Members and staff are one model
told apart by `is_staff`, rather than a default user for admin plus a separate
member model, which would mean a second authentication stack and two identities
for anyone who is both.

The primary key is a UUIDv7 -- time-ordered, so inserts land at the end of the
index instead of scattering across it -- and the sign-in identifier is a unique,
lower-cased email address.

### Status, not a boolean

`status` is the source of truth: Pending, Pending payment, Active, Suspended,
Inactive, Sharing. Only Active signs in. Sharing is the one value that is not a
stage in a lifecycle -- it is where a sharing member sits permanently, holding
stock without ever signing in. `is_active` is a denormalised copy of
`status == 'active'`,
because Django's auth stack filters on it in SQL and a Python property would
break every queryset. `save()` derives it, and a database check constraint
rejects any write that changes one without the other -- including
`.update()` and raw SQL.

### Roles, and what each one may do

Every account holds exactly one role -- Admin, Cultivator, Member or Sharing member -- in a column
with a check constraint. Registration makes a Member; Admin and Cultivator are appointed in the
Django admin, because both carry authority over records that are not the account's own. A **sharing
member** is registered by a cultivator: a name, an identity number and a nickname, four flowering
plants, and no way to sign in -- an identity that seeds the swap zone so a new club's zone is not
empty. It holds no permissions at all, a check constraint keeps the role out of Active, and a second
one refuses a record with no registering cultivator, no consent attestation or no nickname. The
attestation is the club's POPIA basis for holding a third party's identity number, and it is called
an attestation rather than a consent because a cultivator's word is weaker evidence than the person's
own tick.

A Django group was the obvious alternative and was rejected as the source of truth: a group is
runtime data, an account can belong to none or to all four, and no constraint can say "exactly
one". The groups exist anyway, mirrored from the column, so the model permissions the plant and
strain apps will bring can be attached to a role in one place.

What each role may do is a dictionary in `accounts/roles.py` rather than `auth.Permission` rows,
because almost every action is against a model that does not exist yet and a permission row needs a
content type, which needs a model. A second authentication backend resolves it, so
`user.has_perm('platform.purchase_plants')` works today and one call still covers both kinds of
permission. It authenticates nobody.

Two separations are worth knowing. **Role is not status:** an inactive account holds nothing
whatever its role, so suspension and erasure needed no knowledge of roles to stay safe. **Role is
not `is_staff`:** `is_staff` opens the Django admin, `role` opens the platform's administrative
actions, and neither derives from the other -- the cost being two places to grant privilege, which
the admin states rather than hides.

The catalogue, the rejected alternatives and the long list of what roles govern that is not yet
built are in [design/features/roles-and-permissions.md](design/features/roles-and-permissions.md).

### The ID number is encrypted, and still searchable

`user.id_number` reads and writes an AES-256-GCM column with a fresh nonce per
row, so the ciphertext leaks nothing -- not even which two members share a
number. That also makes it unindexable, so a second column holds a keyed HMAC
of the same value: exact-match lookups (`User.objects.by_id_number(...)`) and a
unique constraint of one account per identity document, with no plaintext
anywhere.

Two secrets back this, both separate from `DJANGO_SECRET_KEY` so that rotating
the secret key does not make every stored ID number unreadable. **Lose
`DJANGO_FIELD_ENCRYPTION_KEY` and the ID numbers are gone; there is no recovery
path.** Back it up somewhere other than the database.

A 13-digit number is validated as an RSA ID -- structure, embedded date,
citizenship digit, Luhn check -- and `capture_sa_id_number()` reads
`date_of_birth` off the document itself so the two cannot disagree.
`date_of_birth_verified_at` records when a human checked it; null means
unverified, whatever the member typed.

The admin never displays a full ID number, only the last four digits.

### Erasure

`user.soft_delete()` is the POPIA erasure route, exposed in the admin as
**Erase selected accounts**. It clears name, nickname, email address and ID
number, sets the status to Inactive, stamps `deleted_at`, and revokes every
passkey, outstanding code and live session -- an already signed-in browser is
signed out, not left working until its cookie expires.

The row itself survives, because operating records point at it and cascading
those away would destroy the collective's own history. One field deliberately
survives with it: `email_hash`, a keyed digest that answers
`User.objects.has_been_seen(address)` without the erased record keeping the
address. An erased account cannot be reactivated, and the address is free to
register again as a new member.

`user.deactivate()` is the reversible half: it blocks sign-in and cuts sessions
but erases nothing.

## Configuration

All environment-specific settings are read from the environment, with `.env`
loaded automatically in development. `.env` is gitignored; `.env.example`
documents every variable.

| Variable | Required | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Yes | Startup fails without it. |
| `DJANGO_FIELD_ENCRYPTION_KEY` | Yes | 32 bytes, base64. Encrypts ID numbers. Losing it loses them permanently. |
| `DJANGO_BLIND_INDEX_PEPPER` | Yes | 32 bytes, base64. Keys the searchable digests of ID numbers and emails. |
| `DJANGO_DEBUG` | No | Defaults to `False`. |
| `DJANGO_ALLOWED_HOSTS` | When `DEBUG=False` | Comma-separated. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | No | Comma-separated, scheme included. Must include the frontend origin. Defaults to `localhost:3000` when `DEBUG=True`. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | When `DEBUG=False` | Browser origins allowed to call the API. Defaults to `localhost:3000` when `DEBUG=True`. |
| `DJANGO_WEBAUTHN_RP_ID` | When `DEBUG=False` | Registrable domain of the frontend. Not a URL, not an IP. Defaults to `localhost` when `DEBUG=True`. |
| `DJANGO_WEBAUTHN_RP_NAME` | No | Name the authenticator shows the member. |
| `DJANGO_WEBAUTHN_ORIGINS` | When `DEBUG=False` | Full frontend origins allowed to present credentials. Defaults to `localhost:3000` when `DEBUG=True`. |
| `DJANGO_DEFAULT_FROM_EMAIL` | No | Fallback sender, used only where a storefront names none of its own. |
| `EMAIL_CC_HOST` | When `DEBUG=False` | The club's SMTP server. Blank means the console backend. |
| `EMAIL_CC_PORT` | No | Defaults to 587 with TLS, 465 with SSL. |
| `EMAIL_CC_USER` / `EMAIL_CC_PASSWORD` | With a host | SMTP credentials. |
| `EMAIL_CC_USE_TLS` / `EMAIL_CC_USE_SSL` | No | STARTTLS on 587, or implicit TLS on 465. Mutually exclusive; TLS defaults on. |
| `EMAIL_CC_FROM` | When `DEBUG=False` | The address club mail is sent as. Normally must be one the provider is authorised to send for. |
| `EMAIL_F2C_*` | Same as above | The store's server and sender. Same five variables, same rules. |
| `EMAIL_DISPATCH_RETENTION_DAYS` | No | Days of send history to keep. 365 by default; `0` keeps everything. Enforced by `manage.py purge_email_dispatches`. |
| `DJANGO_CDN_BASE_URL` | With a container | Public prefix the documents are served from. Https outside local development, and its path must match the container. |
| `DJANGO_DOCUMENT_STORAGE_CONTAINER` | No | The blob container the CDN fronts. Blank means uploads go to `MEDIA_ROOT` and are served by runserver. |
| `DJANGO_DOCUMENT_STORAGE_ACCOUNT` | With a container | Storage account name. Not needed if a connection string is set. |
| `DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY` | No | Account key. Leave blank on App Service and use the managed identity. |
| `DJANGO_DOCUMENT_STORAGE_SAS_TOKEN` | No | Used when no account key is set. Needs container write permission, and expires. |
| `DJANGO_DOCUMENT_STORAGE_CONNECTION_STRING` | No | Account and key together. Overrides `DJANGO_DOCUMENT_STORAGE_ACCOUNT`. |
| `DJANGO_DOCUMENT_STORAGE_LOCATION` | No | Blob-name prefix inside the container. Normally blank. |
| `DJANGO_AVATAR_STORAGE_CONTAINER` | No | A **private** container for member photographs, distinct from the documents one. Startup fails if the two match. Blank means uploads go to `MEDIA_ROOT`. |
| `DJANGO_AVATAR_STORAGE_ACCOUNT` | With a container | Storage account name. Not needed if a connection string is set. |
| `DJANGO_AVATAR_STORAGE_ACCOUNT_KEY` | No | Account key. Leave blank on App Service and use the managed identity. |
| `DJANGO_AVATAR_STORAGE_SAS_TOKEN` | No | Used when no account key is set. |
| `DJANGO_AVATAR_STORAGE_CONNECTION_STRING` | No | Account and key together. Overrides `DJANGO_AVATAR_STORAGE_ACCOUNT`. |
| `DJANGO_AVATAR_STORAGE_LOCATION` | No | Blob-name prefix inside the container. Normally blank. |
| `DJANGO_PAYFAST_MERCHANT_ID` | When `DEBUG=False` | From the Payfast dashboard. Falls back to Payfast's published sandbox merchant under `DEBUG`. |
| `DJANGO_PAYFAST_MERCHANT_KEY` | When `DEBUG=False` | Secret. Application settings, not source control. |
| `DJANGO_PAYFAST_PASSPHRASE` | When `DEBUG=False` | Set the same value on the Payfast account. Payfast refuses subscriptions from a merchant without one. |
| `DJANGO_PAYFAST_SANDBOX` | No | Defaults to the sandbox in **every** environment. Live is reached only by setting this false. |
| `DJANGO_PAYFAST_RETURN_URL` | When `DEBUG=False` | Frontend page a paid member returns to. Https outside local development. |
| `DJANGO_PAYFAST_CANCEL_URL` | When `DEBUG=False` | Frontend page a member who cancelled returns to. |
| `DJANGO_PAYFAST_NOTIFY_URL` | When `DEBUG=False` | Django's own public address for Payfast's server-to-server notification. Must be reachable from the internet. |
| `DJANGO_MEMBERSHIP_CHECKOUT_URL` | When `DEBUG=False` | Frontend page a checkout token is paid from, without the token. The emailed link is this plus the token. |
| `DJANGO_PAYFAST_BEHIND_PROXY` | No | Read `X-Forwarded-For` for the notification source check. Only where the edge **overwrites** that header. |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT` | When `DEBUG=False` | Rands and cents. Applies to new subscriptions only; 0 is refused. |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY` | No | `monthly`, `quarterly`, `biannual` or `annual`. Defaults to monthly. |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES` | No | Billings to take, or 0 for until the member cancels. |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_ITEM_NAME` | No | What the member sees on the Payfast page and their statement. |
| `DJANGO_MEMBERSHIP_SUBSCRIPTION_DESCRIPTION` | No | Longer description on the Payfast receipt. |

Frontend variables live in `frontend/.env.local`, documented in
`frontend/.env.example`. `CDN_BASE_URL` is still required there but is no longer
read by anything: Django owns the club document addresses now, because it owns
their versions.

## Payments

A member registered through sign-up sits at **Pending payment** and cannot sign
in. What moves them to Active is a Payfast payment, and `app/core/payments` owns it.

Registration opens a `Subscription` in the same transaction that writes the
member, and hands back a checkout token. The frontend turns that into a form POST
to Payfast; Payfast bills the mandate on its own schedule; and Payfast's
**server-to-server notification** to `POST /api/payments/payfast/notify` is what
records the payment and activates the account.

**The member's return from Payfast activates nothing.** That is a browser
redirect -- theirs to replay, bookmark or forge -- so `/signup/paid` reads nothing
and says the payment is being confirmed rather than that the membership is
active. Getting these two the wrong way round is the classic payment-integration
hole.

A notification has to pass four independent checks before it changes anything:
the source address resolves to one of Payfast's notification hosts, the merchant
id is ours, the signature verifies, and Payfast confirms it sent it. The reason a
notification was refused is logged and never returned -- naming the failed check
tells an attacker which one to fix. Applying one twice is a no-op, because
Payfast retries and a unique index on its payment id makes the second delivery
idempotent.

The arrangement is a **recurring subscription**. Payfast holds the mandate; this
application runs no billing job. The price and cycle are copied onto each
subscription when it is opened, so changing the configured amount changes what
new members are asked for and nothing about what existing ones agreed to.

A cancellation does **not** switch a member off -- they keep the period they paid
for. Access is withdrawn by `manage.py lapse_memberships`, which compares
`paid_until` against today, and **nothing schedules it yet**:

```
.venv\Scripts\python.exe manage.py lapse_memberships --dry-run
.venv\Scripts\python.exe manage.py lapse_memberships
```

### Payments in development

Payfast cannot reach a localhost `notify_url`, so the one step that activates a
membership never fires on a developer's machine. This stands in for it, signing a
real payload and running it through the real verification:

```
.venv\Scripts\python.exe manage.py payfast_notify --email someone@example.com
.venv\Scripts\python.exe manage.py payfast_notify --email someone@example.com --status CANCELLED
```

It refuses to run with `DEBUG=False`. In a deployed environment the honest route
for somebody who paid another way is **Activate selected accounts** in the member
admin, which records an account change and claims no payment.

With no merchant configured and `DEBUG=True`, Payfast's own published sandbox
merchant is used, so the whole flow works on a fresh clone.

The full design -- including the sign-up non-disclosure rule this feature
narrows, and why -- is in
[design/features/payments.md](design/features/payments.md).

## Club documents

The three documents a joining member agrees to -- the club rules, the annexures
and the constitution -- are rows rather than files in the repository. Staff
upload a PDF in the Django admin under **Club documents**, set a version label
and the sentence a member ticks, then run the **Publish** action. The next
member to open `/signup` reads that revision.

A published revision is immutable and cannot be deleted: updating a document
means publishing a new one. Every agreement points at the revision it was given
against and carries a digest of both the file and the wording as they stood at
that moment, so "which text did this member agree to?" is answered by the
record rather than by whatever the document says today.

Tick **requires reacceptance** when a change is material and members who agreed
to an earlier revision will be asked again; leave it unticked for a typo fix.

For the initial load, or a deployment pipeline:

```powershell
.venv\Scripts\python.exe manage.py publish_club_document constitution 2 .\F2C_Club_Constitution_2.pdf `
  --consent-text "I have read and agree to the Constitution" --material --note "AGM 2026 amendments"
```

Sign-up fails closed: until every required document has a published revision,
`GET /api/documents/current` answers 503 and `/signup` shows *Joining is
briefly unavailable* rather than a form with a missing agreement. See
`design/features/sign-up.md` section 5.

### Where the files go

Azure Blob Storage, fronted by the CDN. An admin upload writes the blob
directly; nobody copies anything by hand.

The blob name carries the version -- `documents/<document>/<version>/<file>` --
so publishing a revision writes a new blob rather than replacing one members
have already agreed to, and nothing in front of it ever needs purging. That is
also why the blobs are sent with a one-year immutable `Cache-Control`.

An Azure blob URL always carries the container as its first path segment, and
only the host is replaced by `DJANGO_CDN_BASE_URL`. So a CDN base of
`https://qa-static.urup.com/consumer-collective` and a container named
`consumer-collective` describe the same address, and startup **fails** if the
two disagree -- the alternative symptom is every document link 404ing after a
deploy.

On App Service, set no secret: give the App Service managed identity the
**Storage Blob Data Contributor** role on the container and leave
`DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY` blank. An account key and a SAS token both
work and are read in preference to the identity, so a key left in application
settings is never silently ignored.

URLs are unsigned (`expiration_secs=None`): these links go into a page anyone
can open, and a SAS token in them would expire.

## A member's own profile

`/profile` is one screen for all three roles, guarded by a session rather than a
role: every account that can sign in has exactly one profile, and it is the same
screen. It splits into what a member may change and what they may only read.

| | Fields | Where |
| --- | --- | --- |
| Theirs to change | First name, last name, mobile number | `PUT /api/accounts/me/profile` |
| Shown, changed by the club | Nickname, email address | Django admin |
| Shown, taken from a document | Date of birth, identity number (masked) | Django admin |

The email address is not editable because it is the sign-in identifier, and
swapping it needs proof the new address receives mail. The nickname is unique
across the club and other members know each other by it. The last two came off an
identity document, and a field a member can retype is a field
`date_of_birth_verified_at` would no longer be telling the truth about. Each
reason is recorded in `accounts/profile.py`.

The identity number crosses the wire **masked and only masked** -- all but its
last four digits replaced -- and `accounts.profile` has no way to produce any
other form, so the endpoint cannot be talked into disclosing one. The masking is
`common.validators.mask_id_number`, shared with the Django admin so the two
cannot drift.

### Where a photograph goes

A **private** container of its own, and never the one the CDN fronts. A club
document is published to everybody; an avatar is a photograph of somebody's face.
The container has no public access, no SAS is minted, and nothing calls `.url()`
on that backend -- so an avatar has exactly one address:

```
GET /api/accounts/me/avatar?v=<avatar_updated_at>
```

which checks the session before it streams a byte. The cost is accepted: avatars
are served by the application rather than by a CDN. They are 512-pixel squares of
a few tens of kilobytes, cached privately for a week, and a member looks at their
own. `accounts/storage.py` **refuses to start** if `DJANGO_AVATAR_STORAGE_CONTAINER`
names the documents container, because that mistake would publish every member's
photograph.

Every upload is decoded and **re-encoded** by Pillow rather than stored as it
arrived (`accounts/avatars.py`). That one decision does most of the work: a file
that is not an image is refused, a polyglot loses the half that was not pixels,
and EXIF goes -- including the GPS coordinates a phone writes into a photograph,
which most members do not know is there. The orientation tag is applied before it
is discarded, which is the one piece of EXIF that matters; dropping it without
acting on it turns every portrait upload on its side.

The browser crops before it uploads, and none of that is trusted. The crop
geometry is pure and tested in `frontend/club/lib/image-crop.ts`, and it holds one
invariant on every pan and zoom: the square is always inside the image. Only the
square is uploaded -- the rest of the frame never leaves the browser.

Erasure deletes the blob, not just the column. See `User.soft_delete`.

## Not yet configured

Production deployment is deliberately out of scope for now. When a target is
chosen, it needs: a process manager fronting Uvicorn (Gunicorn with
`UvicornWorker` on Linux), static file handling (`STATIC_ROOT` plus WhiteNoise
or a CDN), a real database, and the Django deployment checklist
(`manage.py check --deploy`).

Authentication adds two more: a real email provider in `MAILERS` (codes are
printed to the console today) and a shared cache backend, without which the
auth rate limits are per worker rather than per deployment.

The send log adds a scheduled job rather than a service: `manage.py
purge_email_dispatches`, nightly, which is what turns `EMAIL_DISPATCH_RETENTION_DAYS`
from a number into a retention policy. Nothing breaks without it; the table
simply grows and keeps personal information past the window the deployment says
it keeps it for.

The club documents add one: an Azure Blob Storage container behind the CDN, and
the `DJANGO_DOCUMENT_STORAGE_*` variables above. Without it the PDFs are written
to `MEDIA_ROOT` and served by runserver, which is fine locally and is not a
deployment.

Member avatars add a second, and it must be a **private** container -- the
`DJANGO_AVATAR_STORAGE_*` variables above. Without it photographs are written to
`MEDIA_ROOT`, where under `DEBUG` runserver's static handler will serve one to
anybody who guesses the path. Fine on a developer's machine; a deployment either
configures the container or puts a web server on `MEDIA_URL` that does not serve
the `avatars/` prefix.

Payments add three. A **Payfast merchant** and the `DJANGO_PAYFAST_*` variables
above -- Django refuses to start without them once `DEBUG` is off, because a
payment integration that silently falls back to a sandbox is one that takes a
member's money into an account nobody is watching. A **publicly reachable
`notify_url`**, because Payfast's notification is server-to-server and it is the
only thing that activates a membership; nothing on localhost can receive one, and
`manage.py payfast_notify` stands in for it in development. And **something that
runs `manage.py lapse_memberships`** on a schedule -- a daily cron or an App
Service WebJob. Until that exists an unpaid or cancelled membership keeps its
access indefinitely, which is the largest gap in the feature and is recorded as
risk 2 in `design/features/payments.md`.

The real email provider matters twice over now: the payment link emailed to a
member whose address is already on file is the whole fallback for a duplicate
registration, and with the console backend it reaches nobody.

The frontend adds two requirements. Serve both halves under one registrable
domain (`app.example.co.za` and `api.example.co.za`) so the `SameSite=Lax`
session cookie still reaches the API; a genuinely cross-site split needs
`SameSite=None` plus HTTPS. And set `DJANGO_API_URL` to the internal address
Next.js can reach and `DJANGO_API_PUBLIC_URL` to the public one. Both are read
at request time: the second is rendered into the document by the root layout and
read from there by `lib/api.ts`, so one image serves any environment.

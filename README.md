# Cultivators Collective

Django 6.1 on Python 3.14 (ASGI, Uvicorn) serving a JSON API, with a Next.js 16
frontend that renders every page.

## Architecture

```
Browser ──> Next.js :3000            Django :8000
            (App Router, SSR/RSC) ──> /api/...   JSON API (django-ninja)
                                      /api/docs  OpenAPI (DEBUG only)
                                      /admin/    Django admin
```

Django renders no user-facing pages. Authentication is Django's own session
cookie: signing in sets an HttpOnly `sessionid`, the browser returns it on every
API call, and unsafe methods additionally carry a CSRF token. Next.js server
components forward the incoming cookies to Django so server-rendered pages know
who is signed in.

Members sign in with a passkey, falling back to a code emailed to them. See
[Authentication](#authentication).

The Django side is one app per feature. Each owns its own models, admin, schemas and router;
the routers are mounted on a single API instance in `cultivatorscollective/api.py`, which is the
only module that knows about all of them. Adding a feature means adding one `add_router` line.

| App | Owns |
| --- | --- |
| `accounts/` | The member record (`User`, this project's `AUTH_USER_MODEL`) and the admin over it |
| `authn/` | Passkeys, emailed codes, sessions, rate limits — how a member proves who they are |
| `documents/` | Club documents, their revisions, and the agreements members give |
| `common/` | Field encryption, RSA ID checks. No models, no endpoints |
| `cultivatorscollective/` | Settings, URLs, and the API root the features mount on |

Dependencies run one way: `authn` and `documents` depend on `accounts`, `accounts` depends on
`common`, and nothing depends back. The one place that direction is bent is
`User.soft_delete`, which revokes credentials it does not own — see the comment there.

| Concern | Lives in |
| --- | --- |
| The API root and router mounting | `cultivatorscollective/api.py` |
| The member model | `accounts/models.py` (`User`) |
| Sign-in endpoints | `authn/api.py` |
| Passkey ceremonies | `authn/webauthn.py` |
| Emailed sign-in codes | `authn/otp.py` |
| Rate limits | `authn/throttles.py` |
| Field encryption and blind indexes | `common/crypto.py` |
| RSA ID number checks | `common/validators.py` |
| Pages, layout, components | `frontend/app`, `frontend/components` |
| Everything that calls Django | `frontend/lib/api.ts` (browser), `frontend/lib/server-api.ts` (server) |

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

Frontend:

```
cd frontend
npm install
copy .env.example .env.local
```

## Running

ASGI (use this by default):

```
.\runasgi.ps1
```

or directly:

```
.venv\Scripts\python.exe -m uvicorn cultivatorscollective.asgi:application --reload
```

The site is then on http://127.0.0.1:8000/ and the admin on http://127.0.0.1:8000/admin/.

`manage.py runserver` still works, but Django 6.1 ships a WSGI-only development
server. Anything that depends on async views, async ORM access, streaming
responses, or long-lived connections must be tested through Uvicorn.

## Tests

Backend, 333 tests:

```
.venv\Scripts\python.exe manage.py test
```

Each app tests what it owns, and `manage.py test <app>` runs just that app:

| Suite | Tests | Covers |
| --- | --- | --- |
| `common/tests/` | 12 | Encryption round-trips, the blind index, RSA ID checks |
| `accounts/tests/` | 59 | The member record, and the admin form over the encrypted ID number |
| `authn/tests/` | 137 | The sign-in endpoints, both credential services, the rate limits |
| `documents/tests/` | 113 | Documents, revisions, agreements, storage, the publish command |
| `cultivatorscollective/tests/` | 12 | The brand skin over the Django admin |

Frontend, 859 tests:

```
cd frontend
npm test
npm run test:watch
npm run test:coverage
```

Vitest with jsdom and Testing Library, colocated beside what they test. `npm run typecheck` is
separate and also expected to pass.

## Design documentation

`design/` records what this product is and why each significant decision went the way it did.
Start with [design/README.md](design/README.md).

| Document | Covers |
| --- | --- |
| `design/frontend.md` | Rendering model, routes, module layers, configuration, testing |
| `design/backend.md` | The member record, encryption, API surface, admin, testing |
| `design/features/authentication.md` | Passkeys, emailed codes, sessions, rate limits |
| `design/features/sign-up.md` | Age gate, member details, club document agreements |
| `design/features/landing.md` | The public landing page and its copy governance |
| `design/features/brand.md` | Colour, typography, artwork and the design tokens |

Each document ends in a numbered risk table, and each has a *What is not built* section. Two things
worth reading before planning work: the authenticated frontend is written but not routed
(`design/frontend.md` section 9), and sign-up stores nothing -- the consent ledger exists and is
tested, but there is no member row to write an agreement against
(`design/features/sign-up.md` section 6).

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

Staff keep email and password sign-in at `POST /api/auth/login`, because
Django admin needs it. The frontend no longer offers it.

Only an account with status **Active** can sign in. Pending, Suspended and
erased accounts are all refused identically, and the refusal never says which.

### Endpoints

| Endpoint | Session needed | Purpose |
| --- | --- | --- |
| `POST /api/auth/login/start` | No | Resolve an email to a passkey challenge, or send a code |
| `POST /api/auth/login/passkey` | No | Verify a WebAuthn assertion and open a session |
| `POST /api/auth/otp/start` | No | Send or resend a sign-in code |
| `POST /api/auth/otp/verify` | No | Exchange a code for a session |
| `POST /api/auth/login` | No | Email and password, retained for staff |
| `POST /api/auth/logout` | No | End the session |
| `GET /api/auth/me` | Yes | The signed-in user |
| `POST /api/auth/passkeys/options` | Yes | Options for enrolling a passkey |
| `POST /api/auth/passkeys` | Yes | Store a verified new passkey |
| `GET /api/auth/passkeys` | Yes | List the member's passkeys |
| `DELETE /api/auth/passkeys/{id}` | Yes | Revoke one |

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

### Emailed codes in development

`MAILERS` uses the console backend, so codes are printed to the terminal
running Uvicorn rather than sent. Look for the message body in that output.

Django 6.1 has no async email API, so sending -- and password hashing, which is
deliberately slow -- runs in a worker thread rather than on the event loop.

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

`status` is the source of truth: Pending, Active, Suspended, Inactive. Only
Active signs in. `is_active` is a denormalised copy of `status == 'active'`,
because Django's auth stack filters on it in SQL and a Python property would
break every queryset. `save()` derives it, and a database check constraint
rejects any write that changes one without the other -- including
`.update()` and raw SQL.

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
| `DJANGO_DEFAULT_FROM_EMAIL` | No | Sender address on sign-in code emails. |
| `DJANGO_CDN_BASE_URL` | With a container | Public prefix the documents are served from. Https outside local development, and its path must match the container. |
| `DJANGO_DOCUMENT_STORAGE_CONTAINER` | No | The blob container the CDN fronts. Blank means uploads go to `MEDIA_ROOT` and are served by runserver. |
| `DJANGO_DOCUMENT_STORAGE_ACCOUNT` | With a container | Storage account name. Not needed if a connection string is set. |
| `DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY` | No | Account key. Leave blank on App Service and use the managed identity. |
| `DJANGO_DOCUMENT_STORAGE_SAS_TOKEN` | No | Used when no account key is set. Needs container write permission, and expires. |
| `DJANGO_DOCUMENT_STORAGE_CONNECTION_STRING` | No | Account and key together. Overrides `DJANGO_DOCUMENT_STORAGE_ACCOUNT`. |
| `DJANGO_DOCUMENT_STORAGE_LOCATION` | No | Blob-name prefix inside the container. Normally blank. |

Frontend variables live in `frontend/.env.local`, documented in
`frontend/.env.example`. `CDN_BASE_URL` is still required there but is no longer
read by anything: Django owns the club document addresses now, because it owns
their versions.

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

## Not yet configured

Production deployment is deliberately out of scope for now. When a target is
chosen, it needs: a process manager fronting Uvicorn (Gunicorn with
`UvicornWorker` on Linux), static file handling (`STATIC_ROOT` plus WhiteNoise
or a CDN), a real database, and the Django deployment checklist
(`manage.py check --deploy`).

Authentication adds two more: a real email provider in `MAILERS` (codes are
printed to the console today) and a shared cache backend, without which the
auth rate limits are per worker rather than per deployment.

The club documents add one: an Azure Blob Storage container behind the CDN, and
the `DJANGO_DOCUMENT_STORAGE_*` variables above. Without it the PDFs are written
to `MEDIA_ROOT` and served by runserver, which is fine locally and is not a
deployment.

The frontend adds two requirements. Serve both halves under one registrable
domain (`app.example.co.za` and `api.example.co.za`) so the `SameSite=Lax`
session cookie still reaches the API; a genuinely cross-site split needs
`SameSite=None` plus HTTPS. And set `DJANGO_API_URL` to the internal address
Next.js can reach and `NEXT_PUBLIC_DJANGO_API_URL` to the public one — the
latter is baked into the client bundle at build time.

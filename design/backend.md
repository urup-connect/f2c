# Backend design

Django 6.1 on Python 3.14, served over ASGI by Uvicorn. It exposes a JSON API built with
django-ninja and the Django admin, and renders no user-facing pages.

## 1. Executive summary

The backend is small and its complexity is concentrated in one place: the member record. Everything
interesting about it follows from two constraints that pull in opposite directions.

The first is POPIA. An identity number is not merely an identifier — it discloses date of birth,
sex and citizenship status to anyone who can read the column — so it must be encrypted at rest, and
a member who asks to be forgotten must actually be forgotten.

The second is that the collective still has to operate. One account per identity document has to be
enforceable, staff have to be able to find an account, and the records a member owns cannot be
destroyed along with their personal data.

Sections 4 and 5 are how those two are reconciled. The rest of the backend is conventional.

The API surface is authentication and a health check, and nothing else. There is no membership, no
payment, no cultivation record. Section 12 sets out what that means.

## 2. Why Django serves no pages

Django renders no HTML for members. It serves `/api/` and `/admin/`.

The alternative was Django templates for some screens and Next.js for others. That was rejected
because it produces two rendering stacks, two styling systems and two implementations of "who is
signed in" — and the third of those is the one that eventually diverges and becomes a security
defect.

What is kept from Django is its session and CSRF machinery, which is mature and which the admin
needs anyway. The frontend never handles a token: Django issues an `HttpOnly` `sessionid` cookie,
and unsafe methods carry a CSRF token the frontend reads from a non-`HttpOnly` cookie.

`runserver` still works but Django 6.1 ships a WSGI-only development server. Anything depending on
async views, async ORM access, streaming responses or long-lived connections must be tested through
Uvicorn — which is everything in `authn/api.py`, since every endpoint there is `async def`.

## 3. One app per feature, grouped by what it serves

The Django side is split by feature, not by layer. There is no `api` app holding every endpoint and
every model; each feature owns its own models, admin, schemas and router.

Since Block 0.5 the apps sit under four packages, and the grouping is the answer to a question the
flat layout could not express: **which of these serve both storefronts, and which are the club's?**

```
app/core/       the platform spine. Knows nothing about what is sold
app/commerce/   what both storefronts sell through
app/club/       the cannabis club
app/market/     the produce market. No apps yet
```

| App | Owns | Depends on |
| --- | --- | --- |
| `core/common` | Field encryption, RSA ID checks. No models, no endpoints | — |
| `core/accounts` | The identity, the permission catalogue over it, and the admin | `common` |
| `core/authn` | Passkeys, emailed codes, sessions, rate limits | `accounts`, `common` |
| `core/storefronts` | The two storefronts, who administers one, and which storefront a request is for | `accounts` |
| `core/documents` | Documents, revisions, and the agreements given — per storefront | `accounts`, `storefronts` |
| `core/payments` | The membership subscription, the Payfast integration, and what a payment does to a membership | `accounts`, `membership` |
| `commerce/producers` | The producer organisation, its appointed people, and which storefronts it sells into | `accounts`, `storefronts` |
| `club/membership` | Club membership, its nickname, and turning a sign-up submission into a member | `accounts`, `documents`, `payments` |
| `club/finished_product` | The catalogue of forms a harvest can take. No endpoints | — |
| `club/strains` | The strain catalogue, the aroma and effect vocabularies, and each producer's listing against a strain. No endpoints | `producers`, `finished_product` |
| `club/plant` | The plant, its batch, its serial counter, the ownership history, and the stock-upload template and reader. No endpoints | `producers`, `strains`, `finished_product` |
| `f2c` | Settings, URLs, and the API root | all of them |

**Every app sets `label` explicitly**, so a table is `accounts_user` rather than
`core_accounts_user`. That is what made the move a package rename and nothing more: no table
changed name, `AUTH_USER_MODEL` is still `accounts.User`, and no migration dependency moved. The one
app that *was* renamed is `cultivators` → `commerce/producers`, and that was the point of it — a
farmer growing carrots is the same record as a cultivator growing cannabis.

The boundary earns its keep by what it forbids. `club/plant` importing from `club/strains` is
ordinary; `commerce/producers` importing from `club/strains` would be the commerce spine learning
about cannabis, and the directory is what makes that visible in a diff.

`plant` is Block 3 and the spine of the product: everything the club sells is a row in its table. The
model layer is built — plant, batch, serial allocation, ownership history, the leaf rating — and so is
both halves of capture. `cultivator-stock-upload.md` opens with "Cultivators can load individual
plants **or** batch upload multiple plants using an excel template" and then gives *one* list of
required fields for both — so there is one list in the code. `upload_plants` reads a workbook and
`capture_plant` takes a mapping; from that point they are the same coercion, the same three
database checks and the same write. A second validator for the single-plant form would eventually
disagree with the first, and the half that disagreed would be whichever was used less.

Four interfaces, none of them an endpoint: `manage.py plant_template` and `manage.py upload_plants`
for a batch, `manage.py add_plant` for one, and the admin's add form for one. The admin form
assembles a row in the reader's own shape and hands it to the same two functions, then maps each
complaint back onto the field it came from — which is what `RowError.key` is for. Block 9 is where a
cultivator gets to do any of this themselves.

The other half of the cultivator story's "SOH imports and exports" is
`manage.py export_stock`, with an admin action beside it for whatever staff have filtered on the
changelist. Its scopes are that story's own two inventory screens — "my inventory for sale" and "my
member-owned inventory" — and the default is the first, because that is what stock on hand means. It
carries the platform-generated columns the template deliberately has none of, and flags the "late
items" the same story asks for: a plant past its estimated harvest date and not harvested.

**An export is not a re-import**, and the asymmetry is deliberate rather than an omission. Every plant
in one already exists, so uploading it back is refused by the duplicate check — the import half is the
template, which is for stock that is new.

The upload is split in two on purpose. `plant/spreadsheet.py` decides whether a *file* is readable and
touches no model; `plant/services.py` decides whether what it read is *true* and issues every query.
That is what lets each date coercion and each refusal be tested against a workbook built in memory,
and each lookup be tested without a workbook. It also puts one rule in exactly one place: **the
cultivator is never read from the file.** `cultivator-stock-upload.md` lists "Cultivator ID" among the
upload fields, and it is deliberately not a column — a column naming the cultivator is one that could
be filled in with somebody else's name, and the upload would load stock into their inventory. Who is
uploading is an argument to the command, and will be the session in Block 9.

The four newest apps are the first to be built with no router at all, which is a deliberate
consequence of the sequencing rather than an oversight: `todo.md` puts the models in Blocks 1 and 3
and every endpoint over them in Block 9, so the Django admin is the whole interface until then. What
they do own is a full admin, which is where `member-roles.md`'s administrator CRUD over strains and
product types, and its "trace serials and batches", actually live today.

The dependency direction is the thing to check when reading them. `finished_product` knows nothing
about strains, listings or plants — the platform defines the catalogue and does not care who narrows
it — and `strains` reaches into it by string reference. That is C18's three levels expressed as an
import direction: platform catalogue, then the cultivator's listing, then the plant.

The routers are mounted on one `NinjaAPI` instance in `f2c/api.py`. That module
belongs to the project rather than to any app, because it is the only one that has to know about all
of them; adding a feature is one `add_router` line. The alternative — a single app owning the whole
API surface — was rejected once `documents` arrived: it had already been built as its own app, and a
second feature filing its endpoints somewhere else would have made "where does this go?" a matter of
which week it was written.

Dependencies run one way and nothing depends back, which is what keeps the split real rather than
cosmetic. `authn` reaches into `accounts` for the member it authenticates; `accounts` does not know
passkeys exist.

The one place that direction is bent is erasure. `User.soft_delete` has to revoke credentials it
does not own, or an erased account keeps a way back in. It reaches them through the reverse
relations `authn` declares — `passkeys`, `email_otps`, `passkey_handle` — rather than importing the
app, so the two never become mutually dependent. Those three names are a contract, and
`accounts/tests/test_models.py` asserts all three tables end up empty.

`payments` is the newest app and the clearest case for the split. It depends on `accounts` alone —
it activates an account and knows nothing about club documents or sign-up — and `membership` depends
on it, calling `open_subscription` inside the transaction that writes the member. The direction is
what stops the money knowing about the form: `payments` has no idea a registration exists, which is
why the same subscription machinery will serve an order or a swap fee without being reopened.

`common` holds only what at least two features need and none should own. Encryption is there
because an identity number will not be the last thing this project encrypts; the ID validators
because the same number is checked at sign-up, in the admin and on the member record.

### There is no `stock` app, and there was one

It was scaffolded on a reasonable reading of the brief — `stock` for what a cultivator has on hand,
`plant` for what a member is holding — and removed, because that distinction does not survive the
schema. It is recorded here because it is the kind of thing that gets re-proposed.

**Every use of "stock" in `twp-tasks/` means a count of plants.** `member-roles.md` gives the
cultivator "upload plant **stocks**" and "manage plant **stocks** — adjust available plants";
`platform.allocate_sharing_member_stock` allocates *flowering plants*; `stock-holding-limit.md` is
about "owning more than 4 flowering plants". There is no fungible inventory anywhere in this
platform. Every unit is a serialised plant with a planting date, a harvest date and one owner.

**The serial is the decisive argument.** `plant-id-numbers.md` says the platform-allocated serial
exists "to track ownership changes", so a plant on a cultivator's hands and a plant in a member's
holding have to be *the same row with a different owner*. Two tables means a sale moves a row between
them, which breaks the continuity that is the serial's whole purpose — and breaks the certificate of
ownership, which needs the planting date, the harvest date, the strain and the cultivator pseudonym on
one row that outlives every transfer.

So stock is a queryset over `Plant`, not a table: stock on hand is the plants a cultivator holds
unsold, "adjust available plants" is a status change or a row added and removed, and the four-plant
limit is a count. A model holding quantities would be a denormalised aggregate over another table —
and section 8.2 is the record of what this project requires of a denormalised column: a specific
justification, and **a check constraint tying it to its source**. A cross-table count is the one kind
SQL cannot constrain at all, so it is the one kind this codebase has no way to make safe.

Two smaller things point the same way. `features/landing.md` puts `stock` in `RETAIL_VOICE`, the
banned-word list for member-facing copy — it is not the club's own vocabulary. And a `stock` app would
need `plant` while `plant` would need to know its own availability, which is the one rule this app
layout does not bend.

The apps that *do* belong in that space are later blocks with models of their own and a one-way
dependency on `plant`: orders and cart in Block 5, fulfilment in Block 6, the swap zone in Block 10.

## 4. The member record

`accounts.User` is the project's `AUTH_USER_MODEL`. Members and staff are one model, told apart by
`is_staff`.

The alternative — Django's default user for admin plus a separate member model — would mean a second
authentication stack and two identities for anyone who is both a member and staff. In a collective,
that is most of the people who administer it.

The primary key is a **UUIDv7**, not v4. It is time-ordered, so inserts land at the end of the
primary-key index rather than scattering random writes across it. Free on SQLite, and it matters on
MySQL, where InnoDB clusters the table on its primary key and a random one splits pages on every
insert. Section 8.3 has the cost that comes with it.

The sign-in identifier is a unique, **lower-cased whole** email address — local part included.
Case-sensitive local parts are legal and universally ignored by real mail providers. Honouring them
would let someone register `Member@example.com` alongside `member@example.com` and receive the other
member's sign-in codes.

### 3.1 Status is the source of truth, not a boolean

`status` is one of Pending, Pending payment, Active, Suspended, Inactive, Sharing. Exactly one
value grants access.

Keeping six states rather than a boolean matters because "not yet approved", "not yet paid", "in
trouble", "erased on request" and "holds stock and never signs in" are different situations with
different operational answers, and a single `is_active` flag cannot tell them apart. Sharing is the
one value that is not a stage in a lifecycle: it is where a sharing member sits permanently, and
`design/features/roles-and-permissions.md` section 3.2 says why reusing Pending was rejected.

But `is_active` still exists, as a denormalised copy of `status == 'active'`. That is not
redundancy by accident:

> Django's auth stack does not merely read `is_active`, it **filters on it in SQL** — admin login,
> `ModelBackend` and password reset all do. A Python property would satisfy the reads and silently
> break every queryset.

Three mechanisms keep the two in step:

1. `save()` derives `is_active` from `status` on every write, including partial saves.
2. `save()` adds `is_active` to `update_fields` when a caller passes one, so a partial save cannot
   skip it.
3. A **database check constraint** rejects any write where the two disagree.

The constraint is the backstop for writes that bypass the model entirely — a queryset `.update()`, a
data migration, raw SQL. Without it, such a write silently locks a member out or lets a suspended
one back in. With it, the write fails loudly.

### 3.2 The identity number is encrypted, and still searchable

`user.id_number` is a property over two columns.

| Column | Contents | Purpose |
| --- | --- | --- |
| `id_number_encrypted` | AES-256-GCM ciphertext, fresh nonce per row | The number itself |
| `id_number_hash` | Keyed HMAC-SHA256 of the normalised value | Equality lookup and uniqueness |

A fresh nonce per row means two members with the same number produce different ciphertext, so the
column leaks nothing to anyone reading a database dump — not even which two rows match. That is the
point, and it is also the problem: non-deterministic ciphertext cannot be indexed or compared, which
would leave no way to enforce one account per identity document.

The blind index fills that gap. It supports equality and nothing else — no prefix search, no
browsing — and it carries a `unique` constraint. It is **keyed** rather than a plain hash because the
space of valid RSA ID numbers is small enough to enumerate against an unkeyed digest.

The ciphertext is bound to the field it belongs in. `context` (`'accounts.User.id_number'`) is
authenticated but not encrypted, and GCM verifies it on the way out, so ciphertext copied into a
different column fails to decrypt rather than silently decoding.

Decryption failure raises `crypto.DecryptionError` and is never swallowed. Returning an empty string
would quietly present unrecoverable data as absent — the worst available outcome, because nobody
would know to look.

### 3.3 Two secrets, both separate from `SECRET_KEY`

| Setting | Protects | If lost |
| --- | --- | --- |
| `DJANGO_FIELD_ENCRYPTION_KEY` | The identity numbers themselves | **Permanently unrecoverable.** No recovery path. |
| `DJANGO_BLIND_INDEX_PEPPER` | The searchable digests of ID numbers and addresses | Uniqueness checks and returning-member lookups need a rebuild |

Both are deliberately separate from `DJANGO_SECRET_KEY`, which is rotated on a different schedule
and after any suspected leak. Rotating the secret key must not render every stored identity number
unreadable.

Django refuses to start without all three. That is a design choice: a backend that boots with
encryption misconfigured writes plaintext or crashes at the first identity capture, and both are
worse than not booting.

**`DJANGO_FIELD_ENCRYPTION_KEY` must be backed up somewhere other than the database.**

### 3.4 RSA identity numbers

A 13-digit number is validated as `YYMMDD SSSS C A Z` — birth date, sequence, citizenship digit, a
legacy digit, Luhn check digit. Structure, embedded date, citizenship digit and checksum are all
checked.

A passing number means *not a typo*, not *verified*. Confirming a number was ever issued needs Home
Affairs. `date_of_birth_verified_at` records when a human checked it against a document; null means
unverified, whatever the member typed.

`capture_sa_id_number()` reads `date_of_birth` off the document itself rather than having it typed a
second time, so the two cannot disagree.

Members without an RSA ID are expected. Nothing in the model requires these validators, and a
foreign document is stored as given — a passport has no checksum to test, so there is nothing to
check.

### 3.5 Roles are a column, and permissions are a dictionary

`role` is one of Admin, Cultivator, Member or Sharing member. Exactly one per account, defaulting to
Member, held to the four known values by a check constraint.

A Django group was the obvious alternative and was rejected as the source of truth: a group is
runtime data, an account can belong to none or to all four, and no constraint can express "exactly
one". The groups exist anyway, mirrored from the column by `save()`, so that the model permissions
the strain and plant apps will bring can be attached to a role in one place — but nothing reads them
to decide anything today.

What each role may do is a dictionary in `accounts/roles.py`, not `auth.Permission` rows. Almost
every action is against a model that does not exist yet, and a permission row needs a content type,
which needs a model. `accounts/backends.py` registers a second authentication backend that resolves
the dictionary, so `user.has_perm('platform.purchase_plants')` works today and one call still covers
both kinds of permission. It authenticates nobody: `ModelBackend` stays the only backend that can
open a session.

Three couplings matter and each is deliberate. **Role is not status** — an inactive account holds
nothing whatever its role, which is what makes suspension and erasure safe without either knowing
about permissions. **Role is not `is_staff`** — the two are independent by decision, and the cost of
that (privilege granted in two places) is on the register. **The resolution issues no query**,
because `UserOut` serialises the permission list inside async views.

### 3.6 The sharing member

A **sharing member** is an identity a cultivator registers so that it can hold four flowering plants
and put them in the swap zone — a new club's zone is otherwise empty. They give a name, an identity
number and a nickname, hold no email address, and never sign in.

They are a `User` row all the same, which is the decision worth defending. A separate model would
have meant a second nickname namespace (two people wearing one name in the swap zone is
impersonation, not a collision), a second encrypted identity column, a second erasure route, and two
kinds of owner for every plant, swap and certificate. As a row here they also inherit the club's "one
account per identity document" rule.

Three mechanisms carry the weight:

- `UserStatus.SHARING`, plus a check constraint (`sharing_member_never_signs_in`) refusing the role in
  the Active status. Having no email address already makes them unauthenticatable, but that is a
  property of the *data* — the constraint is what stops somebody typing an address into the admin from
  silently turning stock into an account.
- A **consent attestation**: a cultivator captures a third party's identity number, so POPIA needs a
  lawful basis the person never gave on a form. `sharing_consent_attested_by`, `_at` and `_version`
  record who swore what and when. It is called an attestation rather than a consent because it is
  weaker evidence than a member's own tick, and naming it accurately is what stops the two being
  confused later.
- `sharing_member_is_complete`, a check constraint requiring the registering cultivator, the
  attestation and a nickname — with erased rows exempt, because `soft_delete` blanks the nickname and
  the POPIA erasure route must never be the thing the database refuses.

`accounts/services.py` is the write. It authorises on the permission rather than the role, refuses a
submission with no attestation before validating any field, applies the same eighteen-year rule as
sign-up, and refuses a duplicate identity number in words that name no record — a leak it reduces
rather than closes, and one the design document records as a risk.

`registered_by` is `PROTECT`, so a cultivator who has registered sharing members cannot be
hard-deleted. Deleting a grower must not delete people; the routine answer, erasure, keeps the row.

`design/features/roles-and-permissions.md` is the full record: the catalogue, the rejected
alternatives, and what the roles govern that is not built.

## 5. Erasure

`user.soft_delete()` is the POPIA erasure route, exposed in the admin as **Erase selected accounts**
and restricted to superusers.

It clears first name, last name, nickname, email address and identity number; sets status to
Inactive; stamps `deleted_at`; makes the password unusable; and revokes every passkey, every
outstanding code, the passkey user handle and every live session.

Two details are the whole design:

**The row survives.** Other records point at it — who grew what, who paid what — and cascading those
away would destroy the collective's own operating history rather than the member's personal data.

**`email_hash` deliberately survives with it.** A keyed digest of the address, not cleared, which
answers `User.objects.has_been_seen(address)` without the erased record keeping the address itself.
The collective needs to recognise a returning member; POPIA's minimality principle prefers a digest
to an address. The digest is not unique, so an erased member is free to register again as a new
account.

An erased account cannot be reactivated. `activate()` raises rather than resurrecting a record whose
personal data is gone.

`user.deactivate()` is the reversible half: it blocks sign-in and cuts live sessions but erases
nothing.

`role` deliberately survives erasure too, along with the group mirroring it. A role is a fact about
the collective's own structure rather than about the person, and it confers nothing on an account
erasure has left Inactive.

`flush_sessions()` is what makes either of those real. Changing `status` does not touch the session
store, so without it an already signed-in browser keeps working until its cookie expires. Sessions
carry no user column, so they have to be decoded to be matched — which is linear in live sessions
and is the one part of erasure that will need attention at scale.

## 6. The API surface

Mounted at `/api/` by the project URLconf. Endpoints require a valid session by default; the handful
that cannot opt out with `auth=None`.

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/health` | No | Liveness probe |
| `GET /api/auth/csrf` | No | Set the `csrftoken` cookie |
| `POST /api/auth/login/start` | No | Resolve an address to a passkey challenge, or send a code |
| `POST /api/auth/login/passkey` | No | Verify a WebAuthn assertion, open a session |
| `POST /api/auth/otp/start` | No | Send or resend a sign-in code |
| `POST /api/auth/otp/verify` | No | Exchange a code for a session |
| `POST /api/auth/logout` | No | End the session |
| `GET /api/auth/me` | Yes | The signed-in member |
| `POST /api/auth/passkeys/options` | Yes | Options for enrolling a passkey |
| `POST /api/auth/passkeys` | Yes | Store a verified new passkey |
| `GET /api/auth/passkeys` | Yes | List the member's passkeys |
| `DELETE /api/auth/passkeys/{id}` | Yes | Revoke one |
| `GET /api/documents/current` | No | Every club document at the revision in force, or 503 |
| `GET /api/payments/checkout/{token}` | No | The signed Payfast field set for a subscription awaiting payment |
| `POST /api/payments/payfast/notify` | No | Payfast's server-to-server notification. The only thing that activates a membership |
| `GET /api/documents/outstanding` | Yes | Revisions this member has yet to agree to |
| `POST /api/documents/accept` | Yes | Record agreement to the revisions the member was shown |

`/api/documents/current` is unauthenticated because sign-up reads it before an account exists. It
answers 503 rather than a short list when a required document has no published revision: a caller
cannot tell an incomplete list from a complete one, so the endpoint has to.

`/api/docs` publishes the OpenAPI schema when `DEBUG` is on and 404s otherwise.

Each feature declares its own schemas — `accounts.schemas`, `authn.schemas`, `documents.schemas` —
written explicitly rather than generated from models, so a model change cannot silently alter the
payload the frontend depends on. `accounts.schemas.UserOut` omits `id_number` entirely: it is
encrypted at rest and has no business crossing the wire to a browser. It carries `role` and the
`permissions` the role holds, sent together so the frontend never maps one to the other — a second
copy of the catalogue in a browser bundle would drift from the one the API enforces. Both are for
rendering navigation; every endpoint checks the permission itself. `common.schemas` holds only
the acknowledgement envelope every feature returns.

WebAuthn options and credentials cross as opaque dicts. They are defined by a W3C serialisation that
the browser and py_webauthn both already speak, and re-declaring it would only add a second place
for it to drift.

### CSRF on the pre-session endpoints

Setting `auth=None` also skips django-ninja's built-in CSRF check, so those endpoints call
`check_csrf` themselves. Sign-in is a state-changing request and must not be forgeable.

One implementation detail matters for anyone writing tests against these: **django-ninja parses and
validates the request body before it calls the view**, and the CSRF check lives inside the view. A
malformed body is therefore refused as `422` and never reaches the CSRF check at all.

## 7. Sessions, CSRF and CORS

| Setting | Value | Why |
| --- | --- | --- |
| `SESSION_COOKIE_SAMESITE` | `Lax` | Enough while both halves share a parent domain |
| `CSRF_COOKIE_HTTPONLY` | `False` | The frontend reads this token to echo it in `X-CSRFToken` |
| `SESSION_COOKIE_SECURE` | `not DEBUG` | Cookies never travel in cleartext outside local dev |
| `CORS_ALLOW_CREDENTIALS` | `True` | Required, or the browser sends no cookies at all |

`CorsMiddleware` sits above `CommonMiddleware` so that preflight responses are not redirected.

A genuinely cross-site deployment — frontend and API on different registrable domains — needs
`SameSite=None` plus HTTPS. Under one registrable domain (`app.example.co.za` and
`api.example.co.za`), `Lax` is correct and simpler.

## 8. The database

SQLite in development. **QA and production are MySQL 8.4.** That is a decision with consequences,
and this section exists because most of them are silent.

### 8.0 How the connection is configured

`f2c/database.py` reads `DATABASES` from the environment, as a pure function of a
mapping — the same shape as the two storage readers and `payfast_config`, and for the same reason:
every branch and every refusal is testable with no database server involved.

| Variable | Effect |
| --- | --- |
| `DJANGO_DB_HOST` | **The switch.** Blank means SQLite at `db.sqlite3`; set means MySQL |
| `DJANGO_DB_NAME`, `DJANGO_DB_USER` | Required once a host is named. Missing either is a refusal, not a default |
| `DJANGO_DB_PASSWORD` | Optional. A passwordless local MySQL user is a legitimate development setup |
| `DJANGO_DB_PORT` | Defaults to 3306 |

`DATABASES` used to be four hardcoded lines pointing at `db.sqlite3`, which made the deployed backend
unconfigurable and made everything below untestable — there was no way to point the suite at the
database QA and production actually run.

Three details are decisions rather than plumbing:

**A half-configured MySQL is an error.** `DJANGO_DB_NAME` set with no `DJANGO_DB_HOST` refuses at
startup rather than falling back. The failure it prevents is the quiet one: a typo in a variable name
or a rename in a deployment template, and the application comes up on a local SQLite file with every
MySQL variable set and ignored. Invisible on a developer's machine; in production it is member data
written somewhere nobody backs up.

**`sql_mode` is set explicitly and in full.** Section 8.4 needs `STRICT_TRANS_TABLES`. The trap is
that `init_command` *replaces* the server's `sql_mode` rather than adding to it, so naming only that
one would quietly discard the zero-date and division-by-zero protections MySQL 8 has on by default.
The whole set is named.

**The test database is given an explicit charset and collation.** `utf8mb4` and
`utf8mb4_0900_ai_ci`, so a CI run reproduces production's comparison semantics — which are case- *and*
accent-insensitive, and are the reason strain uniqueness rides on a slug (section 8.3).

**The driver installs everywhere, and its wheels are Windows-only.** `mysqlclient` is in
`[project.dependencies]`, so no deployment is one forgotten package away from not booting — a
developer on SQLite installs it and never loads it. The cost is that it is a C extension with no
published Linux wheel: on Linux, pip builds it from the source tarball and needs `pkg-config`,
`default-libmysqlclient-dev` and a compiler. CI installs those before pip runs, and a Linux
deployment has to as well. The failure without them is `Can not find valid pkg-config name`, which
reads like a missing package rather than a missing toolchain.

### 8.1 What MySQL will not do, and does not say

Django asks the backend whether it supports a feature and, for indexes and constraints, **omits what
it cannot build rather than refusing to migrate.** No error, no warning, no row in the migration
output. The constraint is simply absent from the deployed schema while the model file, the migration
and the test suite all still describe it.

Three things fall into that gap, and 8.4 settles two of them:

| Feature | MySQL 8.4 | Consequence if unsupported |
| --- | --- | --- |
| Partial index — `UniqueConstraint(condition=...)` | **No. No MySQL version builds one** | Silently dropped |
| Expression index — `UniqueConstraint(Lower('x'))` | Yes, since 8.0.13. **Never on MariaDB** | Silently dropped |
| `CHECK` constraint | Yes, since 8.0.16 | Silently unenforced |

So the version in use is fine for two of the three rows, and **the partial-index row is permanent.**
It is not a version to wait out: MySQL has no filtered-index feature and no plans for one, so
`condition=` on a `UniqueConstraint` is a shape this codebase can never use. That is the rule section
8.2 was written about and section 8.3 is written around.

The floor is 8.0.16 rather than 8.4 — that is where `CHECK` starts being enforced, and below it every
check constraint here is decoration, including the two that section 3.1 calls the backstop for writes
that bypass the model. MariaDB is not a substitute at any version, because of the expression-index
row. **Both of those are now asserted at `migrate` rather than trusted** — see 8.5.

### 8.2 Three constraints that used to disappear on MySQL — closed

These were in the repository until `accounts/0007` and `payments/0002`, and each was the only thing
enforcing a rule stated nowhere else:

| Constraint | What was lost | Now |
| --- | --- | --- |
| `user_nickname_unique_ci` | Two accounts could wear one nickname. Both an expression *and* a condition, so it failed the table above twice | `user_nickname_key_unique` over `User.nickname_key` |
| `user_mobile_unique` | Two accounts could hold one mobile number | `user_mobile_key_unique` over `User.mobile_key` |
| `one_live_subscription_per_member` | A member could hold two live subscriptions, and Payfast would bill both | Same name, over `Subscription.live_for_user` |

The nickname was the worst of the three, and section 3.6 says why without knowing it: a nickname is
the *only* identifier the API exposes for another member, so two accounts sharing one is
impersonation rather than a collision. The catalogue depends on that guarantee too — a cultivator's
public name is their nickname, and a fulfilment document carries nothing else.

**The shape of the fix.** Each rule moved onto a derived column that is **null** wherever the old
condition excluded a row, and the unique index over it is unconditional. Nulls are distinct under a
unique index on both SQLite and MySQL, so "any number of accounts may hold no nickname, and no two
may hold the same one" is expressed exactly, on every backend, with no feature the database lacks.

Three details are what make it safe rather than merely portable, and all three are worth knowing
before the pattern is used a fourth time:

**A derived column can go stale, and a stale uniqueness key is worse than an absent one** — a member
renamed by hand still occupies their old name and can be handed somebody else's, and every read goes
through the key, so nothing would show it. So each key is tied to its source by a **check
constraint**, exactly as `is_active` is tied to `status` in section 3.1. `save()` keeps them true;
the constraint catches the write that went around `save()`.

**`save()` now trims the nickname.** That is not tidying: it makes `nickname_key` exactly
`LOWER(nickname)`, which is what lets the check constraint compare the two in SQL. Without it a
stored ` Bob ` would carry a key of `bob` and the constraint would refuse the model's own write.

**A `CHECK` passes when its condition is *unknown*, and a SQL comparison against null is unknown.**
The first version of `live_for_user_matches_status` compared a nullable column with `=` and was
therefore satisfied by exactly the row it existed to refuse — the raw update reviving a cancelled
subscription went straight through. Every one of these constraints now carries an explicit
`__isnull=False` beside its equality. `payments/tests/test_models.py` and
`accounts/tests/test_uniqueness_keys.py` both pin it.

The backfills refuse rather than repair, and **count without naming**, which is the rule
`accounts/0003_mobile_unique` established: a nickname and a mobile number are personal information,
and a migration that printed one would write it into every deploy log and CI transcript. They also
run *before* the first `ALTER`, because MySQL has no transactional DDL and a migration that dies
halfway leaves a partly changed schema.

### 8.3 What the catalogue apps do about it

`strains`, `finished_product` and `cultivators` were written after this decision and are portable by
construction. Four rules, worth stating because they read as odd choices otherwise:

**Every unique constraint is unconditional.** Where a rule applies to only some rows — a listed
offer needs a short description, but a draft may be incomplete — it is a `CheckConstraint` instead of
a partial index. One consequence is visible in the schema: a withdrawn listing still occupies its
cultivator-and-strain pair, because scoping that index to live rows would need the feature MySQL
lacks. A cultivator returning to a strain reinstates the withdrawn row.

**Case-insensitive name uniqueness rides on a derived `slug`.** Not on `Lower(name)`, which is the
obvious spelling and is an expression index. It also fixes a real dev-versus-production divergence:
MySQL's default `utf8mb4_0900_ai_ci` collation is case- *and* accent-insensitive, so a plain unique
index on `name` behaves differently there than on the SQLite the suite runs against. `slugify` folds
identically on both.

**The JSON columns are display-only.** MySQL cannot index a JSON column without a generated column
beside it, so nothing filters on a terpene profile. Anything the Block 5 browse filters have to
search has to be a column or a lookup table — which is one of the reasons aroma and effect are
lookup tables rather than choice lists.

**Primary keys are UUIDv7**, per `plan.md` section 3. MySQL has no native UUID type, so these are
`char(32)` and InnoDB copies the primary key into every secondary index. Time-ordering is what makes
that acceptable: inserts land at the end of the clustered index rather than splitting pages across
it. The cost is real and is accepted on tables holding hundreds of rows.

### 8.4 Operational notes

| | |
| --- | --- |
| `sql_mode` | Must include `STRICT_TRANS_TABLES`, or an over-long decimal is truncated instead of refused |
| Charset | `utf8mb4` at database, table and connection level. Anything less cannot store an emoji in a member's description, and will fail mid-insert rather than at validation |
| DDL | Not transactional. A migration that fails halfway leaves the schema partly changed, so migrations want a backup behind them rather than a rollback |
| Index key length | 3072 bytes on InnoDB with the default row format, which is 768 `utf8mb4` characters. Every unique column in this project is well inside it |

### 8.5 The guards, because none of this can be trusted to a convention

The database version is a **correctness dependency of this codebase**, not an operational detail, and
an undeclared dependency is one that is eventually not met. `common/checks.py` declares it. Both
guards are `Tags.database` checks, which Django runs when they are asked for — which `migrate` does,
and which is exactly the moment a constraint would be silently skipped. `manage.py check --database
default` runs them on demand.

**The version guard** refuses MySQL below 8.0.16, where `CHECK` is parsed and discarded, and refuses
MariaDB outright. Its refusals name what would break rather than only saying no. An unreachable
database is not an error here — Django has its own check for that.

**The constraint-shape guard is the more durable of the two**, because it reads the code rather than
the version. It walks every model's constraints and reports any `UniqueConstraint` this backend will
omit rather than build. So someone adding a `UniqueConstraint(condition=...)` in six months — the
natural, correct-looking spelling of a rule this project has needed three times already — is told at
`migrate` that it will not exist, instead of finding out when two members share a nickname. It
deliberately says nothing about `CheckConstraint`, which also carries a `condition` and is a
different thing entirely; conflating the two made the first version report every check constraint in
the project, which is how a guard stops being read.

### 8.6 The suite runs twice, on two databases

The tests run on SQLite locally, which supports partial indexes, expression indexes and check
constraints. So **a constraint test passes there whether or not the deployed database enforces the
rule** — the exact failure mode section 11 says the suite is written to catch, and the one instance of
it the suite cannot catch by itself.

Three things close it, in increasing order of how much they prove.

**The constraint tests write through a raw queryset `.update()`**, deliberately, because that is the
write a check constraint exists to refuse. A rule enforced only in `save()` is not a rule.

**The shapes are asserted against fake unsupporting backends.** `common/tests/test_checks.py` and the
portability tests in `accounts/tests/test_uniqueness_keys.py` run the guards against connections that
claim to support neither partial nor expression indexes, and assert that no constraint in the project
is reported. That is the one thing SQLite cannot hide, and it runs on a developer's machine with no
MySQL installed.

**And `.github/workflows/ci.yml` runs the whole suite against MySQL 8.4.** That is the only place the
constraints are proven rather than argued about. The `api` job also:

- runs `makemigrations --check`, so a model changed without a migration fails there rather than on a
  deploy;
- runs `migrate` against an *empty* MySQL, which is what actually exercises the hand-written
  backfills in `accounts/0007` and `payments/0002` — those refuse when the data already holds
  duplicates, and a failure path nothing ever executes is a failure path that is probably wrong;
- asserts `connection.vendor == 'mysql'` before doing any of it. Without that the job's own quiet
  failure mode is a fallback to SQLite, where everything passes and proves nothing;
- runs the suite with `--shuffle`, because several tests here mutate shared state to reach the
  situation they are testing — `_DroppedConstraint` takes a constraint off the table and puts it
  back — and a suite that only ever runs in one order is one where a missing restore looks like a
  pass.

`migrate` runs Django's `database`-tagged checks, so section 8.5's guards are exercised against a real
MySQL there as a side effect, including the one that would refuse the server if it were too old.

CI installs the MySQL client headers before pip, because `mysqlclient` has no Linux wheel — section
8.0. It installs with pip and `requirements.txt` rather than Poetry; `poetry.lock` is committed and
pins hashes where `requirements.txt` gives ranges, so switching is a reasonable upgrade if a
dependency release ever breaks a build nobody touched.

The `frontend` job is `npm ci`, lint, `tsc --noEmit`, vitest, `next build`, in that order — cheapest
and most specific failure first, so a red build says what is wrong rather than only that something is.

## 9. Rate limiting

Per-IP limits on the unauthenticated endpoints, each with its own scope so that a burst of failed
code entries cannot exhaust the budget for sending new ones.

| Scope | Rate | Bounds |
| --- | --- | --- |
| `otp_start` | 5/min | Outbound email. Without it the endpoint is a mailbomb relay. |
| `otp_verify` | 10/min | Guessing against a code |
| `auth_start` | 20/min | Address resolution |
| `passkey_verify` | 20/min | Assertion presentation |

These are a blunt instrument on their own — they key on IP, which a determined attacker rotates. The
per-code attempt counter on `EmailOtp` is what actually bounds guessing against one account.

**In production the cache must be shared** (Redis or Memcached). The default per-process
`LocMemCache` would let each Uvicorn worker count separately, so the effective limit becomes the
configured rate multiplied by the worker count.

Rates are read from `NINJA_DEFAULT_THROTTLE_RATES` when the throttle object is constructed, which
happens at import time. `override_settings` cannot reach them.

## 10. Admin

The authentication tables are read-only by design. Staff need to see which passkeys an account holds
so they can revoke one a member has lost, and to confirm a code was issued when someone says it
never arrived — but nothing there should be editable by hand, and the code hashes are never
displayed at all.

The user model is editable with four restrictions:

**`is_active` is not a form field.** It is derived from `status`, and a form field would let it
drift.

**Group membership is not a form field either.** It mirrors `role`, so the same argument applies —
and there is a mechanical reason too: the admin's `save_m2m()` runs after the model save, so an
editable groups widget would overwrite the mirror with whatever was rendered before the role
changed. `role` itself *is* editable, and the admin is the only place a cultivator or an
administrator is appointed. What the chosen role permits is displayed beside it, read from
`accounts/roles.py` so the admin cannot describe authority the application does not grant. There are
deliberately no bulk role actions: activate, suspend and erase are batch operations, and handing out
authority over other members' records is not.

**The Sharing member panel is editable, and points at the service.** It holds `registered_by` and
the attestation columns. Until there is an endpoint the admin is the only interface staff have, so a
read-only panel would make sharing members uncreatable — but
`accounts.services.register_sharing_member` is the route that validates the identity number, the age
rule and the nickname, and the panel says so. The database refuses an incomplete sharing member
either way.

**The identity number is write-only.** Staff need to *set* it and to confirm *which* one is on file,
not to read it back. Rendering a member's identity number into an admin page puts it in the browser
cache, the proxy logs and anyone's shoulder view for no operational gain. The list shows the last
four digits behind asterisks; a row that will not decrypt shows `UNREADABLE`, surfaced rather than
hidden, because it is a key or integrity problem someone has to look at.

**There is exactly one exception, and it pays for itself with a row.**
`POST /api/members/{id}/identity-number` — the administrator's register, not this admin — returns
the whole number, and writes an `accounts.IdentityNumberDisclosure` naming the member, the reader,
the time and a stated reason *before* it decrypts anything. The write and the decrypt are one
transaction, so a read that happened is a read that is recorded, and a column that will not decrypt
rolls the row back rather than leaving evidence of something that did not occur. The reason is
required and has a minimum length: a disclosure nobody can review afterwards is worth no more than
the masked default, which is free. The ledger is not editable and has no delete, for the reason the
consent ledger below is not either — a row staff can type into is not evidence of anything. It is a
`POST` rather than a `GET` because a `GET` is cacheable, prefetchable and logged by every proxy in
between, and because a `GET` has no body to carry the reason.

**Erasure is an explicit action, not the delete button.** Hard delete is superusers only and
cascades into everything referencing the member. The routine answer to "please delete my account" is
the Erase action.

Search is extended to cover the encrypted column: a term of six or more digits is looked up through
the blind index, which is exact-match only and so cannot be used to browse.

### Club documents

The **Club documents** group is where a document revision is uploaded and published, and it is the
only place either happens. Three rules shape it:

**Publishing is an action, not a save.** It is irreversible, and a save button that does something
irreversible as a side effect will eventually be pressed by accident.

**A published revision goes read-only and loses its delete button.** Staff who need to change a
document publish a new revision; that is the mechanism, not an inconvenience around it. Only
`change_note` and `requires_reacceptance` stay editable. `DocumentVersion.save` refuses the change
too, so a queryset write fails the same way — and `DocumentConsent.version` is `PROTECT`, which is
the backstop a bulk delete cannot get past.

**The agreement ledger is read-only throughout.** A consent row is evidence that a member ticked a
box, and a row staff can type into is not evidence of anything. It is searchable by member and by
document, and it flags a revision whose file or wording no longer hashes to what was agreed to —
impossible while the immutability guard holds, which is exactly why it is surfaced.

## 11. Testing

| | |
| --- | --- |
| Runner | Django test runner |
| Layout | A `tests/` package per app, one module per layer |
| Tests | 1191 |
| Command | `.venv\Scripts\python.exe manage.py test` |
| Backend | SQLite locally; **MySQL 8.4 in CI**, which is where the constraints are proven — section 8.6 |

| Module | Covers |
| --- | --- |
| `common/tests/test_crypto.py` | Encryption round trip, nonce freshness, context binding, blind index |
| `common/tests/test_validators.py` | Check digit, embedded date, length |
| `accounts/tests/test_models.py` | Status/`is_active` coupling, the encrypted ID number, erasure, display names |
| `accounts/tests/test_admin_forms.py` | Setting, replacing and clearing an encrypted field staff cannot read |
| `accounts/tests/test_roles.py` | The catalogue's own shape, the check constraint, `has_perm` through both backends, the group mirror |
| `accounts/tests/test_sharing_members.py` | Registering one, the attestation without which nothing is written, the constraints that stop them signing in, the vague refusal, erasure |
| `membership/tests/test_services.py` | The registration write: duplicates, the age rule, the role and status it lands on |
| `membership/tests/test_api.py` | The endpoints sign-up posts to, and what they refuse |
| `payments/tests/test_gateway.py` | The Payfast protocol: the signature, its two orderings, the PHP-compatible encoding, every configuration refusal |
| `payments/tests/test_services.py` | What a payment does to a membership: activation, idempotency, renewals, cancellation, lapsing |
| `payments/tests/test_api.py` | The two endpoints, and the status codes Payfast decides redelivery from |
| `payments/tests/test_models.py` | The partial unique index on a live subscription, the paid-up check constraint, both against raw updates |
| `payments/tests/test_commands.py` | Lapsing and its dry run; the development notification command, and that it refuses to run in production |
| `payments/tests/test_admin.py` | That nothing in the payments admin is editable, asserted through a real POST |
| `authn/tests/test_api.py` | Every endpoint: enumeration resistance, CSRF, passkey and code paths |
| `authn/tests/test_otp.py` | Code generation, hashing at rest, expiry, attempt burn, superseding |
| `authn/tests/test_webauthn.py` | Challenge expiry, single use, ceremony key separation, option contents |
| `authn/tests/test_throttles.py` | Each limit as a client meets it, and that the scopes count separately |
| `f2c/tests/test_admin_branding.py` | The brand skin over the admin: palette drift, template overrides, assets |
| `documents/tests/test_models.py` | File digests, immutability after publish, delete refusals |
| `documents/tests/test_services.py` | Failing closed on a missing revision, re-acceptance, stale versions |
| `documents/tests/test_api.py` | The payload contract, the 503, idempotent agreement |
| `documents/tests/test_admin.py` | What the admin refuses once a revision is published |
| `documents/tests/test_command.py` | Upload, digest and publish from the command line |
| `documents/tests/test_storage.py` | Reading Azure configuration, and the refusals that stop a broken deploy |
| `finished_product/tests/test_models.py` | The zero-cost default, `requires_payment` tracking the price, the non-negative constraint against a raw update, retirement without deletion |
| `strains/tests/test_models.py` | The derived slug as the portable uniqueness key, exclusivity and the fact that nothing in SQL enforces it, the listing constraints against raw updates, C18 through both routes that check it |
| `strains/tests/test_admin.py` | The listing form, which is the only thing enforcing C18 on the save that creates a listing; and that the cultivator pickers exclude members, administrators and erased growers |
| `cultivators/tests/test_models.py` | That the pseudonym is the account's own display name and not a second namespace; publication defaults |
| `plant/tests/test_leaf_rating.py` | The brief's five worked examples, the undocumented midpoint, and that the result is always a step of 0.5 |
| `plant/tests/test_models.py` | Serial allocation and the refusal to restart a sequence; the constraints against raw updates; the ownership history and the one gap in it; the four-plant count that excludes a harvested plant |
| `plant/tests/test_spreadsheet.py` | The template round-tripping through its own reader; the ambiguous date that is refused rather than guessed; the price refused rather than rounded; duplicates inside one file; that there is no cultivator column and none for anything the platform generates |
| `plant/tests/test_upload.py` | That one bad row stops the file and consumes no serial; that another cultivator's listing is invisible; the C18 column confirming and never overriding; batches shared across two uploads; every refusal the commands make |
| `plant/tests/test_capture.py` | That a single capture is refused by the same rules as a workbook row and shares its serial counter and plant-ID namespace; that errors arrive keyed by field; and that the admin allocates a serial on add |
| `plant/tests/test_export.py` | That stock on hand means unsold; that a withdrawn plant is in no scope and another cultivator's stock in none of them; the overdue flag; that every row shares one "today"; and that the owner column is a nickname, absent when nothing is owned |

The suite is written around a specific idea: **test what is invisible when it breaks.** An encrypted
column that stops round-tripping loses data with no error. A denormalised `is_active` that drifts
locks members out. An endpoint that starts distinguishing a real address from an unknown one still
returns a valid response for both, and has quietly become a membership lookup for anyone with a
list of email addresses. None of those produce a stack trace.

So the assertions are frequently about what did *not* happen — no email sent, no code row written,
no difference between two responses — and several tests compare two responses to each other rather
than to a fixed expectation, because *indistinguishable* is the actual requirement.

Signature mathematics is mocked. What a real authenticator returns is py_webauthn's responsibility
and is exercised against real hardware; what is tested here is which credential this application
will accept an assertion for, and what it writes when it does.

### A defect this suite found

The passkey sign-in path returned **500 for every member who had enrolled a passkey**.
`login/start` wrote `user.pk` — a `UUID` — into the session, and the session is serialised to JSON,
which has no UUID type and raises rather than coercing. The whole passkey flow was dead.

It had a second half. `login/passkey` compared `credential.user_id` (a `UUID`) against the stored
value, and a `UUID` never equals its own string form, so had the write succeeded every correct
passkey would have been refused with 401.

Both are fixed — stored and compared as text — and `test_the_challenge_is_stored_pinned_to_the_member`
guards it.

## 12. What is not built

There is no distribution record. The API is authentication, the club documents, registration,
payments and a health check. `accounts.User` is the substantive model, alongside the three tables in
`authn` supporting authentication, the three in `documents`, and the two in `payments`.

**The catalogue and the plant now exist as data**, which this section used to list as absent, and the
distinction matters: `strains`, `finished_product`, `cultivators` and `plant` have models,
constraints, migrations, a full admin and tests — and **no endpoint of any kind.** An administrator
can curate strains and product types, staff can write a cultivator's listing, and a plant can be
entered and transferred, all through `/admin/` or a shell. No member can see any of it, because
nothing serves it. That is Block 9 in `todo.md`.

C18's three levels are now three: the platform defines the finished product type catalogue, a listing
selects a subset, and `Plant.finished_product_types` inherits from its listing with no per-plant
override. One question that falls out of it is open — the property reads *live*, so a cultivator
removing a type from a listing changes what a member who already bought a plant may choose at
harvest. The precedent for the answer is `payments.Subscription`, which copies what a member agreed
to onto their own row; the natural place to take that snapshot is the order, in Block 5.

**Stock capture is now served**, which this section used to list as absent. `plant.api`, mounted at
`/api/stock`, captures one plant, takes an Excel workbook with a dry run, and generates the
per-cultivator template — so `allocate_serials` is no longer written for a five-hundred-row batch
that nothing submits. It is the first module in the project to ask an object-level permission
question: `platform.manage_plant_stock` is granted by every producer appointment, so `plant.stock`
asks the codename and then asks `ProducerMembership` whether this caller is appointed to *that*
farm. That second half is what C13 recorded as having nothing to point at.

What is still missing around the plant is a cultivator-facing read. Capture writes stock and nothing
serves it back: the stock-on-hand export is `manage.py export_stock` and an admin action, and the
browse a cultivator would use is the same queryset Block 5 reads for members. There is also no
status for a plant that died: C9 is open, nobody has decided whether a crop failure means
substitution, refund or credit, and inventing one would settle that in the schema.

**Payment status is now recorded**, which this section used to list as absent. What is still missing
around it is narrower and is set out in `design/features/payments.md` section 9: nothing schedules
the command that withdraws access from an unpaid membership, no member-facing screen shows a
subscription or offers cancellation, and no email is sent when a membership activates or lapses.

Roles are the newest instance of the same gap, and the sharpest. The three roles, the action
catalogue and the enforcement path are built and tested; almost nothing they govern exists. No
endpoint checks a `platform.*` permission, because no endpoint performs an action the catalogue
names. There is no cultivator organisation, so a primary cultivator cannot appoint anybody. A
sharing member can be registered and holds no plants — the plant model now exists, so
`platform.allocate_sharing_member_stock` is finally *expressible*, but there is no swap zone for them
to seed and Block 10 is gated on a legal opinion, which is the entire purpose of the role. See
`design/features/roles-and-permissions.md` section 13, which lists this properly.

Production deployment is deliberately out of scope. When a target is chosen it needs:

| Requirement | Note |
| --- | --- |
| Process manager fronting Uvicorn | Gunicorn with `UvicornWorker` on Linux |
| **MySQL 8.4** | SQLite today. 8.0.16 is the hard floor and MariaDB is refused at any version; `common/checks.py` asserts both at `migrate`, and section 8.1 has the reasons |
| Application settings for the database | `DJANGO_DB_HOST`, `_NAME`, `_USER`, `_PASSWORD`. Plus the MySQL client headers on the host, since `mysqlclient` has no Linux wheel. Section 8.0 |
| Static file handling | `STATIC_ROOT` plus WhiteNoise or a CDN |
| A real email provider | `MAILERS` uses the console backend; sign-in codes and the payment link are printed to the terminal and reach nobody |
| A Payfast merchant, and a reachable `notify_url` | Without both, no membership activates. The notification is server-to-server, so Django's public address has to be reachable from the internet |
| Something that runs `manage.py lapse_memberships` | A daily cron or an App Service WebJob. Until it exists, an unpaid membership keeps its access indefinitely |
| A shared cache backend | Without it the rate limits are per worker, not per deployment |
| `manage.py check --deploy` | The Django deployment checklist |

## 13. Risks

| # | Risk | Status                                                                                       |
| --- | --- |----------------------------------------------------------------------------------------------|
| 1 | Losing `DJANGO_FIELD_ENCRYPTION_KEY` destroys every stored identity number with no recovery path. | Open — needs a documented backup and rotation procedure                                      |
| 2 | The default `LocMemCache` makes rate limits per worker. A multi-worker deployment silently multiplies every limit. | Open — blocks production                                                                     |
| 3 | Codes are printed to the console. No email provider is configured, so no member can sign in on a deployed environment. | Partly closed, and stated wrongly — the console backend survives only under `DEBUG` and `_mailer` refuses a deployed environment naming no host. A provider is configured for both storefronts and the club mailbox authenticates; the market mailbox does not, and QA and production carry none of the values. P1 |
| 4 | `flush_sessions()` decodes every live session to find one member's. Linear in session count. | Accepted at current scale                                                                    |
| 5 | `login/start` reveals which addresses have a passkey, because credential IDs must reach the browser for the authenticator to match against. Inherent to identifier-first passkey flows; closing it means moving to a usernameless flow over discoverable credentials. | Accepted                                                                                     |
| 6 | `role` and `is_staff` are independent, so privilege is granted in two places and they can disagree. Accepted by decision; the admin says so rather than hiding it. | Accepted                                                                                     |
| 7 | The role-to-group mirror is best-effort. Harmless while no platform action comes from a group, which is today. It stops being harmless the day model permissions hang off a role group. | Open — see `features/roles-and-permissions.md` risk 3                                        |
| 8 | The action catalogue names actions against models that do not exist, so a codename may not survive contact with the real thing — and a renamed codename is a silent loss of authority, not an error. | Accepted at this stage                                                                       |
| 9 | A refused sharing-member registration tells the cultivator that the identity number is known to the club. Unavoidable while one account per identity document is enforced and the cultivator has to be told the registration failed. | Accepted — the refusal names no record, role or other cultivator                             |
| 10 | The sharing-member consent attestation is a cultivator's word rather than the person's own act, and nothing re-attests when the wording is revised. | Open — wants legal review of the wording, and a decision on notifying sharing members directly |
| 11 | A cultivator creates `User` rows. It is the only non-administrator route to an account, and it captures a third party's identity number. | Accepted — authorised on a permission, and every record carries who attested                 |
| 12 | The root `.gitignore` is a copy of the Next.js frontend template. It covers no Python artefact at all — not `.venv/`, `__pycache__/`, `*.pyc`, `.idea/`, nor `db.sqlite3` and its `.pre-customuser.bak` copy. The project is not yet under version control, so the first `git add` would commit a virtual environment and two databases. | Closed                                                 |
| 13 | Three constraints silently disappeared on MySQL, because it builds no partial index and Django omits what the backend will not build. Nickname uniqueness, mobile uniqueness and one-live-subscription-per-member were absent from any deployed schema while the models, the migrations and the suite all still described them. Section 8.2. | **Closed** — `accounts/0007` and `payments/0002` moved all three onto derived columns with unconditional unique indexes, each tied to its source by a check constraint |
| 14 | The suite runs on SQLite locally, so a constraint assertion passes there whether or not the deployed database enforces the rule. The one class of invisible failure the suite cannot catch by itself. Section 8.6. | **Closed** — `.github/workflows/ci.yml` runs the whole suite against MySQL 8.4, asserts the vendor before it does, and migrates an empty database so the hand-written backfills run |
| 15 | MySQL below 8.0.16 parses `CHECK` and discards it, which would silently unenforce every check constraint in the project — including the `is_active`/`status` backstop in section 3.1, and MariaDB would drop expression indexes the same way. | **Closed** — `common/checks.py` refuses both at `migrate`, and a second guard reports any constraint the backend will omit rather than build. Section 8.5 |
| 16 | Strain exclusivity spans two tables, so no constraint can express it. `CultivatorStrainListing.clean` is the only thing enforcing it, and a queryset `.create()` walks past it. | Open — closes when Block 2 puts a service in front of the write, as `accounts.services` does for sharing members |
| 17 | The C18 subset rule is enforced in a model and in an admin form, because a many-to-many is invisible to `Model.clean` until the row exists. `ManyToManyField.set` from a shell bypasses both. | Accepted — one shared `check_offered_types` means the rule exists once, and both callers are tested |
| 18 | Listing and profile images write to the default storage, which is local disk. `documents` is CDN-fronted but reserved for published club documents, and `accounts` is deliberately private, so public catalogue imagery has nowhere correct to go. | Open — a third, public container. Block 1 leftover |

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
payment, no cultivation record. Section 11 sets out what that means.

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

## 3. One app per feature

The Django side is split by feature, not by layer. There is no `api` app holding every endpoint and
every model; each feature owns its own models, admin, schemas and router.

| App | Owns | Depends on |
| --- | --- | --- |
| `common` | Field encryption, RSA ID checks. No models, no endpoints | — |
| `accounts` | The member record, the roles over it, and the admin | `common` |
| `authn` | Passkeys, emailed codes, sessions, rate limits | `accounts`, `common` |
| `documents` | Club documents, revisions, agreements | `accounts` |
| `membership` | Turning a sign-up submission into a member. No models | `accounts`, `documents`, `payments` |
| `payments` | The membership subscription, the Payfast integration, and what a payment does to an account | `accounts` |
| `cultivatorscollective` | Settings, URLs, and the API root | all of them |

The routers are mounted on one `NinjaAPI` instance in `cultivatorscollective/api.py`. That module
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

## 4. The member record

`accounts.User` is the project's `AUTH_USER_MODEL`. Members and staff are one model, told apart by
`is_staff`.

The alternative — Django's default user for admin plus a separate member model — would mean a second
authentication stack and two identities for anyone who is both a member and staff. In a collective,
that is most of the people who administer it.

The primary key is a **UUIDv7**, not v4. It is time-ordered, so inserts land at the end of the
primary-key index rather than scattering random writes across it. Free on SQLite, and it matters on
PostgreSQL.

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
| `POST /api/auth/login` | No | Email and password, retained for staff |
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

## 8. Rate limiting

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

## 9. Admin

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

## 10. Testing

| | |
| --- | --- |
| Runner | Django test runner |
| Layout | A `tests/` package per app, one module per layer |
| Tests | 794 |
| Command | `.venv\Scripts\python.exe manage.py test` |

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
| `cultivatorscollective/tests/test_admin_branding.py` | The brand skin over the admin: palette drift, template overrides, assets |
| `documents/tests/test_models.py` | File digests, immutability after publish, delete refusals |
| `documents/tests/test_services.py` | Failing closed on a missing revision, re-acceptance, stale versions |
| `documents/tests/test_api.py` | The payload contract, the 503, idempotent agreement |
| `documents/tests/test_admin.py` | What the admin refuses once a revision is published |
| `documents/tests/test_command.py` | Upload, digest and publish from the command line |
| `documents/tests/test_storage.py` | Reading Azure configuration, and the refusals that stop a broken deploy |

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

## 11. What is not built

There is no cultivation or distribution record. The API is authentication, the club documents,
registration, payments and a health check. `accounts.User` is the substantive model, alongside the
three tables in `authn` supporting authentication, the three in `documents`, and the two in
`payments`.

**Payment status is now recorded**, which this section used to list as absent. What is still missing
around it is narrower and is set out in `design/features/payments.md` section 9: nothing schedules
the command that withdraws access from an unpaid membership, no member-facing screen shows a
subscription or offers cancellation, and no email is sent when a membership activates or lapses.

Roles are the newest instance of the same gap, and the sharpest. The three roles, the action
catalogue and the enforcement path are built and tested; almost nothing they govern exists. No
endpoint checks a `platform.*` permission, because no endpoint performs an action the catalogue
names. There is no cultivator organisation, so a primary cultivator cannot appoint anybody. A
sharing member can be registered and holds no plants, because there is no plant model and so no swap
zone for them to seed — which is the entire purpose of the role. See
`design/features/roles-and-permissions.md` section 13, which lists this properly.

Production deployment is deliberately out of scope. When a target is chosen it needs:

| Requirement | Note |
| --- | --- |
| Process manager fronting Uvicorn | Gunicorn with `UvicornWorker` on Linux |
| A real database | SQLite today; the UUIDv7 choice anticipates PostgreSQL |
| Static file handling | `STATIC_ROOT` plus WhiteNoise or a CDN |
| A real email provider | `MAILERS` uses the console backend; sign-in codes and the payment link are printed to the terminal and reach nobody |
| A Payfast merchant, and a reachable `notify_url` | Without both, no membership activates. The notification is server-to-server, so Django's public address has to be reachable from the internet |
| Something that runs `manage.py lapse_memberships` | A daily cron or an App Service WebJob. Until it exists, an unpaid membership keeps its access indefinitely |
| A shared cache backend | Without it the rate limits are per worker, not per deployment |
| `manage.py check --deploy` | The Django deployment checklist |

## 12. Risks

| # | Risk | Status                                                                                       |
| --- | --- |----------------------------------------------------------------------------------------------|
| 1 | Losing `DJANGO_FIELD_ENCRYPTION_KEY` destroys every stored identity number with no recovery path. | Open — needs a documented backup and rotation procedure                                      |
| 2 | The default `LocMemCache` makes rate limits per worker. A multi-worker deployment silently multiplies every limit. | Open — blocks production                                                                     |
| 3 | Codes are printed to the console. No email provider is configured, so no member can sign in on a deployed environment. | Open — blocks production                                                                     |
| 4 | `flush_sessions()` decodes every live session to find one member's. Linear in session count. | Accepted at current scale                                                                    |
| 5 | `login/start` reveals which addresses have a passkey, because credential IDs must reach the browser for the authenticator to match against. Inherent to identifier-first passkey flows; closing it means moving to a usernameless flow over discoverable credentials. | Accepted                                                                                     |
| 6 | `role` and `is_staff` are independent, so privilege is granted in two places and they can disagree. Accepted by decision; the admin says so rather than hiding it. | Accepted                                                                                     |
| 7 | The role-to-group mirror is best-effort. Harmless while no platform action comes from a group, which is today. It stops being harmless the day model permissions hang off a role group. | Open — see `features/roles-and-permissions.md` risk 3                                        |
| 8 | The action catalogue names actions against models that do not exist, so a codename may not survive contact with the real thing — and a renamed codename is a silent loss of authority, not an error. | Accepted at this stage                                                                       |
| 9 | A refused sharing-member registration tells the cultivator that the identity number is known to the club. Unavoidable while one account per identity document is enforced and the cultivator has to be told the registration failed. | Accepted — the refusal names no record, role or other cultivator                             |
| 10 | The sharing-member consent attestation is a cultivator's word rather than the person's own act, and nothing re-attests when the wording is revised. | Open — wants legal review of the wording, and a decision on notifying sharing members directly |
| 11 | A cultivator creates `User` rows. It is the only non-administrator route to an account, and it captures a third party's identity number. | Accepted — authorised on a permission, and every record carries who attested                 |
| 12 | The root `.gitignore` is a copy of the Next.js frontend template. It covers no Python artefact at all — not `.venv/`, `__pycache__/`, `*.pyc`, `.idea/`, nor `db.sqlite3` and its `.pre-customuser.bak` copy. The project is not yet under version control, so the first `git add` would commit a virtual environment and two databases. | Closed                                                 |

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

The API surface is no longer only authentication. Forty-four routes are mounted across nine
routers: authentication, the club documents, member registration and the administrator's member
register, the profile, the membership payment, the produce store's customer registration, the strain
catalogue and plant stock capture. What is still absent is everything the money and the fulfilment
need — no cart, no order, no second gateway, no harvest. Section 6 is the surface; section 12 is the
gap.

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
| `core/accounts` | The identity, the permission catalogue over it, and the admin | `common` — and, in `services` only, `producers`, `club/membership` and `club/plant`. See below |
| `core/authn` | Passkeys, emailed codes, sessions, rate limits | `accounts`, `common` |
| `core/storefronts` | The two storefronts, who administers one, which storefront a request is for, and the record of every email sent | `accounts` |
| `core/documents` | Documents, revisions, and the agreements given — per storefront | `accounts`, `storefronts` |
| `core/attribution` | Which campaign brought somebody. Two touches per conversion, and the mixin any record inherits to point at them | `storefronts` |
| `core/payments` | The membership subscription, the Payfast integration, and what a payment does to a membership. **One gateway, billing one thing** — member purchases settle elsewhere, into another entity's account, through a gateway that does not exist yet: C10, C10.1 | `accounts`, `membership` |
| `commerce/producers` | The producer organisation, its appointed people, and which storefronts it sells into | `accounts`, `storefronts` |
| `club/membership` | Club membership, its nickname, and turning a sign-up submission into a member | `accounts`, `attribution`, `documents`, `payments` |
| `club/finished_product` | The catalogue of forms a harvest can take. No endpoints | — |
| `club/strains` | The strain catalogue, the aroma and effect vocabularies, and each producer's listing against a strain. Nine administrator endpoints at `/api/catalogue` | `producers`, `finished_product` |
| `club/plant` | The plant, its batch, its serial counter, the ownership history, and the stock-upload template and reader. Three capture endpoints at `/api/stock` | `producers`, `strains`, `finished_product` |
| `f2c` | Settings, URLs, and the API root | all of them |

**Every app sets `label` explicitly**, so a table is `accounts_user` rather than
`core_accounts_user`. That is what made the move a package rename and nothing more: no table
changed name, `AUTH_USER_MODEL` is still `accounts.User`, and no migration dependency moved. The one
app that *was* renamed is `cultivators` → `commerce/producers`, and that was the point of it — a
farmer growing carrots is the same record as a cultivator growing cannabis.

The boundary earns its keep by what it forbids. `club/plant` importing from `club/strains` is
ordinary; `commerce/producers` importing from `club/strains` would be the commerce spine learning
about cannabis, and the directory is what makes that visible in a diff.

**`accounts/services.py` is the one place that reaches the wrong way**, and it is worth naming rather
than leaving to be discovered. The models in `accounts` depend on `common` alone; the *service* that
registers a sharing member imports `producers`, `club/membership` and — since C15 —
`club/plant`, for `MEMBER_PLANT_HOLDING_LIMIT`. Sharing-member registration is a club operation
living in the spine because the record it writes is a `User`, and every one of those imports is that
fact showing. The C15 one is deliberate: the alternative is a second `4` in `accounts`, and two
constants for one statutory ceiling would eventually disagree — which would be the platform quietly
deciding a sharing member is a different kind of adult under the Act. The import direction is the
lesser cost, and the real fix is to move the registration into the club package, which is C27 and
C33's territory rather than this one's.

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
complaint back onto the field it came from — which is what `RowError.key` is for. **A cultivator now
does capture themselves**: `plant/api.py` is mounted at `/api/stock` and serves all three. What still
waits on Block 9 is the read back — the stock-on-hand screen and the withdrawal.

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
uploading is an argument to the command, and **is the session over the endpoint** — `plant/api.py`
takes the producer from the payload and then asks `ProducerMembership` whether the caller is
appointed to it.

The four newest apps were the first to be built with no router at all, and two of them still are.
`strains` and `plant` have since gained one — the administrator's catalogue and the cultivator's
capture — while `finished_product` and `producers` are reached through the Django admin alone. That
was a deliberate consequence of the sequencing rather than an oversight: `todo.md` put the models in
Blocks 1 and 3 and their endpoints later, and the endpoints arrived unevenly because the screens
did. What all four own is a full admin, which is where `member-roles.md`'s administrator CRUD over strains and
product types, and its "trace serials and batches", actually live today.

The dependency direction is the thing to check when reading them. `finished_product` knows nothing
about strains, listings or plants — the platform defines the catalogue and does not care who narrows
it — and `strains` reaches into it by string reference. That is C18's narrowing expressed as an import
direction: platform catalogue, then the cultivator's listing, then the plant. C18's fourth level — the
member choosing one of them as the delivery form — lands on the harvest finalisation in Block 6 and
imports nothing here.

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
limit is a count — `held_against_limit`, which C15 turned from a read into the refusal inside
`transfer_to` and C16 widened to every status short of dispatch. A model holding quantities would be
a denormalised aggregate over another table — and section 8.2 is the record of what this project
requires of a denormalised column: a specific justification, and **a check constraint tying it to its
source**. A cross-table count is the one kind
SQL cannot constrain at all, so it is the one kind this codebase has no way to make safe.

Two smaller things point the same way. `features/landing.md` puts `stock` in `RETAIL_VOICE`, the
banned-word list for member-facing copy — it is not the club's own vocabulary. And a `stock` app would
need `plant` while `plant` would need to know its own availability, which is the one rule this app
layout does not bend.

The apps that *do* belong in that space are later blocks with models of their own and a one-way
dependency on `plant`: orders and cart in Block 5, fulfilment in Block 6, the swap zone in Block 10.

### `core/attribution`: which campaign brought them

The commercial question is "which channel brings us members", and the answer has to survive the trip
from a link somebody clicked to a record that did not exist yet. `core/attribution` is one table and
one abstract mixin, and five decisions make it that small.

**Two touches per conversion, not a journey.** `CampaignTouch` is one campaign-bearing arrival — the
five `utm_*` parameters, the ad-network click id, the referring site, the landing path, and when it
happened. A conversion points at two of them: the campaign that found somebody and the one they
converted on. That pair answers what to spend on and what closed it. A row per visit was considered
and not taken — it grows without bound, it describes a person's browsing in detail, and it answers a
question nobody has asked; if it is ever wanted it is a second table pointing at this one.

**The pointers are on the converting record, not the touch.** `Attributed` is an abstract model
providing `first_touch` and `last_touch`, and `ClubMembership` inherits it. The alternative shapes are
both worse: ten campaign columns twice over on every model that cares is twenty columns per table and
a migration per table when a parameter is added, and a generic foreign key from the touch to "some
row in some table" costs a `django_contenttypes` join on every read, cannot be constrained by the
database, and would let a touch point at a row that has been deleted. Two real foreign keys per
record is the whole cost, and every campaign question is asked of one table. A market customer or an
order gains attribution by inheriting the mixin and changing nothing else.

**`first` and `last` are the same row where somebody arrived and joined in one visit**, which is most
conversions. That makes the saving worth having, and it makes "how many joined on the campaign that
found them" `first_touch_id=F('last_touch_id')` rather than a comparison of ten columns.

**Nothing is stored for a visitor who does not convert, and "direct" is not a value.** The touch
lives in a first-party cookie until a registration succeeds — see features/frontend section 6 — so
somebody who only looked leaves nothing in the database. And an arrival with no parameters, no click
and no external referrer produces no touch at all: attribution absent is `first_touch__isnull=True`,
because absence is the honest answer and a stored "direct" invites somebody to add it up as though it
were a channel that had been measured.

**Attribution never refuses a registration.** Every value in it is a label read off a URL, not a
field a member typed and can correct, so `attribution.services` cleans, caps or drops each one and
raises nothing. The five parameters are folded to lower case, because `Instagram` and `instagram` are
one advert and a report that shows them as two is a report nobody trusts twice. Query strings are
stripped from the referrer and the landing path. The one timestamp that comes from the client —
a first touch happened before there was any record to stamp — is dropped rather than believed when it
is malformed, naive, in the future, or older than a browser could credibly hold. A `utm_content` 400
characters long costs a report one odd row; refusing it would cost somebody their membership.

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

### 4.1 Status is the source of truth, not a boolean

`status` is one of Pending, Pending payment, Active, Suspended, Inactive, Sharing. Exactly one
value grants access.

Keeping six states rather than a boolean matters because "not yet approved", "not yet paid", "in
trouble", "erased on request" and "holds stock and does not sign in" are different situations with
different operational answers, and a single `is_active` flag cannot tell them apart. Sharing is the
one value that is not a stage in a lifecycle: it is where a sharing member sits until the deferred
read-only login is built, and `design/features/roles-and-permissions.md` section 3.2 says why reusing
Pending was rejected.

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

### 4.2 The identity number is encrypted, and still searchable

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

### 4.3 Two secrets, both separate from `SECRET_KEY`

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

### 4.4 RSA identity numbers

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

### 4.5 Roles are relationships, and permissions are a dictionary

**This section described a `role` column, and C28 retired it.** What follows is the built state; the
reasoning behind the change is `features/roles-and-permissions.md` section 4, and the migration that
dropped the column and its mirrored groups is `migrations.md` section 3.3.

There is no `role` column and no group mirroring one. Standing and authority are carried by three
relationships — `club/membership.ClubMembership`, `core/storefronts.StorefrontStaff` and
`commerce/producers.ProducerMembership` — and an account may hold all three at once. That is the
point of the change: one person administers the club, holds a membership and is appointed to a farm,
and a single column could only ever record one of the three.

The column was rejected on the same ground a Django group had been rejected before it. A group is
runtime data, an account can belong to none or to all of them, and no constraint can express
"exactly one" — but the deeper objection is that "exactly one" was the wrong rule.

What each relationship grants is a dictionary in `accounts/roles.py`, not `auth.Permission` rows.
Many of the actions are against a model that does not exist yet, and a permission row needs a
content type, which needs a model. `accounts/backends.py` registers a second authentication backend
that resolves the dictionary, so `user.has_perm('platform.purchase_plants')` works today and one
call still covers both kinds of permission. It authenticates nobody: `ModelBackend` stays the only
backend that can open a session.

`UserOut.role` survives as a **routing hint** and nothing more — a single word naming the club
destination an account belongs on, resolved by precedence because there is no single true value.
Risk 12 in `features/roles-and-permissions.md` is what happens if a caller reads it as an authority.

Three couplings matter and each is deliberate. **Authority is not status** — an inactive account
holds nothing whatever it is appointed to, which is what makes suspension and erasure safe without
either knowing about permissions. **Authority is not `is_staff`** — the two are independent by
decision, and section 9 of `features/roles-and-permissions.md` carries the cost. **The resolution
issues no query**, provided `User.objects.with_platform_roles()` has loaded the three relationships;
`UserOut` serialises the permission list inside async views, where an unloaded relation is fatal.

### 4.6 The sharing member

A **sharing member** is a real person a cultivator registers so that they can hold four flowering
plants and have them appear in the swap zone — a new club's zone is otherwise empty. They give a
name, an identity number and a nickname, and they do not transact: no cart, no subscription, no swap
action.

> **This section describes the decision, and the code does not match it yet.** C6 was decided as
> "a sharing member is a placeholder, not a person", acted on in Block 0.5, and then **reversed** —
> the "no login" in the brief was a cost control on the platform this one replaces, not a definition.
> The identity number, the age rule, the attestation and the erasure exemption all come back. C6 in
> `design/conflict.md` lists every place the code still says otherwise. Nothing below is built as
> written.

They are a `User` row, which is the decision worth defending. A separate model would have meant a
second nickname namespace (two people wearing one name in the swap zone is impersonation, not a
collision), a second encrypted identity column, a second erasure route, and two kinds of owner for
every plant, swap and certificate. As a row here they also inherit the club's "one account per
identity document" rule.

Four mechanisms carry the weight:

- `UserStatus.NON_AUTHENTICATING`, plus `is_active` derived from `status` under
  `user_is_active_matches_status`. Having no email address already makes them unauthenticatable, but
  that is a property of the *data* — the constraint is what stops somebody typing an address into the
  admin from silently turning stock into an account. The value is named for the fact rather than the
  club concept, which is why it survives the reversal: when the deferred login is built, a sharing
  member moves to `ACTIVE` and nothing needs renaming.
- A **consent attestation**: a cultivator captures a third party's identity number and offers that
  person's plants on their behalf, so POPIA needs a lawful basis the person never gave on a form.
  `sharing_consent_attested_by`, `_at` and `_version` record who swore what and when. It is called an
  attestation rather than a consent because it is weaker evidence than a member's own tick, and
  naming it accurately is what stops the two being confused later.
- `sharing_member_is_complete`, a check constraint requiring the registering cultivator, the
  attestation and a nickname — with erased rows exempt, because `soft_delete` blanks the nickname and
  the POPIA erasure route must never be the thing the database refuses. It replaces the narrower
  `sharing_member_has_a_cultivator` currently in the schema.
- The **four-plant allocation is the person's own statutory ceiling**, not a platform convention —
  C7. A sharing member holding four flowering plants may hold nothing else. **C15 has enforced it**,
  and took the number out of this module while doing so: `SHARING_MEMBER_PLANT_ALLOCATION` imports
  `plant.models.MEMBER_PLANT_HOLDING_LIMIT`, so the sharing member's four and every other adult's
  four are one constant that cannot drift. C16 widened the statuses it is counted over and this line
  did not have to change, which is what the import bought. The count asks who holds a plant and
  never what kind of member they are, because the role is meant to be droppable later — C33.

`accounts/services.py` is the write. It authorises on the permission rather than the role, checks the
caller is the primary of *this* producer, refuses a submission with no attestation before validating
any field, applies the same eighteen-year rule as sign-up, and refuses a duplicate identity number in
words that name no record — a leak it reduces rather than closes, and one the design document records
as a risk.

`registered_by` is `PROTECT`, so a cultivator who has registered sharing members cannot be
hard-deleted. Deleting a grower must not delete people; the routine answer, erasure, keeps the row.

**The login is specified and deferred.** A sharing member gets a read-only sign-in — the plants they
own and their status, nothing that moves a plant or spends money. It is deferred because it costs the
same whenever it is built, while the identity columns above are cheap only while the database is
empty.

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

**The send log de-identifies itself, and there is no scrub step to remember.**
`storefronts.EmailDispatch` records every email the platform sends — which member, which message,
when, and whether the mail server took it — and it stores **no email address at all**. Every email
this platform sends goes to a member record, so the log holds a foreign key and reads the address off
the account at the moment of sending. Erasure clearing `User.email` therefore removes the address
from the send history too, in one write, with nothing here to keep in step.

**It keeps no message body either, and that survived the move to a queue by being made
deliberate rather than incidental.** A sign-in code and a payment token both live in the body, and
neither belongs in a table staff can read. Since sends run in a Celery worker, something has to
carry the text from the request that composed it to the process that sends it — and the two
candidates were an `EmailDispatch.body` column and a Celery task argument. The task argument was
rejected: it sits in a Redis list in cleartext until a worker takes it, readable by anything
holding the broker key. So the column exists, and the write that records the outcome is the write
that erases it: `body` is in both `SENT_FIELDS` and `FAILED_FIELDS`, and the check constraint
`email_dispatch_body_is_cleared_once_settled` makes it a property of the schema rather than of two
methods. The text lives for the seconds a message is in flight; a row anybody reads holds none,
and it is in no admin fieldset. Without that, hashing the code at rest in `EmailOtp` would have
been quietly undone by a plaintext copy in a send log with a twelve-month window.

What is left after an erasure is which kinds of letter an anonymous account was sent
and when, which is the collective's own operating record. Age-based retention is separate and is a
schedule: `EMAIL_DISPATCH_RETENTION_DAYS`, enforced by `manage.py purge_email_dispatches` on a
timer.

**A campaign identifies nobody, so erasure has nothing to do to it.** `attribution.CampaignTouch`
holds the `utm_*` labels the club wrote into its own links, the ad-network click id, the referring
site, the landing path and a timestamp — and no visitor id, no device fingerprint, no IP address and
no third-party cookie. What makes the pair personal information is the record pointing at it, and
that pointer is on `ClubMembership`, so an erased member's campaign is reachable only through a row
whose personal data is already gone. Nothing is stored at all for a visitor who never registers: the
touch lives in a first-party cookie until there is a record to attach it to. Age-based retention is
the separate half and is again a schedule — `CAMPAIGN_TOUCH_RETENTION_DAYS`, enforced by `manage.py
purge_campaign_touches`, which deletes the label through `SET_NULL` and keeps the member.

An erased account cannot be reactivated. `activate()` raises rather than resurrecting a record whose
personal data is gone.

`user.deactivate()` is the reversible half: it blocks sign-in and cuts live sessions but erases
nothing.

**The three relationships deliberately survive erasure**, as the `role` column and its mirrored
groups did before C28 retired both. An appointment or a membership is a fact about the collective's
own structure rather than about the person, and it confers nothing on an account erasure has left
Inactive — `permissions_for` returns an empty set for one.

`flush_sessions()` is what makes either of those real. Changing `status` does not touch the session
store, so without it an already signed-in browser keeps working until its cookie expires. Sessions
carry no user column, so they have to be decoded to be matched — which is linear in live sessions
and is the one part of erasure that will need attention at scale.

## 6. The API surface

Mounted at `/api/` by the project URLconf. Endpoints require a valid session by default; the handful
that cannot opt out with `auth=None`.

Forty-four routes across nine routers, plus the health probe on the API root.

*Authentication — `core/authn`*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/health` | No | Liveness probe |
| `GET /api/auth/csrf` | No | Set the `csrftoken` cookie |
| `POST /api/auth/login/start` | No | Resolve an address to a passkey challenge, or send a code |
| `POST /api/auth/login/passkey` | No | Verify a WebAuthn assertion, open a session |
| `POST /api/auth/otp/start` | No | Send or resend a sign-in code |
| `POST /api/auth/otp/verify` | No | Exchange a code for a session |
| `POST /api/auth/logout` | No | End the session |
| `GET /api/auth/me` | Yes | The signed-in account |
| `POST /api/auth/passkeys/options` | Yes | Options for enrolling a passkey |
| `POST /api/auth/passkeys` | Yes | Store a verified new passkey |
| `GET /api/auth/passkeys` | Yes | List the account's passkeys |
| `DELETE /api/auth/passkeys/{id}` | Yes | Revoke one |

*Joining — `club/membership` and `core/accounts`*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `POST /api/members/register` | No | Club sign-up. Writes the `User`, the `ClubMembership` at Pending payment and one consent per club document, or nothing |
| `POST /api/members/nickname/availability` | No | Whether a nickname is free, asked while the form is still open |
| `POST /api/customers/register` | No | Produce-store sign-up. Writes a `User` and nothing else — no membership, no appointment, no permission |

*The account's own record — `core/accounts`*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/accounts/me/profile` | Yes | Name, nickname, mobile, avatar |
| `PUT /api/accounts/me/profile` | Yes | Correct them |
| `POST /api/accounts/me/avatar` | Yes | Upload a cropped avatar |
| `DELETE /api/accounts/me/avatar` | Yes | Remove it |
| `GET /api/accounts/me/avatar` | Yes | Serve it |

*Club documents — `core/documents`*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/documents/published` | No | Every published document for a storefront, for a legal index |
| `GET /api/documents/current` | No | Every document at the revision in force, or 503 |
| `GET /api/documents/outstanding` | Yes | Revisions this member has yet to agree to |
| `POST /api/documents/accept` | Yes | Record agreement to the revisions the member was shown |

*Payment — `core/payments`*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/payments/checkout/{token}` | No | The signed Payfast field set for a subscription awaiting payment |
| `GET /api/payments/me/checkout` | Yes | The same field set for the signed-in member |
| `POST /api/payments/payfast/notify` | No | Payfast's server-to-server notification. The only thing that activates a membership |

*The member register — `club/membership.administration_api`. Every route, read and write alike,
holds out for `platform.disable_user` — there is no `manage_members` codename, and the module
docstring says why a read is gated on the same one as a write*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/members` | Yes | The register, filterable |
| `GET /api/members/{id}` | Yes | One member, with their standing and disclosure history |
| `PUT /api/members/{id}` | Yes | Correct a member's details |
| `POST /api/members/{id}/suspend` | Yes | Block an account from signing in, reversibly |
| `POST /api/members/{id}/reinstate` | Yes | Lift a suspension |
| `POST /api/members/{id}/identity-number` | Yes | Read one in full, writing an `IdentityNumberDisclosure` row before decrypting |

*The strain catalogue — `club/strains`, every route behind `platform.manage_strain_catalogue`*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `GET /api/catalogue/strains` | Yes | The catalogue |
| `POST /api/catalogue/strains` | Yes | Add one |
| `GET /api/catalogue/strains/{id}` | Yes | One strain |
| `PUT /api/catalogue/strains/{id}` | Yes | Correct it |
| `POST /api/catalogue/strains/{id}/retire` | Yes | Retire it |
| `GET /api/catalogue/terms` | Yes | The aroma and effect vocabularies |
| `POST /api/catalogue/terms/{kind}` | Yes | Add a term |
| `PUT /api/catalogue/terms/{kind}/{id}` | Yes | Correct one |
| `GET /api/catalogue/cultivators` | Yes | The producers a listing can be written against |

*Stock capture — `club/plant`. Every route asks `platform.manage_plant_stock` **and** whether the
caller is appointed to the producer named in the request*

| Endpoint | Session | Purpose |
| --- | --- | --- |
| `POST /api/stock/plants` | Yes | Capture one plant |
| `POST /api/stock/uploads` | Yes | A workbook of them, with a `dry_run` that validates and writes nothing |
| `GET /api/stock/template` | Yes | The per-cultivator Excel template |

**There is no member-facing read of the last three groups, and that is deliberate.** The catalogue
and the stock a member would browse are the same rows read for a different audience, so Block 5
writes a second router rather than relaxing these.

`/api/documents/current` is unauthenticated because sign-up reads it before an account exists. It
answers 503 rather than a short list when a required document has no published revision: a caller
cannot tell an incomplete list from a complete one, so the endpoint has to.

`/api/docs` publishes the OpenAPI schema when `DEBUG` is on and 404s otherwise.

Each feature declares its own schemas — `accounts.schemas`, `authn.schemas`, `documents.schemas` —
written explicitly rather than generated from models, so a model change cannot silently alter the
payload the frontend depends on. `accounts.schemas.UserOut` omits `id_number` entirely: it is
encrypted at rest and has no business crossing the wire to a browser. It carries `role` and the
`permissions` the account's three relationships grant, sent together so the frontend never maps one
to the other — a second copy of the catalogue in a browser bundle would drift from the one the API
enforces. **`role` is a routing hint derived by precedence, not the source of the list beside it** —
section 4.5. It also carries `status` and `membership_status`, which answer different questions:
whether this identity may sign in, and where their club membership stands, the second being null for
a produce-store customer. Both `role` and `permissions` are for rendering navigation; every endpoint
checks the permission itself. `common.schemas` holds only
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
check constraint here is decoration, including the two that section 4.1 calls the backstop for writes
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

The nickname was the worst of the three, and section 4.6 says why without knowing it: a nickname is
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
constraint**, exactly as `is_active` is tied to `status` in section 4.1. `save()` keeps them true;
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
an undeclared dependency is one that is eventually not met. `core/common/checks.py` declares it. Both
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

**There is no role field, because there is no role column — C28.** Nor is there a role filter.
Authority is granted by writing one of the three relationships: `ClubMembership` has an admin of its
own, so does `StorefrontStaff`, and `ProducerMembership` is an inline on `Producer`. That is where a
cultivator or an administrator is appointed, and it is why one person can now be all three.

**Group membership is a form field again.** It was read-only for as long as `save()` mirrored the
role column into it — a picker whose value the admin's `save_m2m()` would overwrite after the model
save. With no column to mirror there is no mirror, and `groups` is an ordinary editable field.

What an account may do is displayed **read-only**, resolved through `accounts.roles` rather than
restated, so the admin cannot describe authority the application does not grant. There are
deliberately no bulk authority actions: activate, suspend and erase are batch operations, and
handing out authority over other members' records is not.

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
| `accounts/tests/test_customer_registration.py` | The store's sign-up: the byte-identical answer for a new address and a duplicate, the handset match that is sent nothing, the 503 that keeps the account when mail fails, and that every refusal code is one the store renders |
| `accounts/tests/test_profile.py` | That an account with no relationship at all — a store customer — reads and edits its own record, which is what retiring `manage_own_profile` was for |
| `accounts/tests/test_avatars.py` | Upload, crop, replace and delete, and what is refused |
| `accounts/tests/test_notifications.py` | The suspension email, per storefront, on commit, with a send failure logged rather than raised |
| `accounts/tests/test_uniqueness_keys.py` | The blind index and the normalised mobile key, against raw updates |
| `accounts/tests/test_roles.py` | The catalogue's own shape and namespacing, that the granting sets do not overlap, the UC-tier actions kept out of it, and `has_perm` through both backends |
| `accounts/tests/test_sharing_members.py` | Registering one, the attestation without which nothing is written, the constraints that stop them signing in, the vague refusal, erasure. Currently asserts the *absence* of all of that, per the superseded reading of C6 |
| `membership/tests/test_services.py` | The registration write: duplicates, the age rule, and the membership status it lands on |
| `membership/tests/test_api.py` | The endpoints sign-up posts to, and what they refuse |
| `membership/tests/test_administration.py` | The register's reads and writes, and the disclosure row written before an identity number is decrypted |
| `membership/tests/test_administration_api.py` | Every route behind `platform.disable_user`, and the 403 for an account without it |
| `membership/tests/test_nickname_availability.py` | Taken, reserved and malformed, and that the three are not distinguishable to a caller |
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
| `producers/tests/test_models.py` | That the pseudonym is the account's own display name and not a second namespace; publication defaults; the appointment rights and the primary that only one person holds |
| `plant/tests/test_leaf_rating.py` | The brief's five worked examples, the undocumented midpoint, and that the result is always a step of 0.5 |
| `plant/tests/test_models.py` | Serial allocation and the refusal to restart a sequence; the constraints against raw updates; the ownership history and the one gap in it; the four-plant count and its boundary — a harvested plant and a processed one count, a shipped one does not (C16) — and the refusal built on it: a fifth plant, a harvested fifth plant, the remedy named in the message, the message saying a harvest frees no place, the ledger left untouched, the allowance that never reads negative, and the member with four harvested plants who has nothing swappable |
| `plant/tests/test_spreadsheet.py` | The template round-tripping through its own reader; the ambiguous date that is refused rather than guessed; the price refused rather than rounded; duplicates inside one file; that there is no cultivator column and none for anything the platform generates |
| `plant/tests/test_upload.py` | That one bad row stops the file and consumes no serial; that another cultivator's listing is invisible; the C18 column confirming and never overriding; batches shared across two uploads; every refusal the commands make |
| `plant/tests/test_capture.py` | That a single capture is refused by the same rules as a workbook row and shares its serial counter and plant-ID namespace; that errors arrive keyed by field; and that the admin allocates a serial on add |
| `plant/tests/test_export.py` | That stock on hand means unsold; that a withdrawn plant is in no scope and another cultivator's stock in none of them; the overdue flag; that every row shares one "today"; and that the owner column is a nickname, absent when nothing is owned |
| `plant/tests/test_api.py` | The three capture routes: the four outcomes and their four status codes, the dry run that writes nothing, and the object-level refusal when a caller is appointed to a different farm |
| `strains/tests/test_api.py` | The catalogue routes and the permission each holds out for |
| `strains/tests/test_services.py` | What the router does not decide: the authorisation, retirement without deletion, and C18 on a listing |
| `storefronts/tests/test_mail.py` | That each storefront sends as itself, and the configuration refusals that stop a deploy naming no host or no sender |
| `storefronts/tests/test_checks.py` | The host map, and what an unmapped host falls back to |
| `common/tests/test_checks.py` | The MySQL version floor, the MariaDB refusal, and the report of any constraint the backend will silently omit |

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

**Email delivery and read tracking are not built, and cannot be from here.** `EmailDispatch`
records three stages — sent, delivered, read — and this deployment can fill in exactly one of them.
Mail leaves through plain SMTP, and a relay accepting a message is not the message arriving: nothing
downstream reports back, so `delivery_status` stays at *not reported* on every row. Closing that gap
means a provider that emits delivery events — Postmark, Mailgun, SES, any of them — which is a
provider account, DKIM/SPF/DMARC on both storefront domains, and one signed webhook route.
`EmailDispatch.apply_provider_event` is the whole of the handler behind that route and is written and
tested already, so the remaining work is configuration and a signature check rather than a migration.

Reading is a separate decision rather than the same gap. An open is only knowable through an
invisible image in the message body, and the answer it gives is poor — Apple Mail's privacy proxy
prefetches images, so it reports opens nobody made, and clients that block images report none where
there were some. **Put on a one-time sign-in code it is also surveillance of a security event**, so
it is deliberately absent: `read_status` says *not tracked*, which is a different statement from *not
read*, and the distinction is the reason the value exists. `record_read` is where a reversal would
land if the club ever wants opens on the payment-link email alone.

There is no distribution record. The API is authentication, the club documents, both registrations,
the account's own profile, the membership payment, the member register, the strain catalogue and
stock capture. `accounts.User` is still the substantive model, alongside the three relationship
tables that carry standing, the three in `authn` supporting authentication, the three in
`documents`, and the two in `payments`.

**The catalogue and the plant now have endpoints**, which this section used to list as absent twice
over — first as models, then as models with no route. `strains`, `finished_product`, `producers` and
`plant` have models, constraints, migrations, a full admin and tests; two of the four now have a
router as well. What survives of the original point is narrower and still true: **every one of those
routes is written for staff or for a cultivator, and none of them for a member.** A member can see
nothing of the catalogue or the stock, because the browse that would serve it is Block 5's and does
not exist. `finished_product` and `producers` are still reached through `/admin/` or a shell alone —
so a primary cultivator cannot appoint anybody except through the Django admin, which is Block 2's
remaining route.

C18 is decided, and it has four levels rather than three. Three of them narrow and are built: the
platform defines the finished product type catalogue, a listing selects a subset, and
`Plant.finished_product_types` inherits from its listing with **no per-plant override** — now closed
rather than deferred. The fourth selects and is unbuilt: the member chooses one of the inherited types
at harvest as the form the plant is delivered in, recorded on Block 6's finalisation record rather than
as a column here.

**The question that fell out of it is now ruled, and the code is behind the ruling.** The property
reads *live*, so a cultivator removing a type from a listing changes what a member who already bought
a plant may choose at harvest. C18 rules the set **snapshotted onto the order**, on the
`payments.Subscription` precedent — what a member agreed to is copied onto their own row. The order is
Block 5, so nothing changes here yet; the docstring on `Plant.finished_product_types` still describes
the question as open, and correcting it is the first line of that work. A platform-level withdrawal
still beats the snapshot: `FinishedProductType.is_available` is intersected with it at finalisation.

**Stock capture is now served**, which this section used to list as absent. `plant.api`, mounted at
`/api/stock`, captures one plant, takes an Excel workbook with a dry run, and generates the
per-cultivator template — so `allocate_serials` is no longer written for a five-hundred-row batch
that nothing submits. It is the first module in the project to ask an object-level permission
question: `platform.manage_plant_stock` is granted by every producer appointment, so `plant.stock`
asks the codename and then asks `ProducerMembership` whether this caller is appointed to *that*
farm. That second half is what C13 recorded as having nothing to point at.

**The ownership ledger now opens at capture rather than at the first sale — C13.** *Each plant must
always have a verifiable owner*, so `PlantOwnership` carries a `cultivation` tenure held by the
`Producer`, written by `Plant.save` on insert and closed by the first transfer. Two nullable holder
columns — `owner` for a member, `producer` for a farm — with `tenure_has_one_holder` insisting on
exactly one, and `tenure_reason_matches_holder` keeping the reason and the holder in agreement. The
alternative was a user account per farm that nobody signs into, which every membership rule would
then have to exclude. The structure it serves is `features/cultivator-organisation.md`.

**The administrator's read of that ledger is C14, and it is not built.**
`platform.view_member_inventory` is granted to the club administration and has no endpoint: what
each member and sharing member holds, with the `PlantOwnership` trail behind each plant. Two
constraints on it are decisions rather than details — the query filters on plants and their owners
and never asks what kind of member the owner is, because C33 requires the sharing-member role to
stay droppable; and the projection carries the nickname and no identity column, because oversight of
stock needs no identity and the full read of an identity number lives on the member's own record,
where it writes an `IdentityNumberDisclosure` row before decrypting.

**The four-plant statutory limit is now enforced — C15, counted per C16.**
`MEMBER_PLANT_HOLDING_LIMIT` is `4`, `Plant.assert_may_be_held_by` refuses a fifth, and `transfer_to`
calls it — the only place `owner` is written, and a status only ever moves forwards, so acquisition is
the only way a count can rise.

**What the four is counted over is C16's, and C16 reversed the reading C15 shipped.**
`HOLDING_LIMIT_STATUSES` is preflowering, in bloom, harvested and processed: every plant the club is
still holding for the member, released at `shipped`. A harvested plant therefore keeps its place until
it goes out for delivery, because until then it is stock in the club's custody with a row of its own —
and a limit that stopped counting at the cut would be the platform declining to count what it could
see. `SHIPPED` stands in for the delivery-confirmed event **C9.1** has not chosen; when it exists it
replaces `processed` as the last member of that tuple and nothing else moves. `FLOWERING_STATUSES`
still exists and now means only what it says: what may be swapped, per `harvest.md`. The two tuples
are deliberately separate. It is a count in Python rather than a constraint, because SQL cannot
express *at most four rows matching a predicate per owner*; the concurrent-transfer race that leaves
is named in the method and accepted, alongside the same trade already recorded for `owner` itself and
for strain exclusivity (risk 16). Two limits in the same brief are **not** built and will not be —
the household limit and the dried-weight limit — and C15 carries them as accepted risks with the
reason stated in the club rules: the platform cannot observe what a member holds off-platform, and
enforcing what it cannot see would manufacture a record of a control that never ran.

What is still missing around the plant is a cultivator-facing read. Capture writes stock and nothing
serves it back: the stock-on-hand export is `manage.py export_stock` and an admin action, and the
browse a cultivator would use is the same queryset Block 5 reads for members. There is also no
status for a plant that died, and **C9 now says what one has to express**: a failed crop is
substituted with an equivalent plant where one exists — the ownership row moves to the substitute
serial and the money, which the club holds from order until delivery, follows it — and is refunded
out of those held funds where no equivalent exists. So the plant needs a dead status and the order
needs a **held or released** state; credit was ruled out and is not a case to model. What is still
open is **C9.1**, the event that releases the funds, and that is an order-level fact rather than a
plant one, so it does not block the plant status.

**Payment status is now recorded**, which this section used to list as absent. What is still missing
around it is narrower and is set out in `design/features/payments.md` section 9: nothing schedules
the command that withdraws access from an unpaid membership, no member-facing screen shows a
subscription or offers cancellation, and no email is sent when a membership activates or lapses.

**What is missing around payments is wider than that, and C10 is what made it visible.** This app is
not "the payment layer" — it is one gateway billing one product into one merchant account. The money
map C10 records needs two:

- The **membership fee** is collected by **F2C** through Payfast, which is what is built, and 60% of
  it is owed onward to the club. That obligation is settled outside the application; the collection is
  not, and it is correct as it stands.
- **Everything a member buys** is collected by the **Cultivators Collective**, a different legal
  entity, through **PayGate or Stitch** — undecided, and the two are not interchangeable. Nothing
  exists. `payfast_config` is a single-gateway assumption carrying one merchant identity, and no order
  model records which gateway or which account took the money, which two entities reconciling off the
  same table will need. This is **C10.1**, it is build work rather than a question about the brief,
  and it sits in Block A ahead of either storefront's checkout.

Two consequences reach the schema rather than the integration. The commission has to be recorded as an
**amount on the transaction** — the rates themselves are out of scope for the application, but a
statement of account without a commission line cannot be reconciled. And there is no disbursement path
at all: Payfast does not pay out, and neither candidate gateway is being considered for it, so the
realistic first release is a **payment run** — a payable list per cultivator per period over released
orders, against the encrypted bank details already on `Producer` — rather than a payout API.

Roles are the newest instance of the same gap, though it has narrowed. The three relationships, the
action catalogue and the enforcement path are built and tested; most of what they govern still does
not exist. **Four services now check a `platform.*` permission** — `membership.administration` for
`disable_user`, `plant.stock` for `manage_plant_stock`, `strains.services` for
`manage_strain_catalogue` and `accounts.services` for `register_sharing_member` — where this section
used to say none did, and `plant.stock` is the only one that also asks an object-level question. The
other twenty-odd codenames still name actions with nothing to perform them against. The cultivator
organisation exists as a record but has no endpoint, so a primary cultivator appoints staff in the
Django admin rather than on a screen. A sharing member can be registered and holds no plants — the
plant model now exists, so
`platform.allocate_sharing_member_stock` is finally *expressible*, but there is no swap zone for them
to seed. **Block 10 is no longer gated on a legal opinion** — C7 is decided as residual risk — so the
purpose of the role is now reachable rather than blocked. See
`design/features/roles-and-permissions.md` section 13, which lists this properly.

**Production deployment is no longer out of scope, and the target is decided — C31.** Azure in West
Europe: three Container Apps (the API and both storefronts), an Azure Database for MySQL Flexible
Server 8.4, an Azure Managed Redis, a Container Registry, a storage account for media and a Log
Analytics workspace. The API image is written — `Dockerfile` builds `mysqlclient` in a build stage
and ships `libmariadb3` and the CA roots in the runtime stage, non-root — and `deploy/entrypoint.sh`
waits for the database, gates on `check --deploy --fail-level WARNING`, migrates and then serves
under Uvicorn. Both Next.js images are written too. What is left is provisioning rather than code:

| Requirement | Position |
| --- | --- |
| Process manager fronting Uvicorn | **Settled by the container.** `deploy/entrypoint.sh` runs Uvicorn directly and Container Apps supplies the supervision; no Gunicorn layer |
| **MySQL 8.4** | **Built.** SQLite survives only as the local default. 8.0.16 is the hard floor and MariaDB is refused at any version; `core/common/checks.py` asserts both at `migrate`, and section 8.1 has the reasons |
| Application settings for the database | `DJANGO_DB_HOST`, `_NAME`, `_USER`, `_PASSWORD`, plus `DJANGO_DB_SSL_CA` — the connection is `VERIFY_IDENTITY` or it is refused. Section 8.0 |
| Static file handling | `STATIC_ROOT` plus WhiteNoise or a CDN. Still open |
| A real email provider | **Mostly done, and this row used to be wrong.** The console backend survives only under `DEBUG`, and `_mailer` refuses a deployed environment naming no host, so nothing could ever have shipped silently printing to a terminal. A cPanel provider is configured for both storefronts on 587 with STARTTLS and the club mailbox authenticates. Left: the market mailbox does not, and neither QA nor production carries the values. P1 |
| `DJANGO_BEHIND_PROXY=true` on the API container | **The single highest-consequence variable.** Container Apps ingress is a reverse proxy, so without it `verify_notification` sees Envoy's address and rejects every Payfast notification. `payments.W001` fires on `check --deploy` and the entrypoint gates on it, so a revision missing it never starts |
| A Payfast merchant, and a reachable `notify_url` | Without both, no membership activates. The notification is server-to-server, so Django's public address has to be reachable from the internet. **This is F2C's merchant account**, which is correct for the membership fee and wrong for everything else — C10 |
| A second gateway, and a second merchant account | Member purchases collect into the **Cultivators Collective's** account through PayGate or Stitch. Neither is chosen and nothing is built, so no plant order can be paid for at all — C10.1 |
| Something that runs `manage.py lapse_memberships` | **Built, and not as this row said.** A **Celery worker and beat**, off the API image — `deploy/entrypoint.sh worker` and `... beat`, beat capped at one replica. Not the Function App or the Container Apps Job earlier revisions named: both kept the schedule in platform configuration and out of any commit, and neither could be run locally. It covers all three unrun jobs, not just this one. The schedule is `CELERY_BEAT_SCHEDULE`, the record is `scheduling.ScheduledRun`, and the broker is database 1 of the Redis already provisioned below. No protected endpoint was needed — C31, `design/deploy.md` 5.2 |
| A shared cache backend | **Built.** Azure Managed Redis deployed, `redis:7-alpine` locally; `f2c/cache.py` refuses a deployed environment naming none, and refuses `redis://` where the access key would travel in clear |
| `manage.py check --deploy` | **Enforced rather than remembered.** The entrypoint runs it at `--fail-level WARNING` before Uvicorn starts, so a warning is a failed revision and the previous one keeps serving |

## 13. Risks

| # | Risk | Status                                                                                       |
| --- | --- |----------------------------------------------------------------------------------------------|
| 1 | Losing `DJANGO_FIELD_ENCRYPTION_KEY` destroys every stored identity number with no recovery path. | Open — needs a documented backup and rotation procedure                                      |
| 2 | The default `LocMemCache` makes rate limits per worker. A multi-worker deployment silently multiplies every limit. | **Closed — C31.** Azure Managed Redis in QA and production, `redis:7-alpine` locally. `f2c/cache.py` refuses a deployed environment that names no `DJANGO_REDIS_URL`; `LocMemCache` survives only as the no-configuration fallback that keeps the suite runnable |
| 3 | Codes are printed to the console. No email provider is configured, so no member can sign in on a deployed environment. | Partly closed, and stated wrongly — the console backend survives only under `DEBUG` and `_mailer` refuses a deployed environment naming no host. A provider is configured for both storefronts and the club mailbox authenticates; the market mailbox does not, and QA and production carry none of the values. P1 |
| 4 | `flush_sessions()` decodes every live session to find one member's. Linear in session count. | Accepted at current scale                                                                    |
| 5 | `login/start` reveals which addresses have a passkey, because credential IDs must reach the browser for the authenticator to match against. Inherent to identifier-first passkey flows; closing it means moving to a usernameless flow over discoverable credentials. | Accepted                                                                                     |
| 6 | ~~`role` and `is_staff` are independent, so privilege is granted in two places and they can disagree.~~ | **Closed by C28 and C29.** There is no role column. `is_staff` and a `StorefrontStaff` row remain two grants made in the same admin, which is intended — `features/roles-and-permissions.md` section 9 |
| 7 | ~~The role-to-group mirror is best-effort and drifts.~~ | **Closed.** The groups went with the column — section 4.5, and `migrations.md` §3.3. `groups` is an ordinary editable admin field again |
| 8 | The action catalogue names actions against models that do not exist, so a codename may not survive contact with the real thing — and a renamed codename is a silent loss of authority, not an error. | Accepted at this stage                                                                       |
| 9 | A refused sharing-member registration tells the cultivator that the identity number is known to the club. Unavoidable while one account per identity document is enforced and the cultivator has to be told the registration failed. | Accepted — the refusal names no record, role or other cultivator. C34 is the case that makes it sting: a sharing member trying to join the club properly |
| 10 | The sharing-member consent attestation is a cultivator's word rather than the person's own act, and nothing re-attests when the wording is revised. Under C33 it now evidences the mandate to offer that person's plants as well as the POPIA basis. | Open — wants legal review of the wording. The deferred read-only login is what closes it: a person who signs in can consent for themselves |
| 11 | A cultivator creates `User` rows. It is the only non-administrator route to an account, and it captures a third party's identity number. | Accepted — authorised on a permission, and every record carries who attested                 |
| 12 | The root `.gitignore` is a copy of the Next.js frontend template. It covers no Python artefact at all — not `.venv/`, `__pycache__/`, `*.pyc`, `.idea/`, nor `db.sqlite3` and its `.pre-customuser.bak` copy. The project is not yet under version control, so the first `git add` would commit a virtual environment and two databases. | Closed                                                 |
| 13 | Three constraints silently disappeared on MySQL, because it builds no partial index and Django omits what the backend will not build. Nickname uniqueness, mobile uniqueness and one-live-subscription-per-member were absent from any deployed schema while the models, the migrations and the suite all still described them. Section 8.2. | **Closed** — `accounts/0007` and `payments/0002` moved all three onto derived columns with unconditional unique indexes, each tied to its source by a check constraint |
| 14 | The suite runs on SQLite locally, so a constraint assertion passes there whether or not the deployed database enforces the rule. The one class of invisible failure the suite cannot catch by itself. Section 8.6. | **Closed** — `.github/workflows/ci.yml` runs the whole suite against MySQL 8.4, asserts the vendor before it does, and migrates an empty database so the hand-written backfills run |
| 15 | MySQL below 8.0.16 parses `CHECK` and discards it, which would silently unenforce every check constraint in the project — including the `is_active`/`status` backstop in section 4.1, and MariaDB would drop expression indexes the same way. | **Closed** — `core/common/checks.py` refuses both at `migrate`, and a second guard reports any constraint the backend will omit rather than build. Section 8.5 |
| 16 | Strain exclusivity spans two tables, so no constraint can express it. `CultivatorStrainListing.clean` is the only thing enforcing it, and a queryset `.create()` walks past it. | Open — closes when Block 2 puts a service in front of the write, as `accounts.services` does for sharing members |
| 17 | The C18 subset rule is enforced in a model and in an admin form, because a many-to-many is invisible to `Model.clean` until the row exists. `ManyToManyField.set` from a shell bypasses both. | Accepted — one shared `check_offered_types` means the rule exists once, and both callers are tested |
| 18 | Listing and profile images write to the default storage, which is local disk. `documents` is CDN-fronted but reserved for published club documents, and `accounts` is deliberately private, so public catalogue imagery has nowhere correct to go. | Open — a third, public container. Block 1 leftover |
| 19 | The household limit — eight flowering plants where two or more adults live — is not modelled and will not be. Two members of one household can each hold four here, and the household can exceed eight once plants held elsewhere are counted. | **Accepted — C15, R-C15.1.** Enforcing it means collecting who a member lives with: a third party's personal information, for a purpose the platform cannot achieve. POPIA §10 refuses it. Stated in the club rules as the member's own responsibility |
| 20 | The dried-weight limit — 600g per person, 1.2kg per household — is not modelled and will not be. A member taking repeated delivery of finished product could exceed it and the platform would not know. | **Accepted — C15, R-C15.2.** There is no event at which the platform learns what a member still holds, and a cumulative-delivery proxy would refuse honest members while catching nobody. Stated in the club rules |
| 21 | The four-plant limit is enforced *per member on this platform*. A member who also grows at home or belongs to a second club can hold four here and be over the statutory limit in fact. | **Accepted — C15, R-C15.3.** The same off-platform blindness as 19 and 20, and the one the club rules must state plainly: four held through this club counts against the same four the law allows |
| 22 | A plant stops counting against a member's four at `shipped`, so one in a courier's hands counts against nobody and a member can briefly hold five in fact. | **Accepted — C16, R-C16.1.** It closes itself: C9.1's delivery-confirmed event replaces `shipped` as the boundary. Days rather than weeks, and it errs into the window the platform cannot observe anyway |
| 23 | The holding count is reduced by a status change rather than by a transaction, so a cultivator marking a batch `shipped` frees places on members' allowances. | **Accepted — C16, R-C16.3.** It is the correct behaviour, and the exposure is the honesty of the dispatch record — the same trust the certificate of ownership already rests on. Worth an admin log entry when Block 6 builds finalisation |
| 22 | The four-plant check is a count in Python, not a constraint. Two concurrent transfers to a member holding three can both pass and leave five. | Accepted — a member acquires plants one deliberate purchase or swap at a time, and the remedy is an `ADJUSTMENT` tenure. Closes with risk 16 when Block 2 puts a service in front of every plant write, or not at all |

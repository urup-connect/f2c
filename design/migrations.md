# Migrations: the conventions, and what the cleared set encoded

Two things live here. **Sections 1 and 2** are standing rules for writing a migration in this
project, and they describe current practice. **Section 3** is a one-time record: the schema is being
rebuilt from the models under Block 0.5, every numbered migration is deleted, and this is what those
files said that `models.py` does not.

Read section 3 before writing the new initial set. Two items in it are data that has to be
recreated; the third was a decision, and it has since been taken — 3.3.

---

## 1. What a migration may not do

**Never import application code.** Every migration in the cleared set that needed a constant
inlined it — `PLANT_SERIAL_SEQUENCE`, `LIVE_STATUSES`, `nickname_key`, the four group names — with
the same comment each time: *a migration is a historical record and has to keep applying the same
way in five years; importing application code would let a later edit silently change what this
migration did.* Use `apps.get_model`, never a direct model import.

**Refuse, do not repair.** Where a migration adds a constraint the existing data might violate, it
counts the violations first and raises with a message saying what to do, rather than picking a row
to keep. `accounts/0007` and `payments/0002` both did this. The payments case says why in one line:
two live subscriptions against one member is a money question — which mandate is real, whether the
other was charged, whether anything is owed back — and a migration does not get to answer that
silently.

**Count, never name.** A migration that prints a nickname, a mobile number or a member's identity
writes it into every deploy log and CI transcript that runs. The rule established in
`accounts/0003` and kept by every migration after it: report *how many* rows clash and where to find
them in the admin, never *which*. Reading them in the admin is an authorised act; reading them in a
build log is not.

**A derived column and the constraints over it ship together.** `accounts/0007` put the two unique
indexes and the two `key_matches_source` check constraints in one migration, deliberately: a deploy
sitting between them would have a unique index over a column nothing guarantees is current.

---

## 2. Portability, which is already documented elsewhere

`backend.md` sections 8.1 to 8.5 carry the whole of it and are not repeated here. In short: **MySQL
builds no partial unique index, and Django omits one it cannot build without raising anything**, so
a rule can be described by the model, the migration and the tests while being absent from the
deployed schema. The project's answer is a derived column that is null where the condition excluded
a row, plus an unconditional unique index over it, plus a check constraint tying the column to its
source.

Three rules are expressed that way and the models carry all three, so a fresh initial migration
reproduces them without help:

| Rule | Column | Model |
| --- | --- | --- |
| One nickname, case-insensitive | `nickname_key` | `accounts.User` |
| One handset, one member | `mobile_key` | `accounts.User` |
| One live subscription per member | `live_for_user` | `payments.Subscription` |

`plant.PlantOwnership.current_for_plant` is a fourth, introduced in its initial migration.

The backfills that accompanied these on the way in are moot against an empty database. Their
*reasoning* is section 1.

---

## 3. What the cleared migrations encoded

`todo.md` Block 0.5 named four migrations to check. That list was wrong in both directions, which is
the reason the step exists. Corrected below.

### 3.1 Must be recreated — club documents

**Was: `documents/0002_seed_club_documents`.** A data migration registering three documents by
identity only:

| Slug | Title | Position | Storefront | Audience | Agreement |
| --- | --- | --- | --- | --- | --- |
| `club-rules` | Club Rules | 0 | club | customer | at_registration |
| `annexures` | Annexures | 1 | club | customer | at_registration |
| `constitution` | Constitution | 2 | club | customer | at_registration |

**No revisions, deliberately.** The files on the CDN predate the app, so nothing knows their
digests, and a seeded revision would carry a blank `sha256` — an unverifiable row in the one table
whose entire job is to be verifiable. The consequence is intended: **sign-up fails closed until each
document has a revision published** through the admin or `manage.py publish_document`. That
one-time step is what gets a real digest recorded for every file a member is ever shown.

The slugs match `CLUB_DOCUMENT_IDS` in the frontend. Both the slugs and the consent wording are
seeds, not constraints — staff own them from there.

*Carry forward, with the new columns.* Under C26 these seed against the club storefront with
`audience=customer` and `agreement=at_registration`. The market will need its own terms, privacy
notice and data policy — new rows at `audience=public`, `agreement=none`, not copies of these three.

### 3.2 Must be recreated — the plant serial counter

**Was: `plant/0001_initial`, a hand-edited operation at the end.** Not on the todo's list, and the
more dangerous omission of the two.

It seeds one row: `SerialCounter(name='plant', next_value=1)`. The reason it is a migration rather
than a `get_or_create` in the allocator is written into the file, and it is worth keeping verbatim
in spirit: **`allocate_serials` deliberately refuses to create the row**, because a missing counter
and a counter at 1 look identical to code and are completely different to a member — recreating it
would restart the sequence and reissue serials already printed on certificates of ownership. The row
is written once, and its absence afterwards is an error for a person to look at rather than
something the application repairs.

*Carry forward, and check the operation still lands last so the table certainly exists.* Note that
`verticals.md` section 6 scopes serial counters per producer, so the seeded name may no longer be
the bare string `plant`.

### 3.3 A decision, not a transcription — the auth groups

**Was: `accounts/0004_user_role` and `accounts/0005_sharing_member`.** Also not on the todo's list.

Both seeded `django.contrib.auth` groups mirroring the role column — four of them, named by the
literals behind `ROLE_GROUP_NAMES` in `accounts/roles.py`, written out rather than imported for the
reason in section 1. They exist so that a staff member opening *Authentication and Authorisation*
finds the roles waiting for the model permissions the later apps would bring.

**C28 retired the role column, so these groups mirrored nothing.** Two options were open — drop
them, or keep them as the Django-admin-side view reseeded from the new relationships, which would
have meant deciding what a group means when one person holds three.

**Decided: dropped, with `ROLE_GROUP_NAMES` and the mirroring in `User.save`.** The lighter option,
and consistent with C29: the Django admin's audience is a handful of staff gated by `is_staff`, and
groups mirroring member-facing roles were never what let them in. Nothing is seeded. Model
permissions, when they arrive, hang off the relationship tables the way platform actions now do.

### 3.4 Obsolete — the superuser backfill

**Was: `accounts/0004`.** A one-time `User.objects.filter(is_superuser=True).update(role='admin')`,
described in the file as a reading of an existing database rather than a rule: the accounts that
bootstrapped the deployment are its club administrators.

**Do not recreate.** C29 makes `is_staff` the UC tier outright, and C28 removes the column this
wrote to. The relationship it was approximating is now explicit.

### 3.5 Nothing to keep

- **`accounts/0008_identity_number_disclosure`** — named on the todo's list, and it is plain
  generated `CreateModel` output with no docstring and no data operation. The model says everything.
- **`accounts/0007_portable_uniqueness_keys`** and **`payments/0002_portable_live_subscription_index`**
  — also named on the list. Their *rules* are in the models and their *reasoning* is in
  `backend.md` section 8.2 and in section 1 above. The backfills are moot against an empty database.
- **`accounts/0003_mobile_unique`**, **`0006_member_avatar`**, **`0002_member_registration`**, and
  every remaining `0001_initial` — generated, or generated plus a refusal check that has nothing to
  check. Nothing beyond the models.

---

## 4. The rebuild checklist

In order, once the new models exist:

1. `makemigrations` once per app, and read the output rather than trusting it.
2. Re-add the club document seed — 3.1.
3. Re-add the serial counter seed, last in its migration — 3.2.
4. Act on the group decision — 3.3.
5. Confirm the four derived-column rules in section 2 came through with both their unique index and
   their check constraint, in the same migration.
6. `manage.py check --deploy`, and run the suite on both databases per `backend.md` section 8.6.

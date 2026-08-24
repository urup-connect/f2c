# Sign-up

Three screens in sequence: the age gate, the member details form, and a confirmation. A completed
sign-up creates a member who cannot sign in until their membership is paid for.

## 1. Executive summary

Sign-up now stores what it collects. That reverses what this document used to say, and it is still
the most important fact in it.

A completed submission creates a `User` at status **Pending payment**, with their three club
document agreements, in one transaction. `POST /api/members/register` is the write; `app/membership`
owns it. The account cannot sign in: Django derives `is_active` from `status`, a check constraint
holds the two together in SQL, and every sign-in route resolves an address through
`User.objects.active_by_email`. There is no path by which registering produces an account that can
log in. What moves an account from Pending payment to Active is a payment, and **the payment gateway
is now built** — `app/payments` opens a subscription in the same transaction as the member, hands
them to Payfast, and activates the account when Payfast's server-to-server notification arrives. A
member of staff in the admin remains the route for somebody who paid another way. See
[payments.md](payments.md).

**That reverses part of one rule stated below, and the reversal is deliberate.** A duplicate
submission — an address, identity number or mobile already on file — used to be answered *identically*
to a new registration, so the form could not be used to ask whether a named person is a member here.
A new member is now redirected to Payfast and a duplicate cannot be, because there is no subscription
to pay for. Everything else about the answer is still identical, nothing is still written, and the
outstanding payment link is emailed to the address rather than returned. What that discloses, what it
does not, and the alternative that was declined are in [payments.md](payments.md) section 4 and its
risk 1. Risks 11, 15 and 16 below record the change.

The club documents live in Django. Their files, versions and wording are published by staff in the
admin and read at render time, and the consent ledger that records who agreed to which revision is
now written at sign-up rather than merely existing. See section 5.

**One thing this document used to make a condition of storing anything is still outstanding.** There
was no data layer, no agreed retention period and no published privacy notice, and the position taken
here was that an identity number may not be stored before all three exist. The data layer now exists
and the number is stored — encrypted with AES-256-GCM, reachable only through a blind index, never
returned over the wire. The retention period and the published privacy notice are not done. That is a
decision recorded, not a gap overlooked: see section 10, risk 1.

The rules themselves are the substance of the feature. Six fields, three agreements, and a
recurring theme: **a form that argues with its owner is a defect before it is anything else.**

## 2. The three screens

| Screen | Route | Guard |
| --- | --- | --- |
| Entry | `/join` | None. Discards any age pass and sends the visitor to the gate. |
| Age check | `/age-check` | None. Public. |
| Member details | `/signup` | Age pass required, re-validated on every request |
| Confirmation | `/signup?submitted=1` | Same |
| Unavailable | `/signup?unavailable=1` | Same |

The gate is enforced on `/signup` rather than on the landing page's buttons. One guard, so a
bookmark, a shared link or any entry point added later is gated without anyone having to remember to
point it at the check.

The unavailable screen is where a submission lands that passed every rule and could not be written:
Django unreachable, or a required club document with no revision in force. It is the same screen a
visitor sees when the documents cannot be read at render time, deliberately — in both cases nothing
was stored, and there is nothing they can do about it.

### Always the gate, coming from the landing page

That guard admits anyone still holding a valid pass, which is right for a bookmark and wrong for the
landing page: a visitor who steps back out and starts again would re-enter the member details form
against a date of birth they can neither see nor change. Coming from the landing page is a decision
to begin, not a resumption.

So the landing page's two Sign Up buttons point at `/join`, which discards the pass and sends the
visitor to a gate with no query string on it — no earlier answer, and no earlier refusal still on the
screen. `/signup`'s guard is unchanged; `/join` is an additional entry point, not a replacement for
it.

It is a Route Handler because a cookie cannot be cleared while a Server Component renders, and it
carries no route segment config: reading the cookie store is runtime data, so the redirect is never
prerendered and never answered from a cache. A cached redirect clears nobody's cookie.

Nothing else needed clearing. A previous *completed* attempt leaves a member record, and a second
submission of it is answered exactly as the first with nothing written — see section 6 on duplicates
— so the pass is the only thing an abandoned attempt leaves behind on the server. What the browser
itself restores into a form on back-navigation is left alone, so ordinary autofill still helps a
member who wants it.

## 3. The age gate

### The rule

Eighteen years, and it is **calendar arithmetic, not milliseconds**.

Adding eighteen years to a `Date` invites a time zone, an hour that does not exist across a clock
change, and a 29 February that silently becomes 1 March in a different place from where it was
meant. Comparing `(year + 18, month, day)` part by part has none of that.

"Today" is South African Standard Time, UTC+2 all year — the country observes no daylight saving. It
is derived through `Intl.DateTimeFormat` with an explicit zone rather than from the server's clock.

The current instant is always an argument, never read from inside the function. A date boundary is
then a test case rather than something that misbehaves only at midnight in production.

### The refusals

Ordered so the visitor is told the most useful thing first: what is missing, then what is not a
number, then what is not a date, then what is wrong with the date itself.

| Reason | Meaning |
| --- | --- |
| `incomplete` | A field is blank |
| `not-a-number` | Something other than one to four digits |
| `not-a-real-date` | 31 February, month 13, a two-digit year |
| `in-the-future` | Born after today |
| `implausible` | More than 120 years ago — a mistyped year, not a life |
| `under-age` | The actual rule |

A four-digit year is required, so a visitor typing `94` is corrected rather than aged out.

The refusal travels back to the gate as a **reason code in the query string, never the date**. A
redirect can only carry a URL, and a URL is written to every access log on the way. The code is
narrowed from an arbitrary string on the way back in, so a hand-typed or stale code shows the plain
form rather than a blank error.

### 29 February

A 29 February birthday has no eighteenth birthday in a common year. Comparing parts places it on 1
March, so the visitor waits one more day. That is the conservative side of a legal convention this
code should not be inventing.

### The pass

The gate's result travels to `/signup` in `cc_age_pass`: `httpOnly`, `SameSite=Lax`, thirty minutes,
version-prefixed so a changed shape is refused rather than misread.

It is **unsigned**, deliberately. A signature would stop a visitor forging a date they could equally
have typed into the gate, which is no protection at all. What matters is that the eighteen-year rule
is applied again on every read — and it is. A malformed, wrong-version, future-dated, expired or
under-age value reads as no pass and sends the visitor back to the gate.

The pass is read again inside the submit action, not trusted from the page. A submission arrives as
an HTTP request like any other, so the date of birth the identity number is checked against has to
come from the cookie the server can verify, never from the form.

The date of birth is never displayed on `/signup` and nothing offers to change it. It reaches the
form as a prop only because the browser-side identity check needs something to check against.

## 4. The member details

Six fields the visitor types. Each has a module of its own in `lib/`, and each returns a discriminated
result rather than throwing.

### 4.1 Names — `person-name.ts`

The interesting part of this rule is **what it refuses to refuse.** It does not require two names, a
vowel, a capital letter, more than one character, or the Latin alphabet. Every one of those
conventions, applied to South African names, rejects people who exist.

What it does refuse is a value that is not a name at all: digits, markup, an email address, an emoji,
or punctuation with no letter anywhere in it.

Both apostrophes are permitted — a keyboard produces `'` and a word processor silently produces `’`,
and a member should not have to know which one they typed.

Length is measured after normalising, so three spaces a visitor did not mean to type cannot push an
otherwise acceptable name over the 70-character limit. Characters are checked before length, because
*that is not a name* is the more useful complaint about a long string full of digits.

### 4.2 Email — `email-address.ts`

Deliberately not RFC 5322. That grammar admits quoted local parts, comments and bracketed IP
literals, none of which a member is going to type and all of which widen the surface for no benefit.

What this catches is a typo. What it guarantees is one normalised stored form — lower-cased whole,
local part included, for the same reason the backend does it: one address must have exactly one
stored form or the same person becomes two members.

Nothing here proves an address can receive mail. Only sending to it does, which is what the emailed
sign-in code will do.

### 4.3 Identity number — `sa-id-number.ts`

Thirteen digits, Luhn-checked, and cross-checked against the date of birth from the age pass.

**Two parts of the number are deliberately not read.** The sequence digits encode sex, and digit 12
is a historical race classifier. Deriving either would put the member record under POPIA section 26
and its narrower processing grounds for no product benefit at all. The result carries the thirteen
digits and nothing else, and a test asserts that.

The date of birth is always an argument, never parsed out of the number. Six digits carry a two-digit
year, so `900315` is 1990 or 1890 and the number does not say which. Guessing a century is a rule
about who may join, dressed up as parsing — and the age gate has already validated a four-digit date,
so the check compares against that instead.

Note this differs from the backend, which does resolve the century (`common/validators.py`), because
neither staff capturing a document nor the registration endpoint has an age pass to compare against.
The endpoint applies the eighteen-year rule to the date it resolves, using the same part-by-part
calendar comparison as the gate (`common.validators.is_at_least`), so a submission that bypasses the
frontend entirely is still refused.

### 4.4 Mobile number — `sa-mobile-number.ts`

Email is how a member signs in, so this is a contact number rather than a credential. It exists to
be reachable, which is why the rule excludes the ranges that cannot reach a person: `080`, `086`,
`087`, `088`, `089` — toll-free, share-call and VoIP.

One stored form, `+27` and nine digits, so the same handset cannot become two members by being
written with different punctuation.

The range rule is **deliberately permissive**: anything starting 6, 7 or 8, less those service
ranges. An allow-list of every allocated prefix would be more precise today and wrong within a year,
and its failure mode is refusing a real member's real number — worse than accepting one that turns
out not to be a handset.

A slash is not accepted as a separator. `082/123/4567` is usually two numbers, and guessing which one
is meant is worse than asking.

### 4.5 Nickname — `nickname.ts`

Three to twenty characters, **ASCII only** — and unlike the name fields, that restriction is the
point.

A nickname is the one value on the member record that is an identity claim against other members. A
Cyrillic "а" inside a name that reads as an existing member's is impersonation, and defending against
that properly means folding confusable characters across the whole of Unicode. Restricting the
alphabet removes the entire class of problem instead.

Uniqueness is decided on the lower-cased form, so `Grower` and `grower` cannot both exist, while the
capitalisation the member chose is what other members see.

Reserved names cover club and staff roles (`admin`, `support`, `official`, `security`) and the
product's own route names. The second group matters because a member called `verify`, appearing
inside a sentence about verifying something, is a phishing message that writes itself.

## 5. The club document agreements

Three documents, each with its own checkbox: the club rules, the annexures, and the constitution.

They are composed alongside the six details rather than through a mechanism of their own, so refusal
ordering, the one-message-per-field rule, the error summary and the no-JavaScript path all cover them
without a second implementation.

**Django owns the documents.** The file, the version and the wording used to be constants in
`frontend/lib/club-documents.ts`. They are now rows: `ClubDocument` is a document's identity,
`DocumentVersion` is one revision of it, and `DocumentConsent` is one member's agreement to one
revision. Staff upload a PDF in the Django admin, publish it, and the next member to open `/signup`
reads that revision. Revising a document no longer needs a deployment — which is the point, because a
club that amends its constitution should not have to ship a frontend to say so. See
`documents/models.py`.

Six decisions are worth recording:

**The revision travels with the agreement.** `ClubDocumentConsent` carries `{ document, version }`,
and the stored row points at a `DocumentVersion` rather than copying a number. Looking the version up
later answers what the document says *today*, not what the member read.

**A published revision is immutable, and that is the audit trail.** `DocumentVersion.save` refuses
a change to the file, the label or the wording once `effective_from` is set, and `delete` refuses
outright. Updating a document means publishing a new revision. Only `change_note` and
`requires_reacceptance` stay editable, because whether a change was material is a judgement sometimes
made the morning after.

**Two digests are copied onto every agreement, not joined from the revision.** A join tells you what
the revision says now; the copy tells you what the member agreed to. A disagreement between the two
is the tamper signal, and the admin surfaces it rather than assuming it away.

**A material change asks again; a typo fix does not.** `requires_reacceptance` on the revision
decides. `documents.services.outstanding_for` reads it, so a member who agreed to v1 is asked about
v3 and never recorded against v2 — correct, because they never read v2, and the reason the ledger is
keyed on the revision rather than on the document.

**The revisions are keyed, not ordered.** The API returns a list; the frontend narrows it into a
record keyed by document id. A checkbox saying *the constitution* that opens the annexures is not a
consent.

**Only `yes` counts.** An unticked checkbox is not posted at all, so an absent field and an empty one
mean the same thing and both are refused. Anything else — `on`, `true`, a padded value — is refused
rather than interpreted: no browser of ours sends it, so accepting it would only mean accepting an
agreement nobody made.

### Reading them, and failing closed

`GET /api/documents/current` is unauthenticated, because sign-up happens before an account exists. It
returns every required document at the revision in force, or **503** — never a partial list. A form
rendering two of three documents collects an agreement that is incomplete in a way nobody can see,
including the club later in a dispute. The frontend refuses a partial body again rather than trusting
that Django did, and `/signup` renders `DocumentsUnavailable` instead of the form.

An id the frontend does not know is ignored rather than refused, so a fourth document published in the
admin does not take sign-up down until a deploy catches up. It cannot be shown or agreed to, which is
the safe half of that trade.

### A revision published mid-form

Every checkbox posts a hidden `version-<document>` field carrying the revision it was rendered
against. The server action re-reads what is in force, uncached, and refuses a mismatch as
`consent-superseded` rather than recording the tick against the newer text — a tick beside v1's
wording is not an agreement to v2. Django's `resolve_submitted` refuses it a second time, because a
server action is an HTTP request like any other. The hidden field is not a security control and is
not treated as one: a forged value is refused rather than believed.

### Where the file lives

The admin's upload goes straight to the Azure Blob Storage container the CDN fronts, through
`django-storages`. The version is part of the blob name — `documents/<document>/<version>/<file>` —
so publishing a revision writes a new blob, never an overwrite of the one members have already
agreed to, and no CDN cache ever needs purging. That is also what makes a one-year immutable
`Cache-Control` safe to send.

Where no container is configured, uploads fall back to `MEDIA_ROOT`. That is not a degraded mode to
apologise for: it is what lets the whole feature — upload, digest, publish, serve — be built and
tested with no cloud account at all, and the test suite pins it so a developer's credentials cannot
change what the suite does.

Two rules are enforced at startup rather than discovered later, both in `documents.storage`, which is
a pure function of an environment mapping so that every branch is testable without an Azure
subscription:

**`DJANGO_CDN_BASE_URL` must be https outside local development.** A document fetched over plain
http is a document anything on the network path can rewrite, and these are the documents a member is
agreeing to.

**Its path must match the container name.** An Azure blob URL always carries the container as its
first path segment, and only the host is replaced. So `https://qa-static.urup.com/consumer-collective`
with a container of `consumer-collective` is the same address, and a base naming anything else is an
address that does not exist. The only other symptom is every document link 404ing after a deploy,
which is why it is a startup failure instead.

Credentials are looked for in one order — a connection string, then an account key or SAS token, then
a managed identity. The identity is what App Service should use and it is last on purpose: an
explicitly configured secret must never be silently ignored in favour of an ambient one. URLs are
unsigned, because a SAS token in a link that goes into a public page is a link that expires.

### What was given up

The sentence a member ticks now comes from the API, so the plain-language compliance checks in
`lib/copy-compliance.ts` no longer read it: `ALL_MEMBER_DETAILS_COPY` covers the short label and the
link text, and the agreement wording is owned by staff in the admin. That is a real loss of coverage,
accepted because the alternative is worse — two copies of the wording, one of them the record of what
a member asserted, drifting apart with nothing to notice.

## 6. What is stored, and what is never said

The accepted path in `signup/actions.ts` calls `registerMember`, which posts `outcome.details` to
`POST /api/members/register`. That is the only place an identity number crosses a process boundary,
and it is server-to-server: the call is in a `server-only` module so it cannot reach a browser
bundle.

### The record

One `User` row at **Pending payment**, and one `DocumentConsent` per club document, written together
or not at all.

| Value | Stored as |
| --- | --- |
| First and last name | Whitespace collapsed, as given |
| Nickname | As typed, unique case-insensitively |
| Email address | Lower-cased whole, unique |
| Mobile number | `+27` and nine digits, unique |
| Identity number | AES-256-GCM ciphertext, plus a unique blind index |
| Date of birth | Read off the identity document, never retyped |
| Agreements | One row per revision, with the revision's two digests copied onto it |

Four of those are decisions rather than mechanics.

**Three values identify a membership, and all three are unique: the email address, the identity
number, and the mobile number.** The club's rule is one handset, one member. It is not a security
control — members sign in with an emailed code or a passkey, never with a phone number — it is who
may hold a membership, and it is enforced in the database rather than only in the registration
service, because a queryset `.update()`, a data migration and a member of staff in the admin do not
go through that service.

The cost is explicit and accepted: **a member who has no phone of their own cannot give a partner's
or a parent's.** They are refused, and — because a duplicate is never disclosed — refused with a
confirmation screen rather than an explanation. See section 10, risk 14.

The column is normalised to `+27` and nine digits before it is written, which is what makes the
constraint mean anything: `082 123 4567` and `+27821234567` are one handset, and a unique index over
the raw text a member typed would let every other spelling through.

**The nickname is unique on `Lower('nickname')`, not on a stored key.** A denormalised column is one
more thing that can drift from the value it derives from, and `is_active` is the only denormalisation
the member record can justify.

Blank values are excluded from both the nickname and the mobile constraint: staff have neither, and
erasure blanks both fields, so without the exclusion the second erased member would be refused by the
database.

**Two of the three unique constraints need a hand-written check in the admin forms.** `email` is
`unique=True` on the column, so `ModelForm` catches a clash unaided. The identity number is unique on
a blind index Django knows nothing about. The mobile number and the nickname are unique under
*conditional* constraints, and `ModelForm` validation does not reach those — so without
`accounts.forms.ContactClashMixin` a member of staff making an ordinary mistake in the admin would
get a 500 instead of a sentence beside the field. `ContactClashTests` is what holds that in place.

**The date of birth is taken from the identity number, and is not marked verified.**
`date_of_birth_verified_at` stays null. A number that passes its check digit is a number that is not
a typo; nobody has looked at a document. Recording a self-service submission as verified would make
that field mean nothing, and it is the field the club would rely on later. This is why registration
calls `user.id_number = …` rather than `capture_sa_id_number`, which would stamp it.

**Every field is validated again in Django.** The endpoint is unauthenticated and reachable without
going through the frontend at all, so the browser's rules and the server action's rules are not rules
the database is protected by. `common.validators` holds the Python versions and they are deliberately
the *floor*: where the frontend is narrower, the frontend refuses first and a member never meets these
messages. A test asserts the floor is not narrower than the ceiling for the name rule, which is the
one where being too strict would refuse real people.

### Duplicates are not disclosed

An email address, an identity number **or** a mobile number already on file returns **exactly** what
a successful registration returns, and writes nothing. The alternative turns the form into a way to
ask whether a named person, a named identity number or a named phone belongs to a member here.

The three answer *identically*, and that sameness is the property under test. If any key answered
differently from the others, the form would become a way to ask which of the three a given value
matched.

A nickname collision *is* disclosed, because a nickname is a claim against other members, the member
has to choose another one, and knowing a nickname is spoken for reveals nothing about who holds it.

The duplicate check runs **before** the nickname check, and the order is load-bearing. A member who
submits the form twice — a double click, a back button, a retried request — holds their own nickname
by then, and telling them it is taken would be both confusing and untrue. The consequence to be aware
of when reading the tests: a nickname collision is only ever reached by somebody whose address,
identity number and handset are all new, so every test about a taken nickname has to make all three
fresh or it silently tests the duplicate path instead.

The check in the service is the polite answer, not the enforcement. A race between two simultaneous
submissions is refused by the unique index, which is the only thing that can refuse it.

An erased member may register again: erasure nulls `email` and blanks both the mobile number and the
identity number, and `email_hash` is deliberately not unique. A *suspended* member is still a
duplicate on all three keys, and still holds their nickname, because suspension is reversible.

### What never travels

The identity number is never returned, never logged, and never put in a URL. The success response is
a status and a sentence and nothing else — `RegistrationOut` has two fields — because a server action
redirects afterwards, and a redirect carries only a URL. Refusals travel as reason codes in the query
string, the same codes the browser-side rules produce, so the form has one way of showing a refusal
rather than two. Tests assert the number is absent from the success body *and* from every refusal
body, which is where an error handler is most likely to have helpfully included the input.

**The ledger is now written at sign-up.** `documents.services.record_consents` is the write,
`DocumentConsent` is the table, and `membership.services.register_member` is what calls it — in the
same transaction as the member row, so there is no such thing as a member whose agreements were lost
or an agreement against a member who was not created. Each row is stamped `signup`, which is what
distinguishes it from the re-acceptance path and from a row a member of staff recorded.

## 7. Validation runs twice, and the server's answer counts

The same pure functions run in the browser and again in the server action. The browser copy is
there so a member finds out about a mistyped identity number before they submit; the server copy is
the one that decides.

Every refusal is collected rather than stopping at the first. A member with three things wrong should
be told three things once, not one thing three times.

A refusal redirects with **reason codes and nothing else** — no name, no address, no identity
number.

### 7.1 One field is checked against the club's records on the way out of it

The nickname, and only the nickname. Leaving the field asks
`POST /api/members/nickname/availability` whether the name is free, and the answer appears against
the field before the member reaches the end of the form.

It is the only field that may be asked about, and the reason is the reason a taken nickname is the
one collision this product discloses at all (section 6, *Duplicates are not disclosed*): a nickname
is a claim against other members, so saying one is spoken for reveals nothing about who holds it. An
address, a handset or an identity number is the opposite — a live answer about any of those turns
this form into a way to ask whether a named person is a member here, so **none of them has an
endpoint to ask**, and `MemberDetailsForm`'s `asksTheApiOnBlur` flag exists partly so that adding one
requires making this argument again.

Four decisions inside that:

- **On blur, not as it is typed.** A value being finished with is the only moment worth asking
  anyone else about it. Asking per keystroke sends a dozen half-written names to the API and answers
  each time about something already changed.
- **Only when the field's own rules accept it.** A malformed nickname has a refusal of its own and
  nothing anybody else can add. Nothing is sent, and no request is spent being told what the browser
  already knew.
- **Through this application, not to Django.** `/api/nickname/availability` is a route handler on the
  site's own origin. That keeps the API's address out of the browser bundle, keeps the wording of a
  failure in one place, and — the point — keeps the *cause* of a failure in a server log rather than
  in the browser's network panel. The handler re-writes the answer down to one boolean rather than
  passing Django's body through, so a field added to that response later cannot reach a browser
  without somebody deciding it should.
- **A POST, with the nickname in the body.** A query string is written to this application's access
  log, the browser's history, and any cache between the two. It is the mildest value this form
  collects and it is still not ours to scatter.

Django re-reads the same rule inside the transaction that writes (`register_member` raises
`NicknameTaken`), so **this check is a courtesy and never the protection**. A nickname free when the
field was left can be taken before the form is sent, and the write is the only place that can refuse
that.

The per-IP limit is `30/m`, looser than `register`'s `5/m` because a member tries a few names in one
sitting and joins once. What it bounds is harvesting the nickname list.

### 7.2 A definite answer is a refusal; a check that failed is not

A **taken** answer is rendered exactly like a rule's refusal — against the field, in the same
wording, and it stops the submission at `handleSubmit` rather than costing a round trip that would
lose everything typed. Two details:

- It does not reach the error summary until the submit. The summary takes focus when it appears,
  which is right after a submit and wrong two fields later: it would haul the caret out of whatever
  the member is typing.
- It is remembered as *the nickname it was about*, not as a boolean. A member who reads the refusal,
  types something else and clicks straight through gives the browser no time to ask again; refusing
  that submission would be refusing the wrong nickname, so it is allowed and the write decides.

A **failed** check is not an answer, and is deliberately not shaped like one. The API unreachable, a
500, a 429, a body that does not parse: nobody knows whether the nickname is free. The field is left
unmarked and valid, a `role="status"` notice says the check could not be made, and **the submission
is not blocked**. Failing closed here would cost somebody a membership to protect a nickname that
`/register` re-checks anyway.

### 7.3 How a fault on our side reaches the member

Two failures are now reportable without anything about the member travelling: the nickname check
(7.2) and a submission that passed every rule and could not be written (section 6).

Both work the same way. The failure mints an eight-character reference (`lib/error-reference.ts`),
the cause is logged against it **server-side** — in the route handler, or in the server action — and
only the reference travels back: to the field as part of the notice, or to `/signup?unavailable=1&ref=…`
in the query string. The screen says something failed, gives the member a handle on it, and says
nothing about which fault it was.

That split is the whole of it, and it holds in both directions:

| Reaches the member | Stays in the log |
| --- | --- |
| That the check or the submission could not be completed | Which fault it was: unreachable, 5xx, 429, an unparseable body, a document with no revision |
| An opaque reference, eight hex characters | The reference, beside the cause |
| That the reference says nothing about them (on the screen that replaces the form) | — |

- **The reference is derived from nothing.** Random, not a hash of the request, the time or the
  value: a reference computed from anything about the member is a value in a query string that can
  be walked backwards.
- **The nickname is not logged**, on any path, and neither is anything else the member typed. The one
  thing worth recording about a value — that Django refused as malformed a nickname the browser
  accepted, meaning the two rule sets have drifted — is logged as the fact that it happened.
- **The reference is read strictly where it is rendered.** `readErrorReference` accepts eight hex
  characters and drops everything else, so a hand-edited `?ref=` cannot put wording of somebody's
  choosing on the screen beside our own.
- **No reference without a log line behind it.** The documents-unavailable screen rendered on the way
  *in* carries none: nothing was attempted for that visitor, so there is nothing to look up. A
  browser that cannot reach this site at all gets the notice without a reference for the same reason.

What this deliberately does not do is name the cause on screen. A member who is told "the API
answered 503" has learned nothing they can act on and something about our deployment; the reference
is what turns "it broke" into something support can trace.

## 8. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | Personal information, an identity number included, is now stored with **no agreed retention period and no published privacy notice**. This document previously made both a condition of storing anything. Storing it was a product decision taken with the position stated; it is recorded here rather than resolved. | Open — needs a retention period and a published privacy notice |
| 2 | Nickname uniqueness is enforced case-insensitively by a database constraint and checked before the write, so the `unavailable` refusal now fires. | Closed |
| 3 | The mobile range rule accepts numbers that are not handsets. Chosen over refusing real members. | Accepted |
| 4 | The age pass is unsigned. Accepted, because the rule is re-applied on read. | Accepted |
| 5 | The frontend resolves no century from an identity number and the backend does. Two rules over one field, correct in both places for different reasons — but they must be read together, and a future change to one is easy to make in isolation. | Open — documented rather than unified |
| 6 | Sign-up writes one agreement per document, in the same transaction as the member. | Closed |
| 7 | Sign-up depends on Django being reachable to render at all. Where it is not, `/signup` shows *Joining is briefly unavailable* rather than a form. Chosen over rendering a form whose agreements cannot be read. | Accepted |
| 8 | The sentence a member ticks is no longer covered by the plain-language compliance checks: it comes from the API, and staff own it in the admin. | Accepted — see section 5, *What was given up* |
| 9 | Nothing verifies that the PDF at a revision's address still hashes to the digest recorded for it. The digest is stored and compared per agreement, and the admin flags a mismatch, but no job re-fetches the file to check. | Open — needs a periodic check |
| 10 | A document published in the admin with an id the frontend does not know is silently not shown. Django only refuses when a `required_at_signup` document has no revision, so a fourth document is invisible rather than blocking. | Accepted — deliberate, so a publish cannot take sign-up down |
| 11 | A registered member sits at Pending payment with nothing that can move them to Active: **the payment gateway is not built**. Until it is, only a member of staff in the admin can activate an account, and a member who registers can never sign in on their own. | **Closed.** `app/payments` activates an account on a Payfast notification — see [payments.md](payments.md). Two gaps remain, recorded there rather than here: nothing schedules the lapsing command (its risk 2) and no real email provider exists, so the emailed payment link reaches nobody (its risk 3) |
| 12 | The registration endpoint is unauthenticated and has no CSRF check. It cannot have a useful one: the caller is a Next.js server action, so there is no browser cookie to forge with and a token would be one this application issues to itself. A per-IP rate limit of 5/minute is the control instead, and it is the only thing bounding bulk creation of member rows. | Accepted — see `membership/throttles.py` |
| 13 | Four validation rules now exist twice, in TypeScript and in Python — names, email, mobile, nickname — joining the identity number at risk 5. Each pair is correct in both places for different reasons, but they must be read together, and a change to one is easy to make in isolation. | Open — documented rather than unified |
| 14 | The mobile number is a unique identity key, so a member with no phone of their own cannot give a partner's or a parent's. Because duplicates are never disclosed, they are refused with a confirmation screen and never learn why. There is no route for staff to make an exception short of editing the other account. | Accepted, by decision — the club's rule is one handset, one member |
| 15 | The frontend has no refusal code for a duplicate, by design, so a visitor whose address, identity number or handset is already held sees the same confirmation screen as a new member. Support has no way to tell the two apart from the member's description alone. | Accepted — the alternative discloses membership. Still true of the *screen a duplicate lands on*, and it is now the screen a new member does **not** land on: see risk 16 |
| 16 | A new registration is redirected to Payfast and a duplicate is not, so whoever submitted the form can tell that an address may already be on file. This narrows risk 15 and reverses part of the non-disclosure rule in section 6. | Accepted, and bounded — one response field differs, nothing is confirmed, and the three duplicate keys still answer identically to each other. Recorded in full in [payments.md](payments.md) section 4 and its risk 1, where the declined alternative is also set out |
| 16 | `POST /api/members/nickname/availability` is an unauthenticated endpoint that answers one question about other members' records. The disclosure is bounded by what the answer contains — one boolean about a name the caller had to type — and by a 30/minute per-IP limit. A harvester with several addresses can still enumerate whether specific nicknames are taken. | Accepted — the same disclosure `register` already makes, and see section 7.1 |
| 17 | The nickname check fails open: a member who submits while it is failing is refused by `register` instead, and that refusal arrives as a redirect, which loses every value they typed. So a failing check turns a taken nickname from an inline message into a re-typed form. | Accepted — the alternative traps a member in a form over a transient fault |
| 18 | The error reference is only as useful as the log it points at. Nothing yet ships those `console.error` lines anywhere retained, and there is no support runbook that says how to look one up. Until there is, a member quoting a reference cannot be helped by it. | Open — needs log retention and a runbook |

# Frontend design

Next.js 16.3.2 on React 19.2.8, App Router, TypeScript throughout. Every page a member sees is
rendered here. The application holds no database and no session store of its own: state that
outlives a request lives in Django, and the one exception is documented in section 5.

**There are now two applications.** Sections 1 to 10 describe the club, `frontend/club`, which is
where every convention in this document was established. Section 11 describes the store,
`frontend/market`, in terms of where it follows those conventions and where it departs from them —
which is the useful way to read it, because the departures are all consequences of the identity split
in `verticals.md` rather than choices made twice.

## 1. Executive summary

The frontend is organised in three layers, and the layering is the design. Pure logic modules hold
every rule and know nothing about React. Components render, take props and emit events, and fetch
nothing. Routes compose components, read configuration and cookies, and are the only layer that
knows the application is on a network.

The consequence that matters commercially is test cost. 1,305 unit tests run in about sixty seconds
with no browser, no server and no database, because the rules they exercise are pure functions and
the components they render take their data as arguments. A rule change is a change to one module
and its test file.

The consequence that matters operationally is that the public product is finished and the member
product is a shell. The landing page, age gate and sign-up form are complete and reachable, and so
now are sign-in, the three role home pages and passkey management. What sits behind the gate is
mostly a catalogue of screens that do not exist yet, because the models they act on do not exist
yet. Section 9 sets out exactly what that means.

## 2. Rendering and the split with Django

Django serves JSON. Next.js renders every page. The alternative — Django templates for some pages
and Next.js for others — was rejected because it puts two rendering stacks, two styling systems and
two notions of "who is signed in" into one product.

Authentication is Django's own session cookie. Signing in sets an `HttpOnly` `sessionid`; the
browser returns it on every API call; unsafe methods additionally carry a CSRF token. A server
component has no browser to attach cookies for it, so the incoming request's cookies are forwarded
by hand in `lib/server-api.ts`. Without that forwarding every server-rendered page would render as
signed out.

Two modules exist for reaching the API, and the split is enforced by imports rather than by
convention:

| Module | Runs | Notes |
| --- | --- | --- |
| `lib/api.ts` | Browser and server | Safe to import anywhere. Handles CSRF and `credentials: include`. |
| `lib/server-api.ts` | Server only | Marked `server-only`. Forwards cookies, sets `cache: 'no-store'`. |

`lib/server-api.ts` cannot be imported into a client bundle, because `next/headers` cannot be. The
`server-only` marker turns that into a build error with a clear message rather than a confusing
module resolution failure.

Session-dependent responses are fetched `no-store`. Caching a response that depends on who asked
for it is the one caching mistake in this architecture that leaks another member's data.

## 3. Module layers

```
app/                    Routes. Compose, read cookies and configuration, redirect.
components/<Domain>/    Presentation. Props in, events out. No fetching, no route awareness.
lib/                    Rules and content. Pure functions and frozen data. No React.
```

`lib/` is where the product's actual logic lives, and it is written as pure functions that take
their inputs as arguments and never read ambient state. The clearest example is the age check: the
current instant is always a parameter, never `new Date()` read from inside. A date boundary is then
a test case rather than something that misbehaves only at midnight in production.

Components are built and tested in isolation before being wired into a route. Each has its test
colocated as `<Name>.test.tsx`. `components/README.md` records the rule.

> **Correction to note:** `components/README.md` describes the path as
> `src/components/<Domain>/<Name>.tsx`. There is no `src/` directory in this project; components are
> at `components/<Domain>/<Name>.tsx`. The rule is right, the path prefix is stale.

## 4. Routes

| Route | Rendering | Purpose |
| --- | --- | --- |
| `/` | Server | The public landing page. The only indexable route. |
| `/join` | Route Handler | The landing page's way in. Discards any age pass, then redirects to `/age-check`. See `sign-up.md` section 2. |
| `/age-check` | Server | The eighteen-year gate in front of joining. |
| `/signup` | Server | The details a joining member gives. Age-gated. |
| `/login` | Server | Sign-in. Renders `Auth/SignInForm`. Sends an already-signed-in visitor to their own area. |
| `/signup/paid` | Server | The confirmation a paid registration lands on. |
| `/signup/cancelled` | Server | The confirmation an abandoned checkout lands on. |
| `/pay` | Server | The outstanding-payment screen for a member the session already identifies. |
| `/pay/[token]` | Server | The same screen reached from the emailed link, for a member with no session. |
| `/blocked` | Server | What a suspended or revoked account is shown. Names their standing, and deliberately not the club's reasons — C32. |
| `/member` | Server | A member's home. Guarded. |
| `/cultivator` | Server | A cultivator's home. Guarded. |
| `/admin` | Server | An administrator's home. Guarded. |
| `/profile` | Server | The account's own record: name, nickname, mobile, and the avatar with its cropper. Guarded. |
| `/admin/members` | Server | The membership register. Behind `platform.disable_user`. |
| `/admin/members/[id]` | Server | One member: read, edit, suspend, reinstate, and the recorded disclosure of an identity number read in full. |
| `/admin/strains` | Server | The strain catalogue. Behind `platform.manage_strain_catalogue`. |
| `/admin/strains/new` | Server | Add a strain. |
| `/admin/strains/[id]` | Server | Edit or retire one. |
| `/admin/strains/terms` | Server | The aroma and effect vocabularies. |
| `/api/nickname/availability` | Route Handler | The sign-up form's nickname check, proxied to Django. See `sign-up.md` section 7. |
| `/robots.txt` | Dynamic | Read at request time, not build time. |
| `/sitemap.xml` | Dynamic | Read at request time, not build time. |

`/join`, `/age-check`, `/signup` and `/login` sit in an `(auth)` route group. A route group shapes the
layout without appearing in the URL, so the screens stay at their public paths while sharing one
frame. `/join` is in the group for filing rather than for the frame: a Route Handler renders no
layout.

`/join` needs no `robots` treatment of its own. `robots.txt` disallows everything but `/`, and the
route returns a redirect rather than a page.

`/api/nickname/availability` is the only route the browser calls with JavaScript, and the only one
that is not a page. It exists so that the one live check on the sign-up form goes through this
origin rather than straight to Django: the API's address stays out of the client bundle, the wording
of a failure is decided in one place, and the *cause* of a failure is logged server-side instead of
appearing in the browser's network panel. Nothing but the sign-up form calls it, and adding a second
such route should be argued for the same way — see `sign-up.md` section 7.1 on why the nickname is
the only field that may be asked about at all.

The `(auth)` layout owns the landmark and the centring and nothing else. It does not own the card:
sign-up needed a wider one, and a child cannot exceed its parent's maximum width, so each page
renders its own `AuthCard` at the width that screen needs.

### The club group, and where the gate is

`/member`, `/cultivator` and `/admin` sit in a `(club)` route group whose layout does two things:
it draws the signed-in shell, and it is the gate.

**Three routes rather than one `/dashboard` that branches.** The three areas answer to different
people and will diverge — a cultivator's screens are about stock, listings and the register, and
none of that is a variation on a member's plants. A route each means the divergence arrives as new
files rather than as a switch statement growing in the middle of an existing one. What the three
share today is one component, `Club/ClubHome`, because the difference between them turned out to be
two sentences: everything below the greeting is drawn from the account's `permissions`, so an
administrator's screen is the same component rendering a different catalogue.

**The gate is a Server Component, not the proxy.** `proxy.ts` runs first and can see the session
cookie, but seeing a cookie is not the same as having a session: an expired, forged or signed-out
cookie is still a string, and a gate that admits anyone holding one is a redirect dressed as a
guard. The club layout asks Django on every request, uncached. It is not the last line of defence
either — every endpoint authorises its own caller — it exists so a member is sent somewhere useful
instead of being shown an area full of refusals.

The layout checks the session; each page checks only the role, reading the same answer through a
request-scoped `cache()` in `lib/club-session.ts`, so one page render makes one call to
`/api/auth/me`. A member who types `/admin` is redirected to `/member` rather than refused: nothing
had rendered, and somewhere they can use beats an error page telling them off.

**How the layout knows where the visitor was going.** A layout is not told which route it wraps,
which is normally right. But an unauthenticated visitor has to reach `/login?next=…` so that signing
in returns them to where they were headed, and the layout cannot say where that was. `proxy.ts`
therefore sets the pathname as a **request** header on the way in. Nothing trusts the value: it
arrives from the client on every request, and `signInPath` runs it through the same check the form
applies to a `?next=` in the query string — a protocol-relative URL starts with a slash and still
leaves the site.

**What each home offers is read from `permissions`, never from `role`.** That is the API's own
instruction (`roles-and-permissions.md` section 12): a role-to-ability map in this bundle would be a
second copy of `accounts/roles.py` and would drift from the one the API enforces. `lib/club-navigation.ts`
holds the catalogue of destinations, each keyed to a `platform.*` codename, and a contract test reads
`app/core/accounts/roles.py` as text and refuses a codename Django does not grant — so a renamed action
cannot quietly empty a menu.

**Twenty-seven of the thirty destinations are marked `planned`** and render as inert text with a
"Not built yet" badge, because the screens they name do not exist. The three that are `ready` — the
strain catalogue, the member register and the account's own profile — carry an `href` and render as
links. A planned tile is never a link and never a disabled button: a control that looks operable and does nothing costs a member a click and a screen-reader
user considerably more, and an anchor to a route that answers 404 is worse than both.

### Server actions, not client state

Both forms submit to a server action (`age-check/actions.ts`, `signup/actions.ts`). Refusals
redirect back with a reason code in the query string rather than returning state to the client.
Three things follow, and all three were the point:

1. The outcome is identical with JavaScript and without it.
2. The page stays a Server Component with nothing to hold.
3. Only the reason travels in the URL — never the date of birth, never a name, never an identity
   number. A redirect can only carry a URL, and a URL is written to every access log on the way.

## 5. Configuration

Deployment configuration is read once, when `lib/site.ts` is first loaded, so a misconfigured
deployment fails on the way up rather than at whichever request first needed the value.

| Variable | Required | Rule |
| --- | --- | --- |
| `APP_ENV` | Yes | One of `local`, `qa`, `production`. Nothing else. |
| `SITE_URL` | Yes | Absolute origin, http or https, no path, no query, no fragment. |
| `CDN_BASE_URL` | Yes | Absolute URL, a path is allowed. Plain http refused outside `local`. Validated but no longer read. |
| `DJANGO_API_URL` | No | Internal address Next.js reaches Django on. Defaults to localhost:8000. |
| `DJANGO_API_PUBLIC_URL` | No | Public address the browser reaches Django on. Read at request time and rendered into the document; see `lib/api-address.ts`. |

Two details in that table are decisions rather than validation:

**Indexing is derived from `APP_ENV`, not from a flag of its own.** A boolean called something like
`ALLOW_INDEXING` can be set wrongly on the QA application, and the failure is invisible until QA
content appears in search results. Deriving it means the QA application cannot be made indexable
without claiming to be Production.

**`CDN_BASE_URL` refuses plain http outside local development.** What is served from there includes
the documents a member agrees to, and a document fetched over plain http is a document anything on
the network path can rewrite. `SITE_URL` carries no such restriction because it is not serving
agreements.

Note that **nothing in this application reads `CDN_BASE_URL` any more.** The club documents were the
first thing served from that host and they no longer come from configuration: Django owns their
addresses, because it owns their versions, and the same https rule now lives in
`DJANGO_CDN_BASE_URL`. The variable and its checks are kept for whatever is served from the host
next, and it is still required, so a deployment that drops it fails on the way up. See
`design/features/sign-up.md` section 5.

Every reader is a pure function taking an environment record, so the tests never mutate
`process.env` and never need a module reset between cases. The failure message names the offending
variable and says where to set it, because these failures happen in deployment rather than on a
developer's machine.

## 6. The one piece of client-visible state

There is no session and no database at sign-up time, so the age gate's result travels to the sign-up
screen in a cookie: `cc_age_pass`, `httpOnly`, `SameSite=Lax`, thirty minutes.

It is deliberately **unsigned**. A signature would stop a visitor forging a date they could equally
have typed into the gate, which is no protection at all. What matters instead is that the
eighteen-year rule is applied again on every read — and it is, inside `readAgePass`. A stale,
malformed, wrong-version, future-dated or expired value reads as no pass at all and sends the
visitor back to the gate.

`secure` follows the scheme the site is actually served on rather than the environment name. Marking
a cookie `Secure` on a plain-http local server means the browser never sends it back, which
presents as a broken gate and takes an afternoon to diagnose.

## 7. Search engine indexing

The landing page is the only route the product ever permits to be indexed, and no environment other
than Production permits any indexing at all. That is enforced three times over, deliberately:

1. **The root layout declares `robots: { index: false, follow: false }`.** Default deny, so a route
   added later is kept out of search results without anyone having to remember to exclude it. The
   landing page is the single override.
2. **`proxy.ts` sets `X-Robots-Tag: noindex, nofollow` outside Production.** A header rather than
   page metadata, because `export const metadata` is evaluated when a static route is built — so a
   build artefact promoted from QA to Production would carry the wrong value. Where a page directive
   and a header disagree, crawlers take the more restrictive.
3. **`robots.txt` and `sitemap.xml` are `force-dynamic`.** Read at request time, so one build
   artefact behaves correctly in both environments.

`proxy.ts`, not `middleware.ts`: the middleware convention is deprecated in Next.js 16 and renamed
to proxy.

## 8. Testing

| | |
| --- | --- |
| Runner | Vitest 4 with jsdom |
| Rendering | Testing Library (React 19) |
| Files | 69 test files, colocated beside what they test |
| Tests | 1,305 |
| Command | `npm test`, `npm run test:watch`, `npm run test:coverage` |

Aliases resolve through Vite's native `resolve.tsconfigPaths`, so the `@/*` mapping is declared once
in `tsconfig.json` rather than twice.

The suite supplies `APP_ENV`, `SITE_URL` and `CDN_BASE_URL` in the Vitest config rather than
depending on a developer's `.env.local`, because `lib/site.ts` validates configuration at import
and would otherwise fail to load at all.

Three kinds of test appear, and the third is the one worth knowing about:

- **Rule tests** against the pure modules in `lib/`. The bulk of the suite.
- **Component tests** rendering a component with props and asserting what a member can see and do.
- **Contract tests** that read source files as text. `app/globals.test.ts` parses `globals.css` for
  declared tokens, because jsdom does not run Tailwind and an `@theme` block is never resolved into
  computed styles at test time. `lib/brand.test.ts` walks `app/`, `components/` and `lib/` looking
  for references to assets that should no longer exist.

Contract tests of that kind are unusual and are worth defending: they catch the class of defect
where the code and its declared design have drifted, which no amount of rendering will surface.

## 9. What is not built

**Sign-in and the three home pages are built.** The three components that were written but unrouted
have been replaced rather than wired up as they stood — they predated the layered structure in
section 3, used `kebab-case.tsx` at the root of `components/`, and had no tests:

| Was | Is now |
| --- | --- |
| `components/login-form.tsx` | `components/Auth/SignInForm.tsx` + `SignInFeedback.tsx`, rules in `lib/sign-in.ts`, copy in `lib/sign-in-content.ts` |
| `components/passkey-manager.tsx` | `components/Account/PasskeyCard.tsx` + `PasskeyList.tsx`, rules in `lib/passkeys.ts` |
| `components/sign-out-button.tsx` | `components/Club/SignOutButton.tsx` |

Every new module has colocated tests, which closes risk 1.

**What is behind the sign-in is a shell, not a product.** Each home shows what the club actually
holds — the account's details, how the membership stands, and the passkeys on it — and then a
catalogue of what it intends to offer, almost all of it marked *Not built yet*. That is the honest
state: `roles-and-permissions.md` section 13 lists the models that do not exist, and the tiles name
the screens that will sit on top of them.

Three specific gaps behind the gate:

- **Two administration screens exist; the other seven do not.** The membership register at
  `/admin/members` and the strain catalogue at `/admin/strains` are built over
  `administration_api.py` and `strains/api.py`. The rest of the administrative catalogue — product
  types, club rules, cultivator management, the member holdings view (C14), reporting — has no
  endpoint behind it and is still done by hand in the Django admin by somebody holding `is_staff`.
  The administrator's home does not link to the Django admin, because that opens on `is_staff` and
  the two facts are independent, so such a link would work for some administrators and refuse others.
- **Nothing a cultivator does is on a screen.** `POST /api/stock/plants`, `/uploads` and
  `GET /template` are built and no page calls them, so stock is still loaded with
  `manage.py upload_plants`. The cultivator's home is entirely `planned` tiles.
- **Outstanding club documents are not surfaced.** `GET /api/documents/outstanding` exists and
  nothing calls it, so a member owing a re-acceptance is not asked for one.

**What is entered at sign-up is stored** — this section used to say it was not, and that has been
wrong since `club/membership` landed. `signup/actions.ts` posts to `POST /api/members/register`,
which writes the `User`, the `ClubMembership` at Pending payment and one `DocumentConsent` per club
document, together or not at all. See `features/sign-up.md` section 6 for the record it writes.

## 10. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | The authenticated components are untested and diverge from the component conventions. | Closed — rewritten to `Domain/PascalCase.tsx` with colocated tests and pure rules in `lib/`. See section 9 |
| 2 | `NEXT_PUBLIC_DJANGO_API_URL` was baked into the client bundle at build time, so one artefact could not serve two environments. | **Closed** — replaced by `DJANGO_API_PUBLIC_URL`, read per request and rendered into the document. Verified: one build served under two addresses without a rebuild. |
| 3 | The age pass is unsigned. Accepted, because the rule is re-applied on read and there is nothing to protect. Signing arrives free if an `AUTH_SECRET` is ever introduced. | Accepted |
| 4 | `.next/types/validator.ts` is generated build output that `tsconfig.json` includes. A stale copy referencing deleted routes breaks `npm run typecheck` with errors that point at no real source file. Cleared once; will recur after routes are renamed. | Open |
| 5 | The club suite is **1,974 tests in 107 files** and the store's is 353 in 23. Most of the runtime is jsdom environment setup. Tolerable now, worth watching as the member area is built. | Accepted |
| 6 | `app/api/nickname/availability/route.test.ts` asserts an eight-character random hex reference does not contain `"500"`, `"503"`, `"429"` or `"422"`. All four are valid hex, so the test fails on roughly one run in thirty. Predates this work. | Open — a one-line fix, not yet taken |
| 7 | `CDN_BASE_URL` is read while `/` is prerendered, so the club film's address is fixed at build time — as `SITE_URL` already is, through the root layout's `metadataBase`. A promoted artefact serves the film from the wrong host. Same class as risk 2. Making the one indexable page dynamic would cost more than it saves; the remedy is a build per environment. | Open |

---

## 11. The store application

`frontend/market`, the produce market storefront, filling the npm workspace slot
`frontend/package.json` has declared since Block 0.5. Same stack, same three layers, same testing
approach; **353 unit tests in 23 files**. It runs on port 3001 so both applications can run at once.

What follows is only what differs from sections 1 to 10. Everything not mentioned is the same.

### 11.1 What it is for, and what it therefore does not have

A store customer is a `User` with no row in `ClubMembership`, `StorefrontStaff` or
`ProducerMembership` — `verticals.md` section 6. Almost every difference below is that sentence
having consequences.

| The club | The store | Why |
| --- | --- | --- |
| Two gates: is this anybody, and is the club open to them | **One gate: is this anybody** | A customer has nothing to pay for and no membership to be behind on. `lib/session.ts` |
| Three homes, chosen by role | **One account area** | Every customer is the same kind of customer |
| Menu derived from the `platform.*` permission catalogue | **A fixed menu of two destinations** | A customer holds *no* codenames — `permissions_for` grants from a membership or an appointment, and a shopper has neither. A permission-derived menu would render empty for every customer the store has. `lib/navigation.ts` |
| Age gate, identity number, nickname, consents at sign-up | **Four fields: two names, an address, an optional mobile number** | POPIA minimisation. An identity number asked for because another storefront needs one is exactly what the principle refuses |
| One indexable route | **Two: `/` and `/legal`** | A store's public pages are meant to be found. `lib/seo.ts` |
| `APP_ENV`, `SITE_URL`, `CDN_BASE_URL` | **`APP_ENV`, `SITE_URL`** | Nothing in the store is served from the static host; a document's address comes from Django, which owns its revisions |
| `copy-compliance.ts` over all member-facing copy | **No compliance corpus** | Those are cannabis rules. A market that could not name a price would not be a market — `verticals.md` risk 6 |

The last row is enforced rather than merely intended: `lib/store-content.test.ts` flattens every fixed
string in the application and asserts that none of them names the club, its produce or its
vocabulary — with one deliberate exception, the sentence on the security screen explaining that
passkeys do not cross a registrable domain.

### 11.2 Routes

| Route | Rendering | Purpose |
| --- | --- | --- |
| `/` | Server, dynamic | The front door. Indexable. Says plainly that the store is not trading yet |
| `/legal` | Server, dynamic | Terms, privacy and data, from `GET /api/documents/published`. Indexable |
| `/sign-in` | Server | Identifier-first sign-in. Sends an already-signed-in visitor to `/account` |
| `/sign-up` | Server + server action | Create an account. See 11.4 |
| `/account` | Server | The signed-in home. Guarded |
| `/account/details` | Server | Name and mobile number. Guarded |
| `/account/security` | Server | Passkeys. Guarded |
| `/robots.txt`, `/sitemap.xml` | Dynamic | Read at request time, not build time |

`/sign-in` and `/sign-up` sit in an `(auth)` group; the three account routes sit in an `(account)`
group whose layout holds the session check. Both groups follow the club exactly, including the reason
the gate is in a layout and not in `proxy.ts`: a proxy sees a cookie, and a cookie is not a session.

There is **no route handler** in this application. The club has one, for the sign-up form's live
nickname check; the store's form asks Django nothing while it is being typed, so there is nothing to
proxy.

### 11.3 Where the store's own logic lives

| Concern | Module |
| --- | --- |
| The session gate, and the name to greet somebody by | `lib/session.ts` |
| Sign-in rules — safe `next`, the code, what a failure says | `lib/sign-in.ts` |
| Sign-up rules, the form reader, and the API's refusals narrowed | `lib/sign-up.ts` |
| The registration call, and the contract it is written against | `lib/sign-up-api.ts` |
| The details form's rules | `lib/profile.ts` |
| The three states of the legal index | `lib/documents.ts` |
| What is offered, and what is described but not built | `lib/navigation.ts` |
| The name, and the fact that the brand is a placeholder | `lib/brand.ts` |
| Design tokens | `app/globals.css` |

Four modules are **verbatim copies** of the club's, with their test suites: `env.ts`,
`person-name.ts`, `sa-mobile-number.ts` and `email-address.ts`. They are platform rules and belong in
`packages/`, and they are duplicated on purpose for the reason `frontend/README.md` records — the
seams are drawn once, against a second consumer, and drawing them file by file while writing that
consumer would mean drawing them from one side. Copying the tests with them is what makes a
divergence a failing test rather than a refusal only one storefront makes.

### 11.4 What is not built, and is not pretending to be

**Sign-up completes. The endpoint is built** — `app/core/accounts/registration.py` and
`registration_api.py`, mounted at `/customers`, with 53 tests. It creates a `User` and nothing else:
no `ClubMembership`, no `StorefrontStaff`, no `ProducerMembership`, and therefore no permission of
any kind. The contract `lib/sign-up-api.ts` was written against is the contract that shipped, so the
form, its rules, its refusals and its confirmation screen needed no change:

```
POST /api/customers/register        auth=None
  { first_name, last_name, email, mobile }        mobile optional
  200     -> accepted, and a six-digit sign-in code is emailed.
             The SAME answer, byte for byte, for an address already on file
  422     -> { "detail": ..., "fields": { "email": ["email-malformed"] } }
  429     -> the per-IP limit, 5/m, which stands in for the CSRF check an
             unauthenticated server-to-server endpoint cannot have
  503     -> either the store has published a document that must be agreed to
             and this contract carries no `consents` field, or the sign-in code
             could not be sent
```

Three decisions in that shape are worth stating, because none of them is the obvious reading.

**A duplicate address is emailed a sign-in code too.** The confirmation screen sends everybody to the
sign-in screen to enter one, so a customer who had forgotten their account would otherwise be told to
wait for something that never arrives. It reaches the mailbox rather than whoever filled in the form
— the same channel, and the same reasoning, that lets the club email an outstanding payment link to a
duplicate. A duplicate matched on the *handset* under a different address is sent nothing at all,
because emailing the typed address would tell it about somebody else's account. The response body is
identical in every case.

**Publishing a market document that must be agreed to stops registration dead**, with a 503, rather
than creating customers recorded as having agreed to nothing — `registration.ConsentRequired`.
Publishing one is a single action in the Django admin taken by whoever writes the terms, not by
whoever writes the endpoint, and without the guard it would begin quietly. The storefront it checks is
**named** rather than read from the request host: the club's own three documents demand agreement at
registration, so a host-scoped check would refuse the store on every unmapped host, which is every
development machine.

**A mail outage answers 503 and keeps the account.** Found by running the endpoint against a mail
server that was not answering. It is the one failure mode this endpoint has that no other on the API
shares: a failed send during sign-in is retryable and idempotent, while a failed send here follows a
row that has already committed — so letting it through would answer 500 to somebody whose account
exists, and every retry would repeat it. The account is not rolled back to match, because it is a
good row and the failure is a mail server.

The remaining stale note is the `unavailable` branch: a 404 no longer means "not built", it means the
API could not route the request. The branch stays as a diagnostic distinct from a 500, and its copy
now says the fault is ours rather than promising a future opening.

The success answer is deliberately identical for a fresh address and one already registered, which is
the same disclosure decision `RegistrationOut` records on the Django side and the same one that makes
`/api/auth/login/start` answer `otp` for an address with no account. A sign-up screen that
distinguished the two would be a way of asking whether somebody shops here.

Also absent, each for a stated reason:

- **No catalogue, cart, order, delivery or produce type.** That is the market vertical —
  `todo.md` Block B — and it is backend work first.
- **No documents.** The store's terms, privacy notice and data policy are not written. `/legal` says
  so, and distinguishes "nothing published" from "could not be read": telling a shopper the store has
  no privacy notice on a day when it has one and the network was down is an untrue statement about a
  legal obligation.
- **No avatar.** The three endpoints work for any account; what is missing is a reason, since a
  shopper's photograph is shown to nobody. Adding it is one API module, a cropper and one card.
- **No administration area.** `StorefrontStaff` carries the market appointment and there is no
  `platform.*` codename for it, so there is deliberately no tile: one gated on a codename that does
  not exist would be gated on `undefined`, and showing every shopper a locked door is worse than
  showing them nothing. C29.

### 11.5 The brand is a placeholder, and says so

The club's tokens come from a guidelines deck and are documented in `features/brand.md`. The store has
no deck. What exists is a name — *Farm to Consumer*, shortened to *F2C*, which is what the platform's
own package and its `EMAIL_F2C_*` configuration already call this storefront — and the club's token
*structure* filled with a neutral palette: the same semantic aliases, the same two type roles, the
same three radii, so ratified colour and type arrive as a change to `app/globals.css` and to nothing
else.

Two consequences are worth recording because they are cheap to keep and expensive to retrofit.
Nothing outside `lib/brand.ts` spells the name, so a rename is one file. And there is no logo asset:
the wordmark is set in the display face, so there is nothing to commission now and nothing to remove
later.

### 11.6 A local-development trap

`GET /api/documents/published` is unauthenticated, so Django resolves the storefront from the host the
request arrived on. Locally both applications call the same Django on `localhost:8000`, which is not
in `DJANGO_STOREFRONT_HOSTS`, so it falls back to `DJANGO_DEFAULT_STOREFRONT` — the club. Working on
`/legal` means setting that variable to `market`, or expecting the club's documents to appear on the
store. In a deployment the two hosts differ and the mapping does the work.

This is not a fault in either application, and it is recorded here because the symptom — the club's
rules on the store's legal page — reads like a scoping bug in the frontend when it is configuration.

### 11.7 Risks

| # | Risk | Status |
| --- | --- | --- |
| 11.1 | The registration endpoint does not exist, so the store cannot take a single account. Everything in front of it is built and tested; the store is one backend endpoint away from usable, and not usable at all until then. | **Closed.** `POST /api/customers/register` is built — see 11.4. The frontend contract needed no change, which is what the risk was really about |
| 11.2 | The palette and typefaces are unratified placeholders. A ratified brand may cost more than a token swap if it brings a different layout language with it. | Accepted — the structure is shared with the club, so the swap is one file |
| 11.3 | Four modules are duplicated from the club with their tests. A rule fixed in one and not the other diverges silently between storefronts. | Accepted, with the duplicated tests as the tripwire. Closes when `packages/` is drawn |
| 11.4 | Risk 2 in section 10 applied here identically. | **Closed** with it — see risk 2. `SITE_URL` and `APP_ENV` are still evaluated during the build, so an image is still environment-specific; the API address no longer is |
| 11.5 | A customer who is also a club member enrols a passkey twice and signs in twice. Surfaced in one sentence on the security screen rather than solved. | Open — `verticals.md` risk 3, which needs a central authentication origin |

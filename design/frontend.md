# Frontend design

Next.js 16.3.2 on React 19.2.8, App Router, TypeScript throughout. Every page a member sees is
rendered here. The application holds no database and no session store of its own: state that
outlives a request lives in Django, and the one exception is documented in section 5.

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
| `/member` | Server | A member's home. Guarded. |
| `/cultivator` | Server | A cultivator's home. Guarded. |
| `/admin` | Server | An administrator's home. Guarded. |
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
`app/accounts/roles.py` as text and refuses a codename Django does not grant — so a renamed action
cannot quietly empty a menu.

Almost every destination is marked `planned` and renders as inert text with a "Not built yet" badge,
because the models they act on do not exist. A planned tile is never a link and never a disabled
button: a control that looks operable and does nothing costs a member a click and a screen-reader
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
| `NEXT_PUBLIC_DJANGO_API_URL` | No | Public address the browser reaches Django on. Baked in at build. |

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

Two specific gaps behind the gate:

- **No administration screens.** The administrator's home is self-contained — it does not link to
  the Django admin, because that opens on `is_staff` and the two facts are independent, so such a
  link would work for some administrators and refuse others. The cost is that the nine
  administrative destinations have no API endpoint behind any of them, and records are still managed
  by hand in the Django admin by somebody holding `is_staff`.
- **Outstanding club documents are not surfaced.** `GET /api/documents/outstanding` exists and
  nothing calls it, so a member owing a re-acceptance is not asked for one.

**Nothing entered at sign-up is stored.** See `features/sign-up.md` section 6.

## 10. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | The authenticated components are untested and diverge from the component conventions. | Closed — rewritten to `Domain/PascalCase.tsx` with colocated tests and pure rules in `lib/`. See section 9 |
| 2 | `NEXT_PUBLIC_DJANGO_API_URL` is baked into the client bundle at build time, so one artefact cannot serve two environments. A promoted build carries the wrong API address. | Open |
| 3 | The age pass is unsigned. Accepted, because the rule is re-applied on read and there is nothing to protect. Signing arrives free if an `AUTH_SECRET` is ever introduced. | Accepted |
| 4 | `.next/types/validator.ts` is generated build output that `tsconfig.json` includes. A stale copy referencing deleted routes breaks `npm run typecheck` with errors that point at no real source file. Cleared once; will recur after routes are renamed. | Open |
| 5 | 1,305 tests take about sixty seconds, most of it jsdom environment setup. Tolerable now, worth watching as the member area is built. | Accepted |
| 6 | `app/api/nickname/availability/route.test.ts` asserts an eight-character random hex reference does not contain `"500"`, `"503"`, `"429"` or `"422"`. All four are valid hex, so the test fails on roughly one run in thirty. Predates this work. | Open — a one-line fix, not yet taken |
| 7 | `CDN_BASE_URL` is read while `/` is prerendered, so the club film's address is fixed at build time — as `SITE_URL` already is, through the root layout's `metadataBase`. A promoted artefact serves the film from the wrong host. Same class as risk 2. Making the one indexable page dynamic would cost more than it saves; the remedy is a build per environment. | Open |

# Farm to Consumer — store frontend

Next.js 16 (App Router, React 19, Tailwind CSS 4, TypeScript) rendering the produce market
storefront. All data comes from the Django API; this app holds no database of its own.

The second of the two applications in this workspace. The club is `../club`, and what the two share,
what they must not, and why nothing is extracted into `../packages` yet are in `../README.md` and
`design/verticals.md` section 7.

## Setup

```
npm install          # from frontend/, once, for both applications
copy .env.example .env.local
```

## Running

```
npm run dev        # http://localhost:3001/
npm run build      # production build (also typechecks)
npm run typecheck  # tsc --noEmit
npm run lint
npm test
```

Port 3001, so the store and the club can run at the same time. The Django API must be running on
http://localhost:8000/.

Use `localhost` rather than `127.0.0.1`. The Django session cookie is `SameSite=Lax`, so the two
servers must share a hostname or the browser will not send it to the API — and an IP address is not a
valid WebAuthn Relying Party ID, so passkeys do not work there either.

## Two local traps worth knowing before you file a bug

**The storefront is resolved from the host Django sees, and locally that host is the club's.**
`GET /api/documents/published` is unauthenticated, so `storefront_for_request` reads the domain the
request arrived on. Both applications call the same Django on `localhost:8000`, which is not in
`DJANGO_STOREFRONT_HOSTS`, so it falls back to `DJANGO_DEFAULT_STOREFRONT` — `club`. Working on
`/legal` therefore means setting that variable to `market` in the repository root `.env`, or expecting
the club's documents to appear. In a deployment the two hosts are different and the mapping does the
work. See `app/core/storefronts/resolution.py`.

**The store has no documents of its own yet**, so `/legal` correctly says nothing is published. That
is an item on `design/todo.md` Block B, not a fault in this application — and the page tells the two
states apart, so "nothing published" and "could not be read" never look the same.

## Layout

| Path | Purpose |
| --- | --- |
| `app/page.tsx` | The front door. Public and indexable |
| `app/legal/` | Terms, privacy and data, from `GET /api/documents/published`. Public and indexable |
| `app/(auth)/sign-in/` | Identifier-first sign-in: passkey, or a code emailed by the store |
| `app/(auth)/sign-up/` | Create an account — four fields, no membership. See below |
| `app/(account)/` | The signed-in area and the session gate in front of it |
| `components/` | Screens and primitives, grouped by where they appear |
| `lib/api.ts` | Browser-side API calls; handles cookies and CSRF |
| `lib/server-api.ts` | Server-side API calls; forwards the request's cookies |
| `lib/session.ts` | The one gate: is this anybody. There is no membership to check |
| `app/globals.css` | Design tokens. Colour is sampled from the store logo; type is still a placeholder — see `lib/brand.ts` |
| `components/Brand/Mark.tsx` | The F2C logo, traced to vector from `design/F2C_new_logo-…png` |

## What is not built, and is not pretending to be

**Sign-up cannot complete, because the endpoint does not exist.** Django registers club members
(`POST /api/members/register`, with an identity number, consents and a subscription); it has no
endpoint for a plain customer. `lib/sign-up-api.ts` is written against the contract that endpoint will
have and answers `unavailable` on the 404 it gets today, which the screen renders as "accounts are not
open yet". Nothing is stubbed and no local state pretends an account was made. When the endpoint
lands, that one file changes.

**No catalogue, cart, order or delivery.** The market vertical is `design/todo.md` Block B.

**No avatar.** The endpoints work for any account; what is missing is a reason, since a shopper's
photograph is shown to nobody. Adding it is this app's `lib/profile-api.ts`, a cropper and one card.

**No administration area.** `StorefrontStaff` already carries the market appointment, and there is no
`platform.*` codename for it — so there is deliberately no tile gated on one. C29.

## Talking to the API

Never call `fetch` against Django directly from a component. Use the two helpers, because each solves
a different problem:

- **Server components** have no browser attaching cookies, so `lib/server-api.ts` copies the incoming
  request's `Cookie` header onto the outbound call. Responses are `no-store`, since they are per-user.
- **Browser code** needs `credentials: "include"` plus an `X-CSRFToken` header on unsafe methods.
  `apiFetch` in `lib/api.ts` adds both, fetching a CSRF token from `/api/auth/csrf` the first time one
  is needed.

After any call that changes the session (sign-in, sign-out), call `router.refresh()` so server
components re-read it.

## Passkeys are per domain

A passkey enrolled here works here. The club is a different registrable domain, so a customer who is
also a club member enrols twice and signs in twice — `design/verticals.md` section 8 and risk 3. The
security screen says so, once, because it is otherwise reported as a bug.

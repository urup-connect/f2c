# Cultivators Collective — frontend

Next.js 16 (App Router, React 19, Tailwind CSS 4, TypeScript) rendering every
page of the platform. All data comes from the Django API; this app holds no
database of its own.

## Setup

```
npm install
copy .env.example .env.local
```

## Running

```
npm run dev        # http://localhost:3000/
npm run build      # production build (also typechecks)
npm run typecheck  # tsc --noEmit
npm run lint
```

The Django API must be running on http://localhost:8000/ — from the repository
root, `.\rundev.ps1` starts both.

Use `localhost` rather than `127.0.0.1`. The Django session cookie is
`SameSite=Lax`, so the two servers must share a hostname or the browser will not
send it to the API.

## Layout

| Path | Purpose |
| --- | --- |
| `app/page.tsx` | Landing page; server-renders API status and session state |
| `app/login/` | Login page (server) + form (client) |
| `app/dashboard/` | Authenticated page; redirects anonymous visitors |
| `components/` | Client components |
| `lib/api.ts` | Browser-side API calls; handles cookies and CSRF |
| `lib/server-api.ts` | Server-side API calls; forwards the request's cookies |

## Talking to the API

Never call `fetch` against Django directly from a component. Use the two
helpers, because each solves a different problem:

- **Server components** have no browser attaching cookies, so
  `lib/server-api.ts` copies the incoming request's `Cookie` header onto the
  outbound call. Responses are `no-store`, since they are per-user.
- **Browser code** needs `credentials: "include"` plus an `X-CSRFToken` header on
  unsafe methods. `apiFetch` in `lib/api.ts` adds both, fetching a CSRF token
  from `/api/auth/csrf` the first time one is needed.

After any call that changes the session (login, logout), call `router.refresh()`
so server components re-read it.

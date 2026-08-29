# Frontend

Two applications, one per storefront, as npm workspaces.

```
frontend/
  club/        the cannabis club, on port 3000
  market/      the produce market, on port 3001
  packages/*   shared code, once there is any
```

`npm install` once here; npm hoists `node_modules` to this directory and there
is one lockfile for both applications.

## Why the club moved into a subdirectory before the market was written

Until Block 0.5 this whole directory *was* the club, which meant every new file
landed inside that assumption without anybody choosing it. Moving it while there
was exactly one application to move cost a directory rename; moving it later
would have cost the same rename plus whatever had accumulated against the old
shape — including, as it turns out, an entire second application.

## Why `packages/` is still empty

The market application now exists, so there *is* a second consumer — and nothing
has been extracted, which is a decision taken with that consumer in front of us
rather than the earlier decision left standing.

What the store needed from the club turned out to be three different kinds of
thing, and only one of them is ready to be a package:

- **Platform rules, identical and copied verbatim** — `person-name.ts`,
  `sa-mobile-number.ts`, `email-address.ts`, `env.ts`, with their test suites.
  These are `packages/` material and nothing about them is in doubt. They are
  copied for now so that the boundary is drawn once, deliberately, rather than
  file by file while the second application was being written.
- **Same shape, different content** — the API client, the sign-in form, the
  passkey card, the form primitives. Extractable, but only after the store's copy
  has been read against the club's: two of them already differ in ways that would
  otherwise become props on a shared component (the club routes to one of three
  homes, the store to one account area; the club's `TextField` carries a notice
  slot the store has no use for).
- **Looks shared and is not** — the environment reading. The club requires
  `CDN_BASE_URL` and the store must not, so a shared reader would take a schema
  argument, which is most of the way back to two readers.

Copying the tests alongside the copied rules is what makes this safe to leave:
a rule fixed in one application and not the other fails a test rather than
diverging quietly. Recorded as risk 11.3 in `design/frontend.md`.

## What must not be shared

`club/lib/copy-compliance.ts` is a cannabis constraint. It forbids currency,
retail voice and clinical claims in member-facing copy, and the produce market
is held to none of that — a market that could not name a price would not be a
market. It stays in the club application even after `packages/` fills up.

The market enforces the mirror image of this rather than nothing at all:
`market/lib/store-content.test.ts` flattens every fixed string in that
application and refuses any that names the club or its produce. The two
storefronts are separate businesses on separate domains with separate mail
servers, and copy that crossed would be indistinguishable from a phishing
attempt — which is the same reason `app/core/storefronts/mail.py` exists.

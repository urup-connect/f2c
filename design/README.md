# Design documentation

What this product is, how it is built, and why each significant decision went the way it did.
These documents describe the system **as it stands today**, not as it is planned. Where something
is deliberately unbuilt, it is recorded as unbuilt rather than omitted.

## The documents

| Document | Covers |
| --- | --- |
| [frontend.md](frontend.md) | The Next.js application: rendering model, routes, module layers, configuration, testing |
| [backend.md](backend.md) | The Django application: the member record, encryption, API surface, admin, testing |
| [features/roles-and-permissions.md](features/roles-and-permissions.md) | The three roles, the action catalogue, and where each is enforced |
| [features/authentication.md](features/authentication.md) | Passkeys, emailed sign-in codes, sessions, rate limits |
| [features/sign-up.md](features/sign-up.md) | The age gate, the details a joining member gives, the club document agreements |
| [features/payments.md](features/payments.md) | The membership subscription, the Payfast integration, and what a payment does to an account |
| [features/landing.md](features/landing.md) | The public landing page, its copy governance and its indexing rules |
| [features/brand.md](features/brand.md) | Colour, typography, logo artwork, photography and the design tokens behind them |

Read `frontend.md` and `backend.md` for the shape of the system. Read a feature document for the
reasoning behind one part of it.

## Where the boundary between the two halves sits

Django renders no user-facing pages. It serves a JSON API and the Django admin, and nothing else.
Every page a member sees is rendered by Next.js, which calls the API server-side and forwards the
member's cookies so that a server-rendered page knows who is signed in.

```
Browser ──▶ Next.js :3000                    Django :8000
            App Router, SSR/RSC ──────────▶  /api/...    JSON API (django-ninja)
                                             /api/docs   OpenAPI, DEBUG only
                                             /admin/     Django admin
```

That split is the single most consequential decision in the project, and both halves are shaped by
it. See `frontend.md` section 2 and `backend.md` section 2.

## Conventions used here

- **Decisions carry their reason.** A section that states a rule without saying what it rules out
  is incomplete. The rejected alternative is usually the more useful half.
- **Deliberate absences are recorded.** "Not built" and "built but not reachable" are different
  states, and both appear below in the sections named *What is not built*.
- **Risks are numbered and kept.** A risk is not deleted when it is accepted; it is marked accepted.
- **No personal data.** No customer names, no real identity numbers, no live addresses. The RSA ID
  numbers that appear in these documents and in the test suite are synthetic, chosen for a valid
  check digit.

## A note on stale references in the source

Roughly 125 comments across the source and test files cite an earlier documentation set by
filename and section number, in the form `design/features/landing-page-engagement.md section 6.6`.
Those files were not in the repository when this set was written, and this set is organised by
subject rather than by the earlier delivery increments. The mapping below is what those citations
now point at. It is recorded here rather than by editing 125 comments, which would be churn
against a set of files that are otherwise accurate and well annotated.

| Cited in the source | Now covered by |
| --- | --- |
| `features/landing-page-engagement.md` | [features/landing.md](features/landing.md) |
| `features/public-landing-and-auth-routing.md` | [features/landing.md](features/landing.md), [frontend.md](frontend.md) §4, §7 |
| `features/brand-design-system.md` | [features/brand.md](features/brand.md) |
| `features/age-gate-before-sign-up.md` | [features/sign-up.md](features/sign-up.md) §3 |
| `features/member-details-at-sign-up.md` | [features/sign-up.md](features/sign-up.md) §4 |
| `features/club-document-agreements-at-sign-up.md` | [features/sign-up.md](features/sign-up.md) §5 |
| `features/passkey-auth-with-email-otp.md` | [features/authentication.md](features/authentication.md) |
| `features/data-layer-foundation.md` | [backend.md](backend.md) §4, [frontend.md](frontend.md) §6 |
| `features/membership-payment-status.md` | Partly built. See [features/payments.md](features/payments.md); the member-facing status screen is still unbuilt, §9 there |

The section and criterion numbers in those citations do not carry across. They referred to numbered
acceptance criteria in the earlier documents, and this set does not restate them.

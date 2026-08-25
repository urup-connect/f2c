# Authentication

Members have no password. Two credentials get them in: a passkey, or a code emailed to them.

## 1. Executive summary

The decision behind this feature is that a member of a cannabis club should not have a password.
Passwords are the credential members reuse, phishers harvest and the club would be liable for
storing. A passkey cannot be phished because nothing shared is ever transmitted, and an emailed code
is bounded to five minutes and five attempts.

Staff keep email and password sign-in, because Django admin needs it. The frontend does not offer
it.

The design constraint that shapes everything else is that **the API must not reveal who is a
member.** Membership of a cannabis club is sensitive in a way that membership of most clubs is not.
Every endpoint that takes an email address answers an unknown address exactly as it answers a real
one.

**Status:** complete and tested, and reachable from the browser. A member signs in at `/login` and
lands in their own area. The one thing still missing is an email provider, without which the code
fallback does not work on a deployed environment — see section 8.

## 2. The two credentials

### A passkey

A WebAuthn credential held by the device: Face ID, Windows Hello, a security key, or a passkey
synced through iCloud Keychain or Google Password Manager.

`resident_key` is **preferred**, so the passkey can later identify the member on its own.
`user_verification` is also **preferred** rather than required — insisting on it locks out
authenticators that cannot do biometrics or a PIN, which is a real population and not an edge case.

### A code emailed to them

Six digits, valid for five minutes, single use, burned after five wrong guesses.

This is the fallback when the member has no passkey, is on a device that does not hold theirs, or
simply asks for a code. It is also **the only route into a new account** — a member with no passkey
has to get in some other way before they can enrol one.

That makes it a front door, not a back door, and it is treated as a first-class credential:

| Property | Mechanism | Without it |
| --- | --- | --- |
| Hashed at rest | Django's configured password hasher | A six-digit secret is reversible from a database dump before it expires |
| Expires | `OTP_TTL_SECONDS`, 300 | A leaked code stays valid indefinitely |
| Single use | `consumed_at` stamped on success | A code works twice |
| Attempt-bounded | `OTP_MAX_ATTEMPTS`, 5 | Six digits is a few thousand requests, not a secret |
| Superseded | Issuing consumes any outstanding code | Asking again widens the guessing surface |

The attempt counter bounds **attempts, not failures** — it increments on a correct code too. So the
code is spent after five tries regardless of how the guesses are spread out, and there is no way to
reset it by interleaving a correct guess.

Five minutes is long enough for an email to arrive and short enough that a leaked code is worthless
by the time it is found.

## 3. Sign-in is identifier-first

`POST /api/auth/login/start` takes an email address and answers with one of two things:

- **`{"method": "passkey", "options": {...}}`** — the address has at least one passkey, and the
  WebAuthn challenge is enclosed.
- **`{"method": "otp"}`** — a code has been emailed. This is also the answer for an address with no
  account, a Pending account, a Suspended account and an erased account.

That second case is the whole point. The endpoint cannot be used to find out who is a member,
because four different situations produce a byte-identical response.

Only an account with status **Active** can sign in. Pending, Suspended and erased accounts are all
refused identically, and the refusal never says which.

### What it does reveal, and why that is accepted

`login/start` does reveal **which addresses have a passkey**, because the credential IDs have to
reach the browser for the authenticator to match against them.

That is inherent to an identifier-first passkey flow. Closing it means moving to a usernameless flow
over discoverable credentials, where the browser offers the member a list of passkeys before any
address is typed. That is a better flow and a larger change; it is recorded as accepted risk 5 in
`backend.md`.

## 4. Sessions and CSRF

The frontend never handles a token. Django issues an `HttpOnly` `sessionid` cookie on sign-in; the
browser returns it on every request; unsafe methods additionally carry a CSRF token the frontend
reads from a non-`HttpOnly` `csrftoken` cookie and echoes in `X-CSRFToken`.

Endpoints that run before a session exists set `auth=None`, which also turns off django-ninja's
built-in CSRF check — so they call `check_csrf` themselves. Sign-in is a state-changing request and
must not be forgeable.

`alogin` rotates the session key, so a pre-sign-in session cannot be fixated.

Passkey and code sign-ins never call `authenticate()`, so Django cannot infer which backend
authorised them and it has to be named explicitly.

## 5. The WebAuthn ceremonies

A ceremony is two round trips: the server issues a challenge, the browser has the authenticator sign
it, and the server verifies the signature against that same challenge. The challenge is held in the
Django session between the halves — which works before the member is signed in, because
`SessionMiddleware` gives every visitor a session.

Four properties of the challenge are the security of the whole feature:

1. **Short-lived.** `WEBAUTHN_CHALLENGE_TTL_SECONDS`, 300.
2. **Single use.** `take_challenge` removes the value whether or not the verification that follows
   succeeds, so a challenge cannot be replayed against a second attempt.
3. **Pinned to a user** on the sign-in path, so a credential belonging to a different account cannot
   be presented against it.
4. **Ceremony-separated.** Enrolment and sign-in use different session keys, so an enrolment
   challenge cannot be replayed against the sign-in endpoint.

Enrolment is authenticated on purpose. A passkey can only be added by a member who has already
proved who they are some other way, which for a new account means an emailed code.

The passkey user handle is a UUID of its own — not the account's primary key and certainly not the
email address. WebAuthn stores this value inside the credential and, for discoverable credentials,
syncs it to the member's password manager. The spec is explicit that it must not contain personal
information, which rules out the address; and the account's own primary key appears in URLs and API
payloads, so a handle that leaks out of a password manager should not be a key to anything else.

Verification refuses to run without a configured relying party. `rp_id()` and `origins()` raise
`ImproperlyConfigured` naming the environment variable, because this is a failure that happens in
deployment rather than on a developer's machine.

## 6. Passkeys have hard hosting requirements

The Relying Party ID is a **registrable domain**, and it is bound to the origin the JavaScript runs
on — the Next.js origin, not Django's. Three consequences, all of which have bitten someone:

- **Locally, sign in at `http://localhost:3000`, never `http://127.0.0.1:3000`.** An IP address is
  not a valid RP ID and passkeys will not work there. The session cookie has the same requirement
  for a different reason.
- **Everywhere else needs HTTPS.** `localhost` is the only exemption the browser makes.
- **In production both halves must sit under one registrable domain** — for example
  `app.example.co.za` and `api.example.co.za` with `DJANGO_WEBAUTHN_RP_ID=example.co.za`.

| Variable | Required | Note |
| --- | --- | --- |
| `DJANGO_WEBAUTHN_RP_ID` | When `DEBUG=False` | Registrable domain. Not a URL, not an IP. |
| `DJANGO_WEBAUTHN_ORIGINS` | When `DEBUG=False` | Full frontend origins, scheme and port included. |
| `DJANGO_WEBAUTHN_RP_NAME` | No | The name the authenticator shows the member. |

## 7. Emailed codes in development

`MAILERS` uses the console backend, so codes are printed to the terminal running Uvicorn rather than
sent. Look for the message body in that output.

Django 6.1 has no async email API, and password hashing is deliberately slow, so both run in a
worker thread rather than on the event loop.

## 8. Reaching it from the browser

`/login` renders `components/Auth/SignInForm.tsx`, which runs the identifier-first flow above:
an address, then a passkey challenge or the code step, with a failed passkey offering the code as
an explicit fallback rather than silently swapping the form out.

A member who signs in lands on their own area — `/member`, `/cultivator` or `/admin`, chosen from
the `role` the sign-in endpoint returns. Each of those carries a passkey card, so enrolling one is
reachable from the moment a member first gets in with a code. See `frontend.md` section 4.

The three components that were written but unrouted have been replaced rather than wired up as they
stood. They predated the layered structure, used a different naming convention and had no tests:

| Was | Is now |
| --- | --- |
| `components/login-form.tsx` | `components/Auth/SignInForm.tsx`, with the rules in `lib/sign-in.ts` and the copy in `lib/sign-in-content.ts` |
| `components/passkey-manager.tsx` | `components/Account/PasskeyCard.tsx` and `PasskeyList.tsx`, with the rules in `lib/passkeys.ts` |
| `components/sign-out-button.tsx` | `components/Club/SignOutButton.tsx` |

All of them now have colocated tests, which closes risk 4.

**A defect the rewrite found.** `passkey-manager.tsx` read `browserSupportsWebAuthn()` during
render. That component is server-rendered before it reaches a browser, and on the server there is
no `navigator` to ask — so the capability answered *no* for every browser alive, and the server HTML
of a perfectly capable machine said *this browser cannot create passkeys*. The check now starts
optimistic and an effect corrects it after mount. Optimistic rather than pessimistic because the two
are not symmetrical: a capable browser briefly told it cannot is a member who gives up on a working
feature, while an incapable one briefly offered the button gets a refusal it can act on.

### What is still not built

**No email provider is configured.** Until one is, no member can sign in on a deployed environment
at all, because the code is printed to a server console nobody is reading. This is the single thing
between the feature and a working sign-in on QA.

**Nothing enrols a passkey without a code first.** By design — see section 5 — but it means the
email provider gates passkeys too, not only the fallback.

**Staff password sign-in is still unrestricted.** `POST /api/auth/login` is not offered by the
frontend and is not limited to staff either. See risk 5.

## 9. A defect worth recording

The passkey sign-in path returned **500 for every member who had a passkey enrolled**, and had done
since it was written.

`login/start` stored the challenge with `user_id=user.pk`. `user.pk` is a `UUID`; the Django session
is serialised to JSON; JSON has no UUID type and raises rather than coercing. Every passkey sign-in
therefore failed in session middleware, after the response had been generated.

The same bug had a second half waiting behind it. `login/passkey` compared `credential.user_id` — a
`UUID` — against the value read back out of the session. A `UUID` is never equal to its own string
form, so even with the write fixed, every correct passkey would have been refused as *not
recognised*.

Both halves are fixed: the value is stored and compared as text.

The reason it survived is worth more than the fix. There were no tests over the API layer at all —
only over the model — so nothing exercised `login/start` for a member with a passkey. The path was
unreachable from the browser too, so no manual testing would have found it either.
`test_the_challenge_is_stored_pinned_to_the_member` now guards it.

## 10. Risks

| # | Risk | Status |
| --- | --- | --- |
| 1 | Rate limits are per worker with the default cache, so a multi-worker deployment multiplies every limit — including the one bounding outbound email. | Open — blocks production |
| 2 | No email provider. The only route into a new account does not work on a deployed environment. | Open — blocks production |
| 3 | `login/start` reveals which addresses have a passkey. Inherent to identifier-first flows. | Accepted |
| 4 | The authenticated components are untested and unrouted. Wiring them up without tests moves that debt into the member-facing product. | Closed — rewritten to the component conventions with tests, and routed. See section 8 |
| 5 | Staff password sign-in remains at `POST /api/auth/login`. It is not offered by the frontend but it is not restricted to staff either — an Active member with a usable password could use it. Members are created with an unusable password, so this is currently unreachable rather than closed. | Open — worth an explicit `is_staff` check |

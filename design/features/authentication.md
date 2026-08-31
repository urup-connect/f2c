# Authentication

Members have no password. Two credentials get them in: a passkey, or a code emailed to them.

## 1. Executive summary

The decision behind this feature is that a member of a cannabis club should not have a password.
Passwords are the credential members reuse, phishers harvest and the club would be liable for
storing. A passkey cannot be phished because nothing shared is ever transmitted, and an emailed code
is bounded to five minutes and five attempts.

Staff keep email and password sign-in **at Django admin's own login view**, because Django admin
needs it. There is no password endpoint on the API: one existed and was deleted — see risk 5.

The design constraint that shapes everything else is that **the API must not reveal who is a
member.** Membership of a cannabis club is sensitive in a way that membership of most clubs is not.
Every endpoint that takes an email address answers an unknown address exactly as it answers a real
one.

**Status:** complete and tested, and reachable from the browser. A member signs in at `/login` and
lands in their own area. Each storefront now sends its own mail through its own server — see section
7 — and what is still missing is the credentials for each deployed environment.

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

## 7. Which server the code is sent from

**Two SMTP servers, one per storefront.** `MAILERS` holds a `club` mailer built from `EMAIL_CC_*` and
a `market` mailer built from `EMAIL_F2C_*`; the aliases are the storefront codes, so routing is
`.send(using=storefront)`. `app/core/storefronts/mail.py` resolves the storefront into all three of
the server, the `From` address and the name in the subject and signature, because those three have to
agree — a code from the store's provider signed "Cultivators Collective" reads as a phishing attempt,
which is the one thing a member must be able to rule out about a one-time code.

The storefront is the **host's**, through `storefront_for_request`, not the member's. `login/start`
and `otp/start` have to answer an address with no account at all, so there is nothing else to ask,
and a member of both storefronts signing in at the store should be answered by the store. What has
*not* changed is the code's scope: `EmailOtp` is not storefront-scoped, so a code issued at one
storefront still verifies at the other. Only the envelope moved. See `design/verticals.md` section 8.

There is no fallback to the other storefront's server. With `DEBUG=False` a blank `EMAIL_*_HOST` or
`EMAIL_*_FROM` refuses startup, because the alternative sends successfully and looks fine.

### In development

Leave both `EMAIL_*_HOST` blank and every storefront falls back to the console backend, so codes are
printed to the terminal running Uvicorn rather than sent. Look for the message body in that output.

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

**The mail servers are configurable but each environment still has to be given credentials.** The
per-storefront plumbing exists — see section 7 — and Django now refuses to start with `DEBUG=False`
until both storefronts have a host and a sender, so this fails loudly at deploy rather than quietly
at the first sign-in. Filling in `EMAIL_CC_*` and `EMAIL_F2C_*` on QA is what remains.

**Two traps found while configuring it locally, both silent, and worth knowing before QA is filled
in.** Neither is caught by `_mailer`, which validates only that `USE_TLS` and `USE_SSL` are not set
together:

- **`PORT=465` with `USE_TLS=True` hangs.** 465 is implicit TLS and `USE_TLS` is STARTTLS, so the
  send opens a plaintext conversation on a port expecting a handshake and waits out the ten-second
  timeout. Use 587 with `USE_TLS`, or 465 with `USE_SSL` — and check which the provider actually
  offers: on the cPanel host configured locally, 465 presents a certificate with no subject, issuer
  or SANs and fails verification, while 587 verifies against the system roots.
- **Omitting `EMAIL_CC_FROM` or `EMAIL_F2C_FROM` sends as the other storefront.** `_from_email`
  falls back to `DEFAULT_FROM_EMAIL` under `DEBUG`, which is a single address and therefore one
  storefront's — so the club sends as the market's domain. Outside `DEBUG` it raises instead, which
  is the right behaviour and the reason this only bites locally. Set each to the mailbox that
  storefront authenticates as.

**Nothing enrols a passkey without a code first.** By design — see section 5 — but it means the
mail configuration gates passkeys too, not only the fallback.

**Staff password sign-in has been removed from the API.** `POST /api/auth/login` no longer
exists. Staff authenticate at `/admin/login/`, which is Django's own view and does not route through
django-ninja. See risk 5.

**A blocked account is told by email, and the endpoints still say nothing.** The vagueness above is
not softened for somebody who cannot get in: `_find_user` filters to Active, so a suspended or
revoked account is answered exactly as a stranger is, and no sign-in response distinguishes them.
The explanation reaches the mailbox instead — `accounts.notifications` — which is the one channel
only its owner reads. A *club* suspension leaves the account able to sign in, so those members also
reach `/blocked`, which names their standing and deliberately not the club's reasons. **C32.**

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
| 2 | No email provider. The only route into a new account does not work on a deployed environment. | Partly closed — two per-storefront SMTP mailers are configurable and required outside `DEBUG` (section 7), and a provider is now configured locally with the club mailbox authenticating. Each **deployed** environment's credentials are still outstanding, as is the market mailbox, which does not authenticate. Two silent traps in the configuration itself are recorded in section 8 |
| 3 | `login/start` reveals which addresses have a passkey. Inherent to identifier-first flows. | Accepted |
| 4 | The authenticated components are untested and unrouted. Wiring them up without tests moves that debt into the member-facing product. | Closed — rewritten to the component conventions with tests, and routed. See section 8 |
| 5 | Staff password sign-in remains at `POST /api/auth/login`. It is not offered by the frontend but it is not restricted to staff either — an Active member with a usable password could use it. Members are created with an unusable password, so this is currently unreachable rather than closed. | **Closed by deleting the endpoint**, not by restricting it. An `is_staff` check would have left a route that opens a session on a password and relies on a second fact — the unusable hash — to be safe. Nothing called it: both frontends use the passkey and code routes, and staff use `/admin/login/`. `NoPasswordLoginTests` holds it at 404 |
| 6 | **The test suite sent through the real `MAILERS`, not a stub.** Django's `setup_test_environment` replaces `EMAIL_BACKEND`, which nothing here sends through — so a developer with a populated `.env` had a suite aimed at their provider. Latent until C32's suspension email reached a `TransactionTestCase`, whose `on_commit` callbacks do run. | Closed — `f2c/test_runner.py` points every alias in `MAILERS` at locmem for the duration of a run, set as `TEST_RUNNER`. Nothing was ever delivered, but a suite that tries is one that can succeed against the addresses in the fixtures |

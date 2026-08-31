import 'server-only'

import { apiBaseUrl } from './api'
import type { SignUpOutcome, SignUpSubmission } from './sign-up'
import { readSignUpRefusals } from './sign-up'

/**
 * Registers a store customer with Django, and never throws.
 *
 * ## The endpoint
 *
 * `POST /api/customers/register` — four fields, no consents, no identity number, no payment. It
 * creates a `User` and **nothing else**: no `ClubMembership`, no `StorefrontStaff`, no
 * `ProducerMembership`, and therefore no permission of any kind. `app/core/accounts/registration.py`
 * is the service, and it records why each absent field is absent.
 *
 * **It is not the club's registration and must never become it.** Django's other registration
 * endpoint, `POST /api/members/register`, requires an identity number and document consents and
 * creates a `ClubMembership` — calling that one from here would enrol shoppers in a cannabis club.
 * The two are separate endpoints on separate prefixes for exactly that reason.
 *
 * **Consents are still absent, and their absence is now enforced on the Django side rather than
 * merely intended.** The store has no published documents, so there is nothing to tick. The day one
 * is published at `agreement=at_registration`, the endpoint refuses every registration with a 503
 * rather than creating customers recorded as having agreed to nothing —
 * `registration.ConsentRequired`. That lands here as `unusable`, which is the right answer:
 * extending this contract to carry consents is our work and not the customer's.
 *
 * **A 404 no longer means "not built".** It means the API could not route the request, which is a
 * deployment fault rather than a phase of the project. The `unavailable` branch stays because it is
 * a different diagnostic from a 500, not because the endpoint might be missing.
 *
 * `design/frontend.md` section 11.4 records the contract.
 *
 * ## Why it is server-only
 *
 * The club's equivalent is server-only because it carries an identity number. This one carries none,
 * and is server-only for a different reason that applies just as firmly: registration is
 * unauthenticated, so it is the one call an abuser can make without an account, and keeping it behind
 * a server action means the origin Django rate-limits and CORS-checks is ours rather than any
 * browser's. It also keeps the sign-up screen renderable without JavaScript.
 *
 * ## Fails closed, and says which kind of failure it is
 *
 * A refusal the customer can act on comes back as `refused` with field-level reasons. A 404 comes
 * back as `unavailable`. Anything else — the API unreachable, a body that does not parse, a status
 * nobody planned for — comes back as `unusable`, and the screen says the fault is ours. Nothing here
 * throws, so the server action does not need a try/catch to stay up.
 */

/** The path the store's registration answers on. One string, one place. */
export const REGISTER_PATH = '/api/customers/register'

export const createAccount = async (submission: SignUpSubmission): Promise<SignUpOutcome> => {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}${REGISTER_PATH}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      /*
       * Never cached, and it could not be: a POST is not cacheable. Stated so a later change to this
       * call cannot inherit a default that would replay one registration for another.
       */
      cache: 'no-store',
      body: JSON.stringify(submission),
    })
  } catch {
    return { status: 'unusable', reason: 'The store could not be reached.' }
  }

  if (response.status === 404) return { status: 'unavailable' }

  let body: unknown

  try {
    body = await response.json()
  } catch {
    body = null
  }

  const payload = body !== null && typeof body === 'object' ? (body as Record<string, unknown>) : {}

  if (response.ok) {
    /*
     * The address is echoed from the submission rather than read out of the response, and the
     * response is not consulted for who was created. Two reasons, and both are the disclosure rule:
     * the API answers identically for an address already on file, so there is nothing to read; and a
     * confirmation built from a response body would put a value in reach of a redirect's query
     * string. See `SignUpOutcome`.
     */
    return { status: 'accepted', email: submission.email }
  }

  if (response.status === 409 || response.status === 422) {
    const refusals = readSignUpRefusals(payload)

    /*
     * A refusal status with nothing this application understands is unusable, not empty. Returning no
     * refusals would send somebody back to a form showing nothing wrong with it.
     */
    return refusals.length > 0
      ? { status: 'refused', refusals }
      : { status: 'unusable', reason: 'The store refused for an unrecognised reason.' }
  }

  return { status: 'unusable', reason: `The store answered ${response.status}.` }
}

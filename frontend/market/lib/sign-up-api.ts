import 'server-only'

import { apiBaseUrl } from './api'
import type { SignUpOutcome, SignUpSubmission } from './sign-up'
import { readSignUpRefusals } from './sign-up'

/**
 * Registers a store customer with Django, and never throws.
 *
 * ## The endpoint this calls does not exist yet
 *
 * That is stated first because it governs everything below. Django has exactly one registration
 * endpoint today — `POST /api/members/register` — and it registers a **club member**: it requires an
 * identity number and document consents, it creates a `ClubMembership`, and it answers with a
 * checkout token for a subscription. None of that belongs to a produce customer, and calling it
 * would enrol shoppers in a cannabis club.
 *
 * So this file is the one place the store's registration contract lives, written against the shape
 * the API will have rather than the shape it has: four fields, no consents, no identity number, no
 * payment. **Until the endpoint lands, the honest outcome is `unavailable`**, which a 404 produces
 * here and which the screen renders as "accounts are not open yet". Nothing is faked, nothing is
 * stubbed, and no local state pretends an account was made.
 *
 * When the endpoint is built, the change is this file and nothing else: the form, its rules, its
 * refusals and its confirmation screen are all written and tested against `SignUpOutcome`.
 * `design/frontend.md` section 11.4 records the contract and `design/todo.md` Block B carries the
 * work.
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

/** The path the store's registration will answer on. One string, one place. */
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

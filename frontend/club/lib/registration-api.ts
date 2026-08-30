import 'server-only'

import { apiBaseUrl } from './api'
import type { MemberDetails } from './member-details'
import { readCheckoutToken } from './checkout'
import { PENDING_PAYMENT, readRegistrationRefusals } from './registration'
import type { RegistrationOutcome } from './registration'

/**
 * Registers a member with Django, and never throws.
 *
 * Server-side only, and deliberately so. This is the one call in the product that carries an
 * identity number, and it must not be reachable from a browser bundle: the number travels from the
 * form to a server action to Django and stops there. No cookies are forwarded — there is no session
 * yet, which is the whole reason the endpoint is unauthenticated.
 *
 * **Fails closed, and says which kind of failure it is.** A refusal the member can act on comes
 * back as `refused` with field-level reasons. Anything else — the API unreachable, a club document
 * with no published revision, a body that does not parse, a status code nobody planned for — comes
 * back as `unusable`, and the form tells the member the fault is ours. Nothing here throws, so the
 * server action does not need a try/catch to stay up.
 *
 * A 200 that does not carry the expected status is treated as unusable rather than believed. The
 * confirmation screen tells a member their membership is waiting on payment; showing that on the
 * strength of an answer this code did not understand would be telling them something we do not
 * know.
 *
 * See design/features/sign-up.md section 6.
 */
export const registerMember = async (details: MemberDetails): Promise<RegistrationOutcome> => {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}/api/members/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      /*
       * Never cached, and it could not be: a POST is not cacheable. Stated so a later change to
       * this call cannot inherit a default that would replay one member's registration for another.
       */
      cache: 'no-store',
      body: JSON.stringify({
        first_name: details.firstName,
        last_name: details.lastName,
        nickname: details.nickname,
        email: details.email,
        mobile: details.mobile,
        id_number: details.idNumber,
        consents: details.consents.map(({ document, version }) => ({ document, version })),
      }),
    })
  } catch {
    return { status: 'unusable', reason: 'Registration failed: the API is unreachable.' }
  }

  let body: unknown

  try {
    body = await response.json()
  } catch {
    body = null
  }

  const payload = body !== null && typeof body === 'object' ? (body as Record<string, unknown>) : {}

  if (response.ok) {
    /*
     * The token is read strictly rather than trusted. A value that is not a well-formed token
     * becomes `null`, which sends the member to the neutral confirmation screen instead of to a
     * payment page built on a value nobody can use — and `null` is a legitimate answer here in any
     * case, being what a duplicate submission gets. So a malformed one degrades into the path that
     * already exists rather than into a failure.
     */
    return payload.status === PENDING_PAYMENT
      ? {
          status: 'accepted',
          memberStatus: PENDING_PAYMENT,
          checkoutToken: readCheckoutToken(
            typeof payload.checkout_token === 'string' ? payload.checkout_token : null,
          ),
        }
      : {
          status: 'unusable',
          reason: 'Registration returned a status this application does not recognise.',
        }
  }

  if (response.status === 409) {
    const refusals = readRegistrationRefusals(payload)

    /*
     * A 409 with no refusal this application understands is unusable, not empty. Returning no
     * refusals would send the member back to a form showing nothing wrong with it.
     */
    return refusals.length > 0
      ? { status: 'refused', refusals }
      : { status: 'unusable', reason: 'Registration was refused for an unrecognised reason.' }
  }

  return {
    status: 'unusable',
    reason: `Registration failed: the API answered ${response.status}.`,
  }
}

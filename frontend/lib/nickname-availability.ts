/**
 * Asking whether a nickname is free, from the browser, while the form is still open.
 *
 * The one field on this form that may be checked against other members' records before the
 * submission. A nickname is a claim against them, so a member whose choice is spoken for has to
 * make another one, and saying that a name is spoken for reveals nothing about who holds it. The
 * email address, the mobile number and the identity number are the opposite: a live answer about
 * any of those would turn the form into a way to ask whether a named person is a member here, and
 * none of them has an endpoint to ask. See design/features/sign-up.md section 7.
 *
 * **The request goes to this application, not to Django.** `/api/nickname/availability` is a route
 * handler on the site's own origin, which keeps three things true: the API's address stays out of
 * the browser bundle, the fault the member is shown is worded in one place, and the cause is logged
 * where the member cannot read it. See `app/api/nickname/availability/route.ts`.
 *
 * **A check that fails is not a refusal.** Django unreachable, a 500, a rate limit, a body that
 * does not parse: all of them mean nobody knows whether the nickname is free, and the honest thing
 * is to say so and let the member carry on. `/api/members/register` asks again inside the
 * transaction that writes, and that answer is the one that counts — so a failure here costs a
 * courtesy, never the protection.
 *
 * The mapping is a pure function with a test, separately from the fetch that feeds it, for the same
 * reason `lib/registration.ts` is: a mapping that quietly stops recognising an answer shows a
 * member a form with nothing wrong on it.
 */

import { readErrorReference } from './error-reference'

/** Where the browser asks. A route handler on this origin, never Django directly. */
export const NICKNAME_AVAILABILITY_PATH = '/api/nickname/availability'

export type NicknameAvailability =
  | { readonly status: 'available' }
  /** Taken, or reserved. One answer, because there is one thing to do about either. */
  | { readonly status: 'taken' }
  /**
   * Nobody knows. `reference` is the handle on the log line that says why, and is null when the
   * browser could not reach its own origin — there is no server-side line to point at.
   */
  | { readonly status: 'unusable'; readonly reference: string | null }

/** What the route handler answers with. Deliberately not Django's shape; see the route. */
export type NicknameAvailabilityBody = {
  readonly available?: unknown
  readonly reference?: unknown
}

/**
 * The answer, from the status code and the body.
 *
 * A 200 is believed only when it carries a boolean. Anything else — a 502 from the route handler, a
 * 200 with a field this code does not understand, an empty body — is unusable rather than read as a
 * "no": telling a member their nickname is taken on the strength of an answer nobody understood
 * would send them off to invent a second one for no reason.
 */
export const readNicknameAvailability = (
  httpStatus: number,
  body: unknown,
): NicknameAvailability => {
  const payload =
    body !== null && typeof body === 'object' ? (body as NicknameAvailabilityBody) : {}

  if (httpStatus === 200 && typeof payload.available === 'boolean') {
    return payload.available ? { status: 'available' } : { status: 'taken' }
  }

  return { status: 'unusable', reference: readErrorReference(payload.reference) }
}

/**
 * Asks, and never throws.
 *
 * A POST with the nickname in the body, like the Django endpoint behind it and for the same
 * reason: a value in a query string is a value in every access log, proxy log and browser history
 * between here and the member. `cache: 'no-store'` is stated rather than assumed — the answer is
 * about another member's record a moment ago, and a cached one is a wrong one.
 */
export const requestNicknameAvailability = async (
  nickname: string,
): Promise<NicknameAvailability> => {
  let response: Response

  try {
    response = await fetch(NICKNAME_AVAILABILITY_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: JSON.stringify({ nickname }),
    })
  } catch {
    /*
     * The browser could not reach this site at all — offline, or a proxy in the way. There is no
     * log line on our side to hand over, so there is no reference to show.
     */
    return { status: 'unusable', reference: null }
  }

  let body: unknown

  try {
    body = await response.json()
  } catch {
    body = null
  }

  return readNicknameAvailability(response.status, body)
}

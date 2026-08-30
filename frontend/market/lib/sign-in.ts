/**
 * The rules of signing in, as pure functions.
 *
 * Separated from the form that runs them because a rule with a test is a rule that keeps working,
 * and a rule embedded in a component is exercised only by rendering the component and driving it.
 *
 * **Where this is shorter than the club's copy, the reason is the identity split.** The club has to
 * decide which of three homes a member lands on, and whether their membership is paid up. The store
 * has one signed-in area and one question at the door — is this anybody — because buying produce
 * requires an account and nothing else. `design/verticals.md` section 6.
 */

import { ApiError } from './api'
import { SIGN_IN_PROBLEMS } from './sign-in-content'

/** Where a customer lands once they are in, absent anywhere better. */
export const ACCOUNT_HOME_PATH = '/account'

/** How many seconds before another code may be asked for. */
export const RESEND_COOLDOWN_SECONDS = 30

/** How many digits a sign-in code has. Django issues six. */
export const CODE_LENGTH = 6

/** Everything but the digits, dropped as they are typed or pasted. */
export const digitsOnly = (value: string): string =>
  value.replace(/\D/g, '').slice(0, CODE_LENGTH)

/**
 * Whether a `?next=` may be followed.
 *
 * Only a path on this origin. A value beginning `//` is a protocol-relative URL and would take the
 * visitor off-site, which is the whole of the open-redirect bug this closes — so it is refused
 * despite starting with a slash. Anything absolute is refused for the same reason.
 */
export const isSafeNext = (next: string | null): boolean =>
  typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')

/**
 * Where a customer goes once they are in.
 *
 * The `?next=` they arrived with, when it is safe to follow, and the account home otherwise.
 *
 * A `next` pointing somewhere this account has no business in is **followed anyway**, and that is
 * deliberate: the signed-in area guards itself on the server and will send them somewhere useful.
 * One guard that always runs is worth more than a second one here that could disagree with it — and
 * a check in the browser is a courtesy, never a control.
 */
export const destinationAfterSignIn = (next: string | null): string =>
  isSafeNext(next) ? (next as string) : ACCOUNT_HOME_PATH

/**
 * Where an unauthenticated visitor is sent, carrying where they were trying to get to.
 *
 * A `next` that is not a path on this origin is dropped rather than escaped. The account layout
 * builds this from a request header (see `proxy.ts`) whose value the client controls, so it goes
 * through the same rule the form applies to a `?next=` found in the query string.
 */
export const signInPath = (next?: string | null): string =>
  isSafeNext(next ?? null) ? `/sign-in?next=${encodeURIComponent(next as string)}` : '/sign-in'

/**
 * What to say when a WebAuthn ceremony did not complete.
 *
 * Keyed on the `DOMException` name rather than on the message, which browsers word differently and
 * change between versions. Anything unrecognised gets the general wording rather than the browser's
 * own, which is written for a developer.
 */
export const passkeyProblem = (error: unknown): string => {
  const name = error instanceof Error ? error.name : ''

  if (name === 'NotAllowedError') return SIGN_IN_PROBLEMS.passkeyNotAllowed
  if (name === 'InvalidStateError') return SIGN_IN_PROBLEMS.passkeyInvalidState
  if (name === 'SecurityError') return SIGN_IN_PROBLEMS.passkeySecurity

  return SIGN_IN_PROBLEMS.passkeyOther
}

/**
 * What to say when the API refused, or could not be reached.
 *
 * Django's own `detail` is shown when there is one, because the endpoints in `authn.api` are
 * written to be read by a person and are already careful to disclose nothing. Anything else — a
 * network failure, a body that did not parse — becomes the general wording, because whatever a
 * `TypeError` says is not addressed to anybody.
 */
export const apiProblem = (error: unknown): string => {
  if (error instanceof ApiError && error.message.trim().length > 0) return error.message
  return SIGN_IN_PROBLEMS.unreachable
}

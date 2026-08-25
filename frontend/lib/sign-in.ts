/**
 * The rules of signing in, as pure functions.
 *
 * Separated from the form that runs them for the reason the rest of `lib/` is: a rule with a test
 * is a rule that keeps working, and a rule embedded in a component is exercised only by rendering
 * the component and driving it. The two rules here are small and both have teeth — one decides
 * where a member lands, and one decides what they are told when a ceremony fails.
 */

import { ApiError, type User } from './api'
import { clubHomeFor } from './club-roles'
import { SIGN_IN_PROBLEMS } from './sign-in-content'

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
 * member off-site, which is the whole of the open-redirect bug this closes — so it is refused
 * despite starting with a slash. Anything absolute is refused for the same reason.
 */
export const isSafeNext = (next: string | null): boolean =>
  typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')

/**
 * Where a member goes once they are in.
 *
 * The `?next=` they arrived with, when it is safe to follow, and their role's home otherwise.
 *
 * A `next` pointing at an area this role has no business in is **followed anyway**, and that is
 * deliberate: the club area guards itself on the server and will send them to their own home. One
 * guard that always runs is worth more than a second one here that could disagree with it — and a
 * check in the browser is a courtesy, never a control.
 *
 * `null` from `clubHomeFor` is a sharing member, who cannot hold a session at all. They are sent to
 * the front door rather than into an area with nothing in it for them.
 */
export const destinationAfterSignIn = (next: string | null, role: User['role']): string => {
  if (isSafeNext(next)) return next as string
  return clubHomeFor(role) ?? '/'
}

/**
 * Where an unauthenticated visitor is sent, carrying where they were trying to get to.
 *
 * A `next` that is not a path on this origin is dropped rather than escaped. The club layout builds
 * this from a request header (see `proxy.ts`) whose value the client controls, so it goes through
 * the same rule the form applies to a `?next=` found in the query string.
 *
 * Here rather than in `lib/club-session.ts`, which is where it is called from: that module is
 * `server-only` and this is a pure string rule with nothing server about it. Keeping it beside
 * `isSafeNext` and `destinationAfterSignIn` also puts the whole of "where does this member go"
 * in one file.
 */
export const signInPath = (next?: string | null): string =>
  isSafeNext(next ?? null) ? `/login?next=${encodeURIComponent(next as string)}` : '/login'

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
 * written to be read by a member and are already careful to disclose nothing. Anything else — a
 * network failure, a body that did not parse — becomes the general wording, because whatever a
 * `TypeError` says is not addressed to anybody.
 */
export const apiProblem = (error: unknown): string => {
  if (error instanceof ApiError && error.message.trim().length > 0) return error.message
  return SIGN_IN_PROBLEMS.unreachable
}

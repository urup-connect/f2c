import type { User } from './api'

/**
 * Where a signed-in account belongs, given the state of its club membership.
 *
 * **This exists because signing in and being a member stopped being the same question.** Before the
 * split, `pending_payment` was an account status and Django refused the sign-in outright: an unpaid
 * member never reached a screen, so no screen had to decide anything. That could not survive the
 * produce market — a customer buying carrots has no club membership to pay for — so the account is
 * now an identity that signs in, and the club gate moved here. See `design/verticals.md` section 5
 * and C27.
 *
 * The rule is deliberately in one pure function rather than in the layout. It is the kind of thing
 * that grows a second copy in a page guard, and two copies of a payment gate is how somebody
 * reaches the club without paying.
 */

/** The membership states Django can report. `null` is an account with no membership at all. */
export type MembershipStatus = NonNullable<User['membership_status']>

/**
 * Where to send this account instead of the club, or `null` to let it through.
 *
 * Three outcomes, and the middle one is the whole point of the exercise.
 */
export type ClubGate =
  | { readonly allow: true }
  | { readonly allow: false; readonly redirectTo: string; readonly reason: GateReason }

/**
 * Why somebody was turned away. Carried so the destination can say something true when they arrive,
 * and so a test asserts on the reason rather than on a path that may be renamed.
 */
export type GateReason =
  /** No club membership at all. A produce-market customer, or an account that never joined. */
  | 'not-a-member'
  /** Owes money, and paying fixes it. */
  | 'owes-payment'
  /** Blocked for a reason a payment does not settle. */
  | 'not-settled-by-payment'

/** Where an unpaid member is sent. The same screen sign-up reaches, which now works signed in. */
export const PAY_PATH = '/pay'

/** Where anybody the club has nothing for is sent. */
export const FRONT_DOOR = '/'

/**
 * The statuses a membership payment actually resolves.
 *
 * Kept in step with `ACTIVATABLE_STATUSES` in `app/core/payments/services.py`, which is what the
 * `/payments/me/checkout` endpoint enforces. This copy decides where to *send* somebody; that one
 * decides whether to *sell* them anything, and the API is the one that counts. A drift shows up as
 * a member sent to a payment screen that refuses them, which is why the endpoint answers 409 with a
 * reason rather than an empty page.
 */
const PAYABLE: ReadonlySet<string> = new Set(['pending_payment', 'suspended', 'lapsed'])

/**
 * Whether this account may use the club, and where it goes if not.
 *
 * **Nobody is sent to a payment screen that cannot help them.** A membership awaiting the club's
 * verification, or a placeholder, is not fixed by money, and offering a checkout there invites a
 * payment for something the payer does not thereby get. Those go to the front door instead. The
 * distinction is the reason this returns a reason rather than a boolean.
 */
export const clubGateFor = (user: Pick<User, 'membership_status'>): ClubGate => {
  const status = user.membership_status

  if (status === null || status === undefined) {
    return { allow: false, redirectTo: FRONT_DOOR, reason: 'not-a-member' }
  }

  if (status === 'active') return { allow: true }

  if (PAYABLE.has(status)) {
    return { allow: false, redirectTo: PAY_PATH, reason: 'owes-payment' }
  }

  return { allow: false, redirectTo: FRONT_DOOR, reason: 'not-settled-by-payment' }
}

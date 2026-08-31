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
 *
 * **Four now, where there were three.** `not-settled-by-payment` was doing duty for three unrelated
 * situations — a membership the club has blocked, one it has not finished checking, and a
 * placeholder — and sent all of them to the marketing landing page with no explanation. A reason
 * exists so the destination can say something true, and one reason covering three cases could only
 * say something vague.
 */
export type GateReason =
  /** No club membership at all. A produce-market customer, or an account that never joined. */
  | 'not-a-member'
  /** Owes money, and paying fixes it. */
  | 'owes-payment'
  /**
   * The club has blocked this membership. Conduct, not money — `suspend_member` on the API side.
   * A payment does not lift it and is not offered; only `reinstate_member` lifts it.
   */
  | 'blocked'
  /** The club has the application and has not finished checking it. Nothing to pay, nothing to do. */
  | 'awaiting-verification'
  /** Anything else the gate does not recognise. Fails closed. */
  | 'not-settled-by-payment'

/** Where an unpaid member is sent. The same screen sign-up reaches, which now works signed in. */
export const PAY_PATH = '/pay'

/**
 * Where a member who cannot use the club is sent, and told why.
 *
 * **Not the front door.** A blocked member used to be redirected to the marketing landing page,
 * which says nothing about their situation and offers them a sign-up form they cannot use. This
 * screen names the situation and carries the support address, which is the only way somebody can
 * ask for a block to be looked at again.
 */
export const BLOCKED_PATH = '/blocked'

/** Where anybody the club has nothing for is sent. */
export const FRONT_DOOR = '/'

/**
 * The statuses a membership payment actually resolves. **The two that are about money.**
 *
 * Kept in step with `ACTIVATABLE_STATUSES` in `app/core/payments/services.py`, which is what the
 * `/payments/me/checkout` endpoint enforces. This copy decides where to *send* somebody; that one
 * decides whether to *sell* them anything, and the API is the one that counts. A drift shows up as
 * a member sent to a payment screen that refuses them, which is why the endpoint answers 409 with a
 * reason rather than an empty page.
 *
 * **`suspended` was in here and has been removed on both sides.** It is a conduct block written by
 * `suspend_member`; non-payment is `lapsed`, written by `lapse_overdue`, which refuses to touch a
 * suspension. So a suspended member was being sent to a checkout, and paying it restored them to
 * Active automatically — around `reinstate_member`, the function that exists so that lifting a
 * block is a deliberate act. See the note on `ACTIVATABLE_STATUSES`.
 */
const PAYABLE: ReadonlySet<string> = new Set(['pending_payment', 'lapsed'])

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

  /*
   * No membership is not a block. A produce-market customer owes the club nothing and has done
   * nothing wrong, so they get the front door — which carries the invitation to join — rather than
   * a screen telling them to write to support about a membership they never had.
   */
  if (status === null || status === undefined) {
    return { allow: false, redirectTo: FRONT_DOOR, reason: 'not-a-member' }
  }

  if (status === 'active') return { allow: true }

  if (PAYABLE.has(status)) {
    return { allow: false, redirectTo: PAY_PATH, reason: 'owes-payment' }
  }

  if (status === 'suspended') {
    return { allow: false, redirectTo: BLOCKED_PATH, reason: 'blocked' }
  }

  if (status === 'pending') {
    return { allow: false, redirectTo: BLOCKED_PATH, reason: 'awaiting-verification' }
  }

  /*
   * `sharing` and anything Django has added since this bundle was built. Both go to the blocked
   * screen rather than the front door: its generic wording is true of any membership the club
   * cannot open, and it gives somebody an address to write to. A placeholder cannot hold a session
   * so never arrives here at all — C6.
   */
  return { allow: false, redirectTo: BLOCKED_PATH, reason: 'not-settled-by-payment' }
}

import { describe, expect, it } from 'vitest'

import { clubGateFor, FRONT_DOOR, PAY_PATH } from './club-membership'

/*
 * The gate in front of the club, and the one rule in it that is easy to get wrong: a member who
 * owes money is sent somewhere that takes it, and a member blocked for any other reason is not.
 */

describe('clubGateFor', () => {
  it('lets an active membership through', () => {
    expect(clubGateFor({ membership_status: 'active' })).toEqual({ allow: true })
  })

  it.each(['pending_payment', 'lapsed', 'suspended'] as const)(
    'sends a %s membership to pay, because paying fixes it',
    (status) => {
      expect(clubGateFor({ membership_status: status })).toEqual({
        allow: false,
        redirectTo: PAY_PATH,
        reason: 'owes-payment',
      })
    },
  )

  it('does not send a membership awaiting verification to pay', () => {
    /*
     * The club has not decided about this person yet, and money does not settle that question.
     * Sending them to a checkout would take a payment for something they do not thereby get —
     * `payments/services.ACTIVATABLE_STATUSES` refuses it on the API side for the same reason.
     */
    expect(clubGateFor({ membership_status: 'pending' })).toEqual({
      allow: false,
      redirectTo: FRONT_DOOR,
      reason: 'not-settled-by-payment',
    })
  })

  it('does not send a placeholder to pay', () => {
    // A sharing member is not a person and pays for nothing — C6. It also cannot sign in, so this
    // is unreachable in practice; the gate refuses it anyway rather than relying on that.
    expect(clubGateFor({ membership_status: 'sharing' })).toEqual({
      allow: false,
      redirectTo: FRONT_DOOR,
      reason: 'not-settled-by-payment',
    })
  })

  it('sends an account with no membership to the front door, not to pay', () => {
    /*
     * A produce-market customer. They owe the club nothing, and a payment screen would be an
     * invitation to buy a membership they never asked for.
     */
    expect(clubGateFor({ membership_status: null })).toEqual({
      allow: false,
      redirectTo: FRONT_DOOR,
      reason: 'not-a-member',
    })
  })

  it('treats an unknown status as not settled by payment', () => {
    // Fails closed. A status this bundle has not heard of is one Django added, and guessing that
    // money fixes it is the guess that costs somebody money.
    expect(
      clubGateFor({ membership_status: 'something_new' as never }),
    ).toEqual({
      allow: false,
      redirectTo: FRONT_DOOR,
      reason: 'not-settled-by-payment',
    })
  })
})

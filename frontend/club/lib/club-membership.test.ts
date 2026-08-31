import { describe, expect, it } from 'vitest'

import { BLOCKED_PATH, clubGateFor, FRONT_DOOR, PAY_PATH } from './club-membership'

/*
 * The gate in front of the club, and the rule in it that is easy to get wrong: a member who owes
 * money is sent somewhere that takes it, and a member blocked for any other reason is not sent
 * there at all.
 */

describe('clubGateFor', () => {
  it('lets an active membership through', () => {
    expect(clubGateFor({ membership_status: 'active' })).toEqual({ allow: true })
  })

  it.each(['pending_payment', 'lapsed'] as const)(
    'sends a %s membership to pay, because paying fixes it',
    (status) => {
      expect(clubGateFor({ membership_status: status })).toEqual({
        allow: false,
        redirectTo: PAY_PATH,
        reason: 'owes-payment',
      })
    },
  )

  it('sends a suspended membership to the blocked screen, never to pay', () => {
    /*
     * **The regression this test exists for.** `suspended` used to sit in `PAYABLE`, so a member the
     * club had blocked for conduct was sent to a checkout — and `ACTIVATABLE_STATUSES` accepted the
     * payment, restoring them to Active around `reinstate_member`. Non-payment is `lapsed`; a
     * suspension is a decision, and money does not reverse a decision.
     */
    expect(clubGateFor({ membership_status: 'suspended' })).toEqual({
      allow: false,
      redirectTo: BLOCKED_PATH,
      reason: 'blocked',
    })
  })

  it('sends a membership awaiting verification to the blocked screen with its own reason', () => {
    /*
     * Not to pay — the club has not decided about this person and money does not settle that
     * question; `ACTIVATABLE_STATUSES` refuses it on the API side for the same reason. And not to
     * the front door either, which is where this used to go: "we are still checking" is something
     * the member can be told, and the landing page cannot tell them it.
     */
    expect(clubGateFor({ membership_status: 'pending' })).toEqual({
      allow: false,
      redirectTo: BLOCKED_PATH,
      reason: 'awaiting-verification',
    })
  })

  it('sends a placeholder to the blocked screen', () => {
    // A sharing member is not a person and pays for nothing — C6. It also cannot sign in, so this
    // is unreachable in practice; the gate refuses it anyway rather than relying on that.
    expect(clubGateFor({ membership_status: 'sharing' })).toEqual({
      allow: false,
      redirectTo: BLOCKED_PATH,
      reason: 'not-settled-by-payment',
    })
  })

  it('sends an account with no membership to the front door, not to pay and not to blocked', () => {
    /*
     * A produce-market customer. They owe the club nothing and have done nothing wrong, so a
     * payment screen would be an invitation to buy a membership they never asked for, and the
     * blocked screen would tell them to write to support about a membership they never had. The
     * front door carries the invitation to join, which is the only thing they might want.
     */
    expect(clubGateFor({ membership_status: null })).toEqual({
      allow: false,
      redirectTo: FRONT_DOOR,
      reason: 'not-a-member',
    })
  })

  it('treats an unknown status as not settled by payment', () => {
    // Fails closed, and now fails closed somewhere that says something. A status this bundle has
    // not heard of is one Django added, and guessing that money fixes it is the guess that costs
    // somebody money.
    expect(clubGateFor({ membership_status: 'something_new' as never })).toEqual({
      allow: false,
      redirectTo: BLOCKED_PATH,
      reason: 'not-settled-by-payment',
    })
  })

  it('never sends anybody to pay for a reason other than owing money', () => {
    /*
     * The property behind every case above, asserted as a property so a status added later cannot
     * quietly acquire a checkout by being appended to the wrong set.
     */
    const statuses = [
      'active',
      'pending',
      'pending_payment',
      'suspended',
      'lapsed',
      'sharing',
    ] as const

    for (const status of statuses) {
      const gate = clubGateFor({ membership_status: status })
      if (!gate.allow && gate.redirectTo === PAY_PATH) {
        expect(gate.reason, status).toBe('owes-payment')
      }
    }
  })
})

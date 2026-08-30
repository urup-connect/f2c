import { describe, expect, test } from 'vitest'

import { member } from '@/test-support/members'
import { MEMBER_REFUSALS } from './member-register-content'
import {
  MEMBER_ROLES,
  MEMBER_STATUSES,
  canReinstate,
  canSignIn,
  canSuspend,
  checkMember,
  disclosureReasonIsEnough,
  labelFor,
  memberHasChanges,
  memberInputFrom,
  refusalFor,
  refusalsFromApi,
  type MemberInput,
} from './member-register'

/*
 * The rules the register's screens apply before they ask the API.
 *
 * Every one of them is a rule the API enforces too, so what is tested here is
 * that the browser reaches the *same* answer — not that it reaches an answer of
 * its own. Where the two deliberately differ, the test says so.
 */

const input = (overrides: Partial<MemberInput> = {}): MemberInput => ({
  firstName: 'Thabo',
  lastName: 'Mahlangu',
  nickname: 'Thabo',
  email: 'thabo@example.com',
  mobile: '082 123 4567',
  ...overrides,
})

describe('checkMember', () => {
  test('accepts a complete record and normalises it', () => {
    const checked = checkMember(input({ email: 'THABO@Example.COM' }))

    expect(checked.status).toBe('valid')
    if (checked.status !== 'valid') return

    // The stored form on both: lower-cased whole, and `+27` with nine digits.
    // The browser sends what `User.save` would have written anyway, so a save
    // that changes nothing is visibly a save that changes nothing.
    expect(checked.submission.email).toBe('thabo@example.com')
    expect(checked.submission.mobile).toBe('+27821234567')
  })

  test('collects every refusal rather than stopping at the first', () => {
    // A form that reports one problem at a time is a form somebody submits four
    // times, and each of those is a round trip.
    const checked = checkMember(
      input({ firstName: '', lastName: '', email: 'not-an-address', mobile: '' }),
    )

    expect(checked.status).toBe('invalid')
    if (checked.status !== 'invalid') return

    expect(checked.refusals.map((refusal) => refusal.field)).toEqual([
      'first_name',
      'last_name',
      'email',
      'mobile',
    ])
  })

  test('accepts a blank nickname, and does not call it taken', () => {
    // Clearing one leaves the member without a nickname, which `display_name`
    // already falls back from. Sign-up requires one because a joining member is
    // choosing how the club will see them; an administrator correcting a record
    // is not.
    const checked = checkMember(input({ nickname: '   ' }))

    expect(checked.status).toBe('valid')
    if (checked.status !== 'valid') return
    expect(checked.submission.nickname).toBe('')
  })

  test('refuses a nickname that is present and malformed', () => {
    const checked = checkMember(input({ nickname: 'ab' }))

    expect(checked.status).toBe('invalid')
    if (checked.status !== 'invalid') return
    expect(refusalFor(checked.refusals, 'nickname')).toBe(MEMBER_REFUSALS.nicknameLength)
  })

  test('refuses a reserved nickname in its own words', () => {
    // Not folded into "already taken". The two are different facts, and an
    // administrator is the one person who can act on the difference.
    const checked = checkMember(input({ nickname: 'admin' }))

    expect(checked.status).toBe('invalid')
    if (checked.status !== 'invalid') return
    expect(refusalFor(checked.refusals, 'nickname')).toBe(MEMBER_REFUSALS.nicknameReserved)
  })

  test('refuses a blank mobile number, unlike the member’s own profile form', () => {
    /*
     * The one asymmetry with `checkProfile`, and it is deliberate. A member
     * clearing their own number is saying "I no longer have that handset", which
     * is an answer. An administrator blanking somebody else's is throwing away a
     * contact detail on their behalf, which is not.
     */
    const checked = checkMember(input({ mobile: '' }))

    expect(checked.status).toBe('invalid')
    if (checked.status !== 'invalid') return
    expect(refusalFor(checked.refusals, 'mobile')).toBe(MEMBER_REFUSALS.mobileMissing)
  })

  test('refuses a landline in its own words', () => {
    const checked = checkMember(input({ mobile: '086 123 4567' }))

    expect(checked.status).toBe('invalid')
    if (checked.status !== 'invalid') return
    expect(refusalFor(checked.refusals, 'mobile')).toBe(MEMBER_REFUSALS.mobileNotAMobile)
  })

  test('says nothing about whether another account holds any of these', () => {
    // The three the browser cannot answer. They come back from the API as
    // per-field refusals and are rendered through the same list this produces.
    const checked = checkMember(input())

    expect(checked.status).toBe('valid')
  })
})

describe('refusalsFromApi', () => {
  test('turns the API’s field map into this screen’s refusal list', () => {
    const refusals = refusalsFromApi({
      email: ['Another account already uses that email address.'],
    })

    expect(refusals).toEqual([
      { field: 'email', message: 'Another account already uses that email address.' },
    ])
  })

  test('joins several messages against one field', () => {
    const refusals = refusalsFromApi({ nickname: ['One.', 'Two.'] })

    expect(refusals[0].message).toBe('One. Two.')
  })

  test('drops a field this build does not know', () => {
    // Rendered against nothing is worse than not rendered: `detail` is always
    // shown as well, so the sentence is never lost even when its field is.
    expect(refusalsFromApi({ invented_column: ['No.'] })).toEqual([])
  })

  test('drops a known field carrying no message', () => {
    expect(refusalsFromApi({ email: [] })).toEqual([])
  })

  test('keeps the identity-disclosure reason, which is not on the record form', () => {
    // The identity card keys its refusal to `reason`. Dropping it would leave
    // that card with a `detail` and no field to mark.
    expect(refusalsFromApi({ reason: ['Say why.'] })).toHaveLength(1)
  })
})

describe('memberHasChanges', () => {
  test('is false for a form that has not been touched', () => {
    const record = member()

    expect(memberHasChanges(memberInputFrom(record), record)).toBe(false)
  })

  test('is false for a change the club would not store', () => {
    /*
     * A trailing space on a surname, and a mobile number retyped in the local
     * form. Neither changes what is written, and a save button that lights up
     * for them is a button promising a change it will not make.
     */
    const record = member()

    expect(
      memberHasChanges(
        { ...memberInputFrom(record), lastName: 'Mahlangu  ', mobile: '082 123 4567' },
        record,
      ),
    ).toBe(false)
  })

  test('is true for a real change', () => {
    const record = member()

    expect(
      memberHasChanges({ ...memberInputFrom(record), lastName: 'Ncube' }, record),
    ).toBe(true)
  })

  test('is true for a form that does not yet validate', () => {
    // It cannot be normalised, so the honest answer is "something is different",
    // and pressing save is how the administrator learns what.
    const record = member()

    expect(memberHasChanges({ ...memberInputFrom(record), email: 'nope' }, record)).toBe(
      true,
    )
  })

  test('sees a nickname being cleared', () => {
    const record = member()

    expect(memberHasChanges({ ...memberInputFrom(record), nickname: '' }, record)).toBe(
      true,
    )
  })
})

describe('canSignIn', () => {
  test('is true for active alone', () => {
    // `User.is_active` is derived from exactly this, with a check constraint
    // holding the two together. Five of the six statuses block a sign-in.
    expect(canSignIn('active')).toBe(true)

    for (const status of MEMBER_STATUSES.filter((choice) => choice.value !== 'active')) {
      expect(canSignIn(status.value), status.value).toBe(false)
    }
  })
})

describe('canSuspend', () => {
  test('is true for an ordinary active account', () => {
    expect(canSuspend(member(), 'admin-1')).toBe(true)
  })

  test('is false for the viewer’s own account', () => {
    // Suspension signs the caller out on the way and they cannot sign back in to
    // undo it. The API refuses it too; this is what stops the button being
    // offered at all, so nobody discovers the rule by pressing it.
    expect(canSuspend(member({ id: 'admin-1' }), 'admin-1')).toBe(false)
  })

  test('is false for an account that is already suspended', () => {
    expect(canSuspend(member({ status: 'suspended' }), 'admin-1')).toBe(false)
  })

  test('is false for a record the API says is not editable', () => {
    expect(canSuspend(member({ editable: false }), 'admin-1')).toBe(false)
  })
})

describe('canReinstate', () => {
  test('is true only for a suspended account', () => {
    expect(canReinstate(member({ status: 'suspended' }))).toBe(true)
  })

  test('is false for an unpaid account', () => {
    // Nothing records where an account sat before a suspension, so reinstatement
    // cannot restore it -- and Pending payment is not a block the club placed.
    expect(canReinstate(member({ status: 'pending_payment' }))).toBe(false)
  })

  test('is false for an erased account, whatever its status', () => {
    expect(canReinstate(member({ status: 'suspended', editable: false }))).toBe(false)
  })
})

describe('disclosureReasonIsEnough', () => {
  test('refuses a reason nobody could review', () => {
    expect(disclosureReasonIsEnough('ok')).toBe(false)
    expect(disclosureReasonIsEnough('          ')).toBe(false)
  })

  test('accepts one that says something', () => {
    expect(disclosureReasonIsEnough('Verifying against the document.')).toBe(true)
  })
})

describe('labelFor', () => {
  test('answers a known value with its label', () => {
    expect(labelFor(MEMBER_ROLES, 'sharing_member')).toBe('Sharing member')
  })

  test('answers an unknown value with itself', () => {
    // A status this build has not heard of still renders. The rows carry their
    // own labels from the API, so this only ever feeds the filters.
    expect(labelFor(MEMBER_STATUSES, 'invented')).toBe('invented')
  })
})

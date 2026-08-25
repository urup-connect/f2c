import { describe, expect, test } from 'vitest'
import type { User } from './api'
import {
  detailRows,
  formatIsoDate,
  fullName,
  greetingName,
  membershipStanding,
} from './club-account'
import { MEMBERSHIP_CARD } from './club-content'

const MEMBER: User = {
  id: '2b0d3a2c-6e0f-4a3f-8f4b-9b6c1f0d1a11',
  email: 'thandi@example.co.za',
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  mobile: '+27821234567',
  display_name: 'greenfingers',
  date_of_birth: '1990-03-15',
  date_of_birth_verified_at: null,
  status: 'active',
  role: 'member',
  permissions: [],
  is_staff: false,
}

/** An erased account: the row survives, every name is cleared, the address is gone. */
const ERASED: User = {
  ...MEMBER,
  email: null,
  first_name: '',
  last_name: '',
  nickname: '',
  mobile: '',
  display_name: '',
  date_of_birth: null,
  status: 'inactive',
}

const rowFor = (user: User, key: string) => detailRows(user).find((row) => row.key === key)

/*
 * `formatIsoDate` outlives the row that used it: the profile screen formats the same date. Kept
 * here rather than moved, because this is the module that exports it.
 */
describe('formatIsoDate', () => {
  test('writes a date the way a South African reader writes one', () => {
    expect(formatIsoDate('1990-03-15')).toBe('15 March 1990')
  })

  test('reads nothing held as nothing held', () => {
    expect(formatIsoDate(null)).toBeNull()
  })

  test('reads an empty string as nothing held', () => {
    expect(formatIsoDate('')).toBeNull()
  })

  test('refuses to show what a date library says when it gives up', () => {
    expect(formatIsoDate('the fifteenth')).toBeNull()
  })
})

describe('fullName', () => {
  test('joins the two parts', () => {
    expect(fullName(MEMBER)).toBe('Thandi Mokoena')
  })

  test('leaves no stray space when only one part is on file', () => {
    expect(fullName({ ...MEMBER, last_name: '' })).toBe('Thandi')
    expect(fullName({ ...MEMBER, first_name: '' })).toBe('Mokoena')
  })

  test('is nothing at all when neither part is', () => {
    expect(fullName(ERASED)).toBeNull()
  })

  test('treats whitespace as nothing', () => {
    expect(fullName({ ...MEMBER, first_name: '  ', last_name: '  ' })).toBeNull()
  })
})

describe('detailRows', () => {
  test('reads in the order the card shows them', () => {
    expect(detailRows(MEMBER).map((row) => row.key)).toEqual([
      'name',
      'nickname',
      'email',
      'mobile',
    ])
  })

  test('carries what the club holds', () => {
    expect(rowFor(MEMBER, 'nickname')?.value).toBe('greenfingers')
    expect(rowFor(MEMBER, 'email')?.value).toBe('thandi@example.co.za')
    expect(rowFor(MEMBER, 'mobile')?.value).toBe('+27821234567')
  })

  test('does not carry the date of birth, which belongs to the profile screen', () => {
    /*
     * It was the last row here, and the reasoning for that placement -- the one thing on the card
     * nobody can change by asking -- is what moved it. A card whose every row a member can now go
     * and correct should not have one row that behaves differently; the honest home for a
     * read-only fact taken off an identity document is beside the identity number it came from.
     *
     * Asserted on the whole serialised row set rather than on one lookup, so a row added back
     * under a different key fails this too.
     */
    expect(rowFor(MEMBER, 'dateOfBirth')).toBeUndefined()
    expect(JSON.stringify(detailRows(MEMBER))).not.toMatch(/birth|1990/i)
  })

  test('says a blank field is blank rather than rendering an empty line', () => {
    // Never an empty string: a screen has to be able to tell "nothing held" from
    // "this failed to draw".
    for (const row of detailRows(ERASED)) {
      expect(row.value).toBeNull()
    }
  })

  test('never carries the identity number', () => {
    // Encrypted at rest, absent from UserOut, and no business on a home page.
    const serialised = JSON.stringify(detailRows(MEMBER))

    expect(serialised).not.toMatch(/id_number/i)
  })
})

describe('membershipStanding', () => {
  test('describes an active membership', () => {
    expect(membershipStanding('active')).toEqual({
      label: MEMBERSHIP_CARD.statusLabels.active,
      note: MEMBERSHIP_CARD.statusNotes.active,
    })
  })

  test.each(['pending', 'pending_payment', 'suspended', 'inactive', 'sharing'] as const)(
    'has something to say about %s, which no session should reach',
    (status) => {
      const standing = membershipStanding(status)

      expect(standing.label.length).toBeGreaterThan(0)
      expect(standing.note.length).toBeGreaterThan(0)
    },
  )
})

describe('greetingName', () => {
  test('uses the name Django decided to show', () => {
    expect(greetingName(MEMBER)).toBe('greenfingers')
  })

  test('has nothing for an account with every name cleared', () => {
    expect(greetingName(ERASED)).toBeNull()
  })
})

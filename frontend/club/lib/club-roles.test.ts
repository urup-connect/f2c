import { describe, expect, test } from 'vitest'
import {
  CLUB_HOMES,
  CLUB_HOME_PATHS,
  CLUB_ROLES,
  ROLE_LABELS,
  clubHomeFor,
  isClubRole,
} from './club-roles'

/* design/features/roles-and-permissions.md section 12. */

describe('CLUB_ROLES', () => {
  test('holds the three roles that sign in', () => {
    expect(CLUB_ROLES).toEqual(['admin', 'cultivator', 'member'])
  })

  test('gives every one of them a home and a label', () => {
    for (const role of CLUB_ROLES) {
      expect(CLUB_HOMES[role]).toMatch(/^\//)
      expect(ROLE_LABELS[role].length).toBeGreaterThan(0)
    }
  })

  test('sends no two roles to the same place', () => {
    expect(new Set(CLUB_HOME_PATHS).size).toBe(CLUB_HOME_PATHS.length)
  })
})

describe('isClubRole', () => {
  test.each(CLUB_ROLES)('recognises %s', (role) => {
    expect(isClubRole(role)).toBe(true)
  })

  test('refuses the sharing member, which never signs in', () => {
    expect(isClubRole('sharing_member')).toBe(false)
  })

  test.each([undefined, null, '', 'Admin', 42, {}])('refuses %o', (value) => {
    expect(isClubRole(value)).toBe(false)
  })
})

describe('clubHomeFor', () => {
  test('sends an administrator to the administration area', () => {
    expect(clubHomeFor('admin')).toBe('/admin')
  })

  test('sends a cultivator to the cultivation area', () => {
    expect(clubHomeFor('cultivator')).toBe('/cultivator')
  })

  test('sends a member to the member area', () => {
    expect(clubHomeFor('member')).toBe('/member')
  })

  test('gives a sharing member nowhere to go', () => {
    // An identity, not an actor: no session can belong to one, and a home it cannot
    // use would be worse than the front door.
    expect(clubHomeFor('sharing_member' as never)).toBeNull()
  })
})

import { describe, expect, test } from 'vitest'
import {
  NICKNAME_MAX_LENGTH,
  NICKNAME_MIN_LENGTH,
  RESERVED_NICKNAMES,
  checkNickname,
  nicknameKey,
} from './nickname'
import type { NicknameCheck } from './nickname'

/*
 * design/features/member-details-at-sign-up.md criteria 12 to 18.
 *
 * The nickname is the one field that is an identity claim against other members, which is why it
 * is ASCII while the name fields are not: a Cyrillic "а" wearing an existing member's name is an
 * attack, and restricting the alphabet removes the whole class of it. See section 6.6.
 */

const accepted = (result: NicknameCheck) => (result.status === 'valid' ? result.nickname : null)
const refusal = (result: NicknameCheck) => (result.status === 'invalid' ? result.reason : null)

describe('a nickname the rule accepts', () => {
  // Criterion 12.
  test.each([
    ['letters only', 'grower'],
    ['mixed case', 'GreenThumb'],
    ['a digit inside', 'grower7'],
    ['a hyphen inside', 'green-thumb'],
    ['an underscore inside', 'green_thumb'],
    ['the minimum length', 'abc'],
    ['the maximum length', 'a'.repeat(NICKNAME_MAX_LENGTH)],
  ])('accepts %s', (_label, nickname) => {
    expect(accepted(checkNickname(nickname))).toBe(nickname)
  })

  // Criterion 18.
  test('preserves the case the visitor typed', () => {
    expect(accepted(checkNickname('GreenThumb'))).toBe('GreenThumb')
  })

  test('trims surrounding whitespace rather than refusing it', () => {
    expect(accepted(checkNickname('  grower  '))).toBe('grower')
  })

  test('runs from 3 to 20 characters', () => {
    expect(NICKNAME_MIN_LENGTH).toBe(3)
    expect(NICKNAME_MAX_LENGTH).toBe(20)
  })
})

describe('the uniqueness key', () => {
  // Criterion 17.
  test('folds letter case, so two nicknames differing only by case are the same one', () => {
    expect(nicknameKey('GreenThumb')).toBe(nicknameKey('greenthumb'))
    expect(nicknameKey('GROWER')).toBe('grower')
  })

  test('does not fold separators, so a hyphen makes a different nickname', () => {
    expect(nicknameKey('green-thumb')).not.toBe(nicknameKey('greenthumb'))
  })

  test('is trimmed, so surrounding whitespace cannot make a second one', () => {
    expect(nicknameKey('  grower ')).toBe('grower')
  })
})

describe('a nickname of the wrong length', () => {
  // Criterion 13.
  test.each([
    ['one character', 'a'],
    ['two characters', 'ab'],
  ])('refuses %s', (_label, nickname) => {
    expect(refusal(checkNickname(nickname))).toBe('length')
  })

  test('refuses one character over the maximum', () => {
    expect(refusal(checkNickname('a'.repeat(NICKNAME_MAX_LENGTH + 1)))).toBe('length')
  })

  test('refuses an empty nickname as missing rather than as a length', () => {
    expect(refusal(checkNickname(''))).toBe('missing')
    expect(refusal(checkNickname('   '))).toBe('missing')
  })
})

describe('a nickname outside the permitted alphabet', () => {
  // Criterion 14.
  test.each([
    ['a space', 'green thumb'],
    ['an accented letter', 'grówer'],
    ['a Cyrillic homoglyph', 'grоwer'],
    ['an emoji', 'grower🌱'],
    ['a full stop', 'grower.7'],
    ['an at sign', 'grower@club'],
  ])('refuses %s', (_label, nickname) => {
    expect(refusal(checkNickname(nickname))).toBe('unexpected-characters')
  })
})

describe('a nickname of the wrong shape', () => {
  // Criterion 15.
  test.each([
    ['starting with a digit', '7grower'],
    ['starting with a hyphen', '-grower'],
    ['starting with an underscore', '_grower'],
    ['ending with a hyphen', 'grower-'],
    ['ending with an underscore', 'grower_'],
    ['two hyphens in a row', 'green--thumb'],
    ['two underscores in a row', 'green__thumb'],
    ['a hyphen then an underscore', 'green-_thumb'],
  ])('refuses %s', (_label, nickname) => {
    expect(refusal(checkNickname(nickname))).toBe('shape')
  })
})

describe('a reserved nickname', () => {
  // Criterion 16.
  test.each([
    ['admin', 'admin'],
    ['in capitals', 'ADMIN'],
    ['in mixed case', 'Support'],
    ['the club itself', 'cultivators'],
    ['a route name', 'signup'],
  ])('refuses %s as unavailable', (_label, nickname) => {
    expect(refusal(checkNickname(nickname))).toBe('unavailable')
  })

  test('holds every reserved name in its comparable form already', () => {
    // A reserved name that is not itself lower case would never match. Guard the list, not the code.
    for (const reserved of RESERVED_NICKNAMES) {
      expect(reserved).toBe(reserved.toLowerCase())
    }
  })

  test('reserves the names that let a member impersonate the club', () => {
    for (const reserved of ['admin', 'support', 'moderator', 'cultivators', 'collective']) {
      expect(RESERVED_NICKNAMES).toContain(reserved)
    }
  })
})

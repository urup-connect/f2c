import { describe, expect, test } from 'vitest'
import { PROFILE_COPY } from './club-content'
import {
  UNREADABLE_ID_NUMBER,
  formatProfileDate,
  identityLines,
  initials,
} from './profile-display'

/*
 * How the read-only half of the profile reads.
 *
 * The tests that matter here are the three-state ones. An identity number is held-and-readable,
 * not-held, or held-and-unreadable, and collapsing the third into either of the others misleads a
 * member: told the club holds no document when it holds one it cannot read, they will send it again
 * for no reason. The same applies to a date of birth that nobody has checked against a document,
 * which is the *normal* state and must not read as a fault.
 */

const HELD = {
  date_of_birth: '1980-01-01',
  date_of_birth_verified_at: '2026-08-12T09:30:00Z',
  has_id_number: true,
  id_number_masked: '*********9087',
}

const NAMES = {
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  email: 'thandi@example.co.za',
}

describe('initials', () => {
  test('takes one letter from each name', () => {
    expect(initials(NAMES)).toBe('TM')
  })

  test('takes one letter when only one name is on file', () => {
    expect(initials({ ...NAMES, last_name: '' })).toBe('T')
    expect(initials({ ...NAMES, first_name: '' })).toBe('M')
  })

  test('falls back to the nickname, then the address', () => {
    const noNames = { ...NAMES, first_name: '', last_name: '' }

    expect(initials(noNames)).toBe('G')
    expect(initials({ ...noNames, nickname: '' })).toBe('T')
  })

  test('is never empty, even for an erased account', () => {
    // A blank circle where a face should be reads as an image that failed to load. The whole point
    // of initials is to be recognisably deliberate.
    const erased = { first_name: '', last_name: '', nickname: '', email: null }

    expect(initials(erased).length).toBeGreaterThan(0)
  })

  test('treats whitespace as nothing', () => {
    expect(initials({ ...NAMES, first_name: '  ', last_name: '  ' })).toBe('G')
  })

  test('yields a whole character for a name outside the BMP', () => {
    // The first UTF-16 unit of an astral character is half of one, and rendering half a surrogate
    // pair produces a replacement glyph.
    expect([...initials({ ...NAMES, first_name: '𝒜lice', last_name: 'Bee' })]).toHaveLength(2)
  })

  test('upper-cases, so a lower-cased record does not look like a mistake', () => {
    expect(initials({ ...NAMES, first_name: 'thandi', last_name: 'mokoena' })).toBe('TM')
  })
})

describe('formatProfileDate', () => {
  test('writes a date the way a South African reader writes one', () => {
    expect(formatProfileDate('1980-01-01')).toBe('1 January 1980')
  })

  test('does not shift the day into the one before it', () => {
    /*
     * The bug this exists to catch. An ISO date has no time in it, so `new Date` reads it as
     * midnight UTC -- and formatted in a timezone behind UTC that is the previous day. A member
     * travelling would watch their own birthday move.
     */
    expect(formatProfileDate('1980-01-01')).toContain('1 January')
    expect(formatProfileDate('2000-03-01')).toBe('1 March 2000')
  })

  test('is nothing at all when the club holds nothing', () => {
    expect(formatProfileDate(null)).toBeNull()
    expect(formatProfileDate('')).toBeNull()
  })

  test('is nothing rather than the string a date library gives up with', () => {
    expect(formatProfileDate('the first of January')).toBeNull()
  })
})

describe('identityLines', () => {
  const lineFor = (profile: Parameters<typeof identityLines>[0], key: string) =>
    identityLines(profile).find((line) => line.key === key)

  test('reads as two lines, date first', () => {
    expect(identityLines(HELD).map((line) => line.key)).toEqual(['dateOfBirth', 'idNumber'])
  })

  test('shows the masked number as the API sent it', () => {
    // Trusted verbatim. Masking here as well would be a second implementation of a rule that has
    // already run, and the two would eventually disagree about how much to show.
    expect(lineFor(HELD, 'idNumber')?.value).toBe('*********9087')
  })

  test('never carries a whole identity number', () => {
    // The plaintext has no representation on this screen. Asserted on the serialised lines so an
    // extra field would fail it too.
    const serialised = JSON.stringify(identityLines(HELD))

    expect(serialised).not.toMatch(/8001015009087/)
  })

  test('says a number is absent rather than leaving an empty line', () => {
    const none = { ...HELD, has_id_number: false, id_number_masked: '' }

    expect(lineFor(none, 'idNumber')?.value).toBeNull()
    expect(lineFor(none, 'idNumber')?.note).toBeNull()
  })

  test('distinguishes a number it cannot read from one it does not hold', () => {
    /*
     * The three-state case. A member told the club holds no document when it holds one it cannot
     * read will send it again for no reason, so the unreadable state gets a sentence of its own.
     */
    const unreadable = { ...HELD, id_number_masked: UNREADABLE_ID_NUMBER }

    expect(lineFor(unreadable, 'idNumber')?.value).toBeNull()
    expect(lineFor(unreadable, 'idNumber')?.note).toBe(PROFILE_COPY.identity.unreadable)
    // And is not the same sentence as "not on file", which is the confusion being avoided.
    expect(lineFor(unreadable, 'idNumber')?.note).not.toBe(
      lineFor({ ...HELD, has_id_number: false }, 'idNumber')?.note,
    )
  })

  test('explains the asterisks rather than leaving them to be guessed at', () => {
    // A run of asterisks is read out one at a time by a screen reader. The note is what says in
    // words that the hiding is deliberate.
    expect(lineFor(HELD, 'idNumber')?.note).toBe(PROFILE_COPY.identity.idNumberNote)
  })

  test('names the date the document was checked', () => {
    expect(lineFor(HELD, 'dateOfBirth')?.value).toBe('1 January 1980')
    expect(lineFor(HELD, 'dateOfBirth')?.note).toContain('12 August 2026')
  })

  test('says an unchecked date is unchecked, without reading as a fault', () => {
    // Registration checks no document -- a number that passes its check digit is a number that is
    // not a typo -- so this is the normal state for every member on the platform today.
    const unverified = { ...HELD, date_of_birth_verified_at: null }

    expect(lineFor(unverified, 'dateOfBirth')?.note).toBe(PROFILE_COPY.identity.unverified)
  })

  test('says nothing about verification when there is no date to verify', () => {
    const none = { ...HELD, date_of_birth: null, date_of_birth_verified_at: null }

    expect(lineFor(none, 'dateOfBirth')?.value).toBeNull()
    expect(lineFor(none, 'dateOfBirth')?.note).toBeNull()
  })
})

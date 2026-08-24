import { describe, expect, test } from 'vitest'
import {
  SA_ID_LENGTH,
  SA_ID_REFUSALS,
  checkSaIdNumber,
  filterSaIdInput,
  isSaIdRefusal,
} from './sa-id-number'
import type { SaIdCheck } from './sa-id-number'
import type { CalendarDate } from './age-gate'

/*
 * design/features/member-details-at-sign-up.md criteria 29 to 36.
 *
 * Every number below is invented and its check digit computed, never taken from anywhere. A
 * structurally valid ID number could in principle coincide with a real one, so these are
 * structural inputs only: nothing here identifies a person and this feature stores nothing.
 * See the fixture note in section 7 of the design doc.
 */

const date = (year: number, month: number, day: number): CalendarDate => ({ year, month, day })

/** The refusal, or null when the number was accepted. Narrows the union so tests stay typed. */
const refusal = (result: SaIdCheck) => (result.status === 'invalid' ? result.reason : null)

/** 15 March 1990, citizen, digit 12 of 8. The reference number for most cases below. */
const NINETEEN_NINETY = '9003155009082'
const DOB_1990 = date(1990, 3, 15)

describe('the refusal codes', () => {
  test('are narrowed from an arbitrary string', () => {
    expect(isSaIdRefusal('checksum')).toBe(true)
    expect(isSaIdRefusal('date-mismatch')).toBe(true)
    expect(isSaIdRefusal('nearly-right')).toBe(false)
    expect(isSaIdRefusal(13)).toBe(false)
    expect(isSaIdRefusal(undefined)).toBe(false)
  })

  test('are the full set the check can return', () => {
    expect([...SA_ID_REFUSALS]).toEqual([
      'missing',
      'length',
      'not-digits',
      'checksum',
      'date-mismatch',
      'not-recognised',
    ])
  })
})

describe('an ID number that passes every check', () => {
  // Criterion 34.
  test('is accepted, and carries nothing but the thirteen digits', () => {
    const result = checkSaIdNumber(NINETEEN_NINETY, DOB_1990)

    expect(result).toEqual({ status: 'valid', idNumber: NINETEEN_NINETY })
  })

  test('reveals no sex and no digit-12 value in its result', () => {
    // Criterion 34. The absence is asserted, not assumed: an added field would fail here.
    const result = checkSaIdNumber(NINETEEN_NINETY, DOB_1990)

    expect(Object.keys(result).sort()).toEqual(['idNumber', 'status'])
  })

  test('is thirteen digits long', () => {
    expect(SA_ID_LENGTH).toBe(13)
  })

  test('accepts a permanent resident, citizenship digit 1', () => {
    // Criterion 33. Permanent residents hold SA ID numbers and are members like any other.
    expect(checkSaIdNumber('9003155009181', DOB_1990)).toEqual({
      status: 'valid',
      idNumber: '9003155009181',
    })
  })

  test('accepts either conventional value of digit 12, because it is not read', () => {
    expect(checkSaIdNumber('9003155009090', DOB_1990).status).toBe('valid')
  })

  test('accepts a birth date of 29 February', () => {
    expect(checkSaIdNumber('0402295009086', date(2004, 2, 29)).status).toBe('valid')
  })
})

describe('the two-digit year', () => {
  /*
   * Criterion 32. The same six digits belong to two centuries and the number does not say which.
   * Both cases below pass, each against its own date of birth, which is the whole point: the
   * century is never guessed, only compared.
   */
  const AMBIGUOUS = '0708195009087'

  test('is accepted against a 2007 date of birth', () => {
    expect(checkSaIdNumber(AMBIGUOUS, date(2007, 8, 19)).status).toBe('valid')
  })

  test('is accepted against a 1907 date of birth', () => {
    expect(checkSaIdNumber(AMBIGUOUS, date(1907, 8, 19)).status).toBe('valid')
  })

  test('is refused against a date of birth in neither century', () => {
    expect(checkSaIdNumber(AMBIGUOUS, date(1908, 8, 19))).toEqual({
      status: 'invalid',
      reason: 'date-mismatch',
    })
  })
})

describe('separators', () => {
  // Criterion 36.
  test('are stripped wherever they fall, yielding the same thirteen digits', () => {
    const written = ['900315 5009 082', '900315-5009-082', '9003 155 009082', ' 9003155009082 ']

    for (const value of written) {
      expect(checkSaIdNumber(value, DOB_1990)).toEqual({
        status: 'valid',
        idNumber: NINETEEN_NINETY,
      })
    }
  })

  test('include the non-breaking space a copy-paste leaves behind', () => {
    expect(checkSaIdNumber('900315\u00a05009\u00a0082', DOB_1990).status).toBe('valid')
  })
})

describe('an ID number that is not there', () => {
  // Criterion 29, the missing case.
  test('is refused as missing when empty', () => {
    expect(checkSaIdNumber('', DOB_1990)).toEqual({ status: 'invalid', reason: 'missing' })
  })

  test('is refused as missing when only separators', () => {
    expect(checkSaIdNumber('  -  ', DOB_1990)).toEqual({ status: 'invalid', reason: 'missing' })
  })
})

describe('an ID number of the wrong shape', () => {
  // Criterion 30.
  test('is refused as digits only when it contains a letter', () => {
    expect(checkSaIdNumber('90031550090X2', DOB_1990)).toEqual({
      status: 'invalid',
      reason: 'not-digits',
    })
  })

  test('reports digits before length, because that is the more useful message', () => {
    // A value with letters is not a number of any length. Criterion 30 over criterion 29.
    expect(checkSaIdNumber('not an id number at all', DOB_1990)).toEqual({
      status: 'invalid',
      reason: 'not-digits',
    })
  })

  // Criterion 29.
  test('is refused as the wrong length when a digit short', () => {
    expect(checkSaIdNumber('900315500908', DOB_1990)).toEqual({
      status: 'invalid',
      reason: 'length',
    })
  })

  test('is refused as the wrong length when a digit long', () => {
    expect(checkSaIdNumber('90031550090820', DOB_1990)).toEqual({
      status: 'invalid',
      reason: 'length',
    })
  })
})

describe('the check digit', () => {
  // Criterion 31.
  test('refuses a number whose thirteenth digit is wrong', () => {
    const wrong = `${NINETEEN_NINETY.slice(0, 12)}3`

    expect(checkSaIdNumber(wrong, DOB_1990)).toEqual({ status: 'invalid', reason: 'checksum' })
  })

  test('refuses every other value of the thirteenth digit', () => {
    const payload = NINETEEN_NINETY.slice(0, 12)
    const correct = NINETEEN_NINETY[12]

    for (let digit = 0; digit <= 9; digit += 1) {
      const candidate = `${payload}${digit}`
      const expected = String(digit) === correct ? 'valid' : 'invalid'

      expect(checkSaIdNumber(candidate, DOB_1990).status).toBe(expected)
    }
  })

  test('is reported ahead of a date mismatch when one digit of the date is mistyped', () => {
    /*
     * Criterion 35. `9002155009082` is the reference number with the fourth digit fumbled: the
     * date now reads 15 February rather than 15 March, so both refusals apply. The checksum one
     * is the one worth telling a person, because it names a typo. A date mismatch does not say
     * which of the two values is wrong, and the date of birth cannot be corrected on this screen.
     */
    expect(checkSaIdNumber('9002155009082', DOB_1990)).toEqual({
      status: 'invalid',
      reason: 'checksum',
    })
  })
})

describe('the date of birth cross-check', () => {
  // Criterion 32.
  test('refuses a valid number whose date disagrees with the date of birth', () => {
    expect(checkSaIdNumber(NINETEEN_NINETY, date(1991, 3, 15))).toEqual({
      status: 'invalid',
      reason: 'date-mismatch',
    })
  })

  test('refuses a disagreement in the month alone', () => {
    expect(refusal(checkSaIdNumber(NINETEEN_NINETY, date(1990, 4, 15)))).toBe('date-mismatch')
  })

  test('refuses a disagreement in the day alone', () => {
    expect(refusal(checkSaIdNumber(NINETEEN_NINETY, date(1990, 3, 16)))).toBe('date-mismatch')
  })

  test('compares only the last two digits of the year', () => {
    // 1890 and 1990 share `90`, so the ID cannot tell them apart and is not asked to.
    expect(checkSaIdNumber(NINETEEN_NINETY, date(1890, 3, 15)).status).toBe('valid')
  })
})

describe('the citizenship digit', () => {
  // Criterion 33.
  test('refuses a value that is neither citizen nor permanent resident', () => {
    expect(checkSaIdNumber('9003155009280', DOB_1990)).toEqual({
      status: 'invalid',
      reason: 'not-recognised',
    })
  })

  test('is reported after the checksum and the date, being the least likely to be a typo', () => {
    // The same unrecognised digit, against a date of birth that also disagrees.
    expect(refusal(checkSaIdNumber('9003155009280', date(1991, 3, 15)))).toBe('date-mismatch')
  })
})

describe('what the field lets through as it is typed', () => {
  // Criterion 58.
  test.each([
    ['a letter on its own', 'a', ''],
    ['a letter among digits', '90031550090X2', '900315500902'],
    ['spaces', '900315 5009 082', '9003155009082'],
    ['hyphens', '900315-5009-082', '9003155009082'],
    ['a plus', '+9003155009082', '9003155009082'],
    ['a whole sentence', 'my id number', ''],
  ])('drops %s', (_label, typed, expected) => {
    expect(filterSaIdInput(typed)).toBe(expected)
  })

  // Criterion 59.
  test('stops at thirteen digits', () => {
    expect(filterSaIdInput('12345678901234567')).toBe('1234567890123')
  })

  test('counts thirteen digits, not thirteen characters', () => {
    /*
     * The whole reason the cap is here rather than on the input's own maxlength: a pasted number
     * written with spaces is fifteen characters and thirteen digits, and truncating the characters
     * would leave eleven digits and a refusal nobody could explain.
     */
    expect(filterSaIdInput('900315 5009 082')).toBe('9003155009082')
    expect(filterSaIdInput('900315 5009 082')).toHaveLength(SA_ID_LENGTH)
  })

  test('leaves an acceptable value untouched, so typing never fights itself', () => {
    for (const value of ['', '9', '900315', '9003155009082']) {
      expect(filterSaIdInput(value)).toBe(value)
    }
  })

  test('is idempotent', () => {
    const once = filterSaIdInput('900315 5009 0821234')

    expect(filterSaIdInput(once)).toBe(once)
  })
})

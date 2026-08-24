import { describe, expect, test } from 'vitest'
import {
  AGE_CHECK_REFUSALS,
  MINIMUM_AGE_YEARS,
  SAST_TIME_ZONE,
  checkAge,
  fromIsoDate,
  hasReachedMinimumAge,
  isAgeCheckRefusal,
  sastToday,
  toIsoDate,
} from './age-gate'

/*
 * design/features/age-gate-before-sign-up.md criteria 8 to 20.
 *
 * Every case fixes the instant, so a boundary is a test rather than something that only breaks
 * at midnight in production. All dates are invented — no real person's date of birth.
 */

/** Midday SAST on 20 August 2026, the reference "today" for most cases below. */
const MIDDAY_SAST = new Date('2026-08-20T10:00:00Z')

const dob = (year: number, month: number, day: number) => ({
  day: String(day),
  month: String(month),
  year: String(year),
})

describe('the minimum age', () => {
  // Criterion 20.
  test('is 18', () => {
    expect(MINIMUM_AGE_YEARS).toBe(18)
  })

  test('is measured against the South African time zone', () => {
    expect(SAST_TIME_ZONE).toBe('Africa/Johannesburg')
  })
})

describe('today, on a South African calendar', () => {
  test('reads the date in SAST, not UTC', () => {
    // Criterion 11. Half past midnight on 20 August in SAST is still 19 August in UTC.
    expect(sastToday(new Date('2026-08-19T22:30:00Z'))).toEqual({
      year: 2026,
      month: 8,
      day: 20,
    })
  })

  test('has not yet rolled over half an hour earlier', () => {
    // Criterion 12.
    expect(sastToday(new Date('2026-08-19T21:30:00Z'))).toEqual({
      year: 2026,
      month: 8,
      day: 19,
    })
  })

  test('reads a plain midday instant as the same day', () => {
    expect(sastToday(MIDDAY_SAST)).toEqual({ year: 2026, month: 8, day: 20 })
  })
})

describe('the eighteen-year rule', () => {
  const today = { year: 2026, month: 8, day: 20 }

  test('passes someone comfortably over age', () => {
    // Criterion 8.
    expect(hasReachedMinimumAge({ year: 1994, month: 4, day: 21 }, today)).toBe(true)
  })

  test('passes someone whose eighteenth birthday is today', () => {
    // Criterion 9.
    expect(hasReachedMinimumAge({ year: 2008, month: 8, day: 20 }, today)).toBe(true)
  })

  test('refuses someone whose eighteenth birthday is tomorrow', () => {
    // Criterion 10.
    expect(hasReachedMinimumAge({ year: 2008, month: 8, day: 21 }, today)).toBe(false)
  })

  test('refuses someone whose eighteenth birthday is later this year', () => {
    expect(hasReachedMinimumAge({ year: 2008, month: 12, day: 1 }, today)).toBe(false)
  })

  test('passes someone whose eighteenth birthday was earlier this year', () => {
    expect(hasReachedMinimumAge({ year: 2008, month: 1, day: 1 }, today)).toBe(true)
  })

  test('refuses someone turning eighteen next year', () => {
    expect(hasReachedMinimumAge({ year: 2009, month: 8, day: 20 }, today)).toBe(false)
  })
})

describe('a birthday on 29 February', () => {
  // Criterion 13. 2026 has no 29 February, so the eighteenth birthday falls on 1 March — the
  // conservative reading, recorded as an open question for legal in section 10.
  const leapling = { year: 2008, month: 2, day: 29 }

  test('is refused on 28 February 2026', () => {
    expect(hasReachedMinimumAge(leapling, { year: 2026, month: 2, day: 28 })).toBe(false)
  })

  test('passes on 1 March 2026', () => {
    expect(hasReachedMinimumAge(leapling, { year: 2026, month: 3, day: 1 })).toBe(true)
  })

  test('passes on 29 February 2028, which does exist', () => {
    expect(hasReachedMinimumAge(leapling, { year: 2028, month: 2, day: 29 })).toBe(true)
  })
})

describe('checking what the visitor typed', () => {
  test('passes an adult date of birth and returns the date it read', () => {
    expect(checkAge(dob(1994, 4, 21), MIDDAY_SAST)).toEqual({
      status: 'pass',
      dateOfBirth: { year: 1994, month: 4, day: 21 },
    })
  })

  test('accepts single-digit parts and surrounding spaces', () => {
    expect(checkAge({ day: ' 7 ', month: ' 3 ', year: ' 1990 ' }, MIDDAY_SAST)).toEqual({
      status: 'pass',
      dateOfBirth: { year: 1990, month: 3, day: 7 },
    })
  })

  test('accepts zero-padded parts, as a browser autofill may supply them', () => {
    expect(checkAge({ day: '07', month: '03', year: '1990' }, MIDDAY_SAST)).toEqual({
      status: 'pass',
      dateOfBirth: { year: 1990, month: 3, day: 7 },
    })
  })

  test('refuses someone under eighteen as under age, not as invalid', () => {
    // Criterion 10, through the whole check.
    expect(checkAge(dob(2010, 5, 5), MIDDAY_SAST)).toEqual({
      status: 'refused',
      reason: 'under-age',
    })
  })

  test('passes at exactly eighteen, on the SAST side of midnight', () => {
    // Criteria 9, 11 and 12 through the whole check.
    const eighteenOn20August = dob(2008, 8, 20)

    expect(checkAge(eighteenOn20August, new Date('2026-08-19T22:30:00Z'))).toEqual({
      status: 'pass',
      dateOfBirth: { year: 2008, month: 8, day: 20 },
    })
    expect(checkAge(eighteenOn20August, new Date('2026-08-19T21:30:00Z'))).toEqual({
      status: 'refused',
      reason: 'under-age',
    })
  })

  test.each([
    ['all three parts', { day: '', month: '', year: '' }],
    ['the day', { day: '', month: '4', year: '1994' }],
    ['the month', { day: '21', month: '', year: '1994' }],
    ['the year', { day: '21', month: '4', year: '' }],
    ['a part holding only spaces', { day: '   ', month: '4', year: '1994' }],
  ])('refuses an incomplete date when %s is missing', (_name, input) => {
    // Criterion 16.
    expect(checkAge(input, MIDDAY_SAST)).toEqual({ status: 'refused', reason: 'incomplete' })
  })

  test.each([
    ['letters', { day: 'ten', month: '4', year: '1994' }],
    ['a decimal', { day: '21.5', month: '4', year: '1994' }],
    ['a sign', { day: '-21', month: '4', year: '1994' }],
    ['a separator', { day: '21/04', month: '4', year: '1994' }],
    ['scientific notation', { day: '2e1', month: '4', year: '1994' }],
    ['a full date in one field', { day: '21 April 1994', month: '4', year: '1994' }],
  ])('refuses a part that is not a whole number: %s', (_name, input) => {
    // Criterion 17.
    expect(checkAge(input, MIDDAY_SAST)).toEqual({ status: 'refused', reason: 'not-a-number' })
  })

  test.each([
    ['31 February', dob(1994, 2, 31)],
    ['29 February in a common year', dob(1995, 2, 29)],
    ['31 April', dob(1994, 4, 31)],
    ['a thirteenth month', dob(1994, 13, 1)],
    ['a zero month', dob(1994, 0, 15)],
    ['a zero day', dob(1994, 4, 0)],
    ['a thirty-second day', dob(1994, 4, 32)],
    ['a two-digit year', dob(94, 4, 21)],
  ])('refuses a date that does not exist: %s', (_name, input) => {
    // Criterion 15.
    expect(checkAge(input, MIDDAY_SAST)).toEqual({
      status: 'refused',
      reason: 'not-a-real-date',
    })
  })

  test('accepts 29 February in a leap year', () => {
    expect(checkAge(dob(1996, 2, 29), MIDDAY_SAST)).toEqual({
      status: 'pass',
      dateOfBirth: { year: 1996, month: 2, day: 29 },
    })
  })

  test.each([
    ['tomorrow', dob(2026, 8, 21)],
    ['next year', dob(2027, 1, 1)],
    ['far in the future', dob(3000, 6, 6)],
  ])('refuses a date in the future rather than calling it under age: %s', (_name, input) => {
    // Criterion 14.
    expect(checkAge(input, MIDDAY_SAST)).toEqual({
      status: 'refused',
      reason: 'in-the-future',
    })
  })

  test('treats today as a real date, refused only for being under age', () => {
    expect(checkAge(dob(2026, 8, 20), MIDDAY_SAST)).toEqual({
      status: 'refused',
      reason: 'under-age',
    })
  })

  test.each([
    ['more than 120 years ago', dob(1905, 6, 6)],
    ['the first year of the calendar', dob(1000, 1, 1)],
  ])('refuses an implausible year: %s', (_name, input) => {
    // Criterion 18.
    expect(checkAge(input, MIDDAY_SAST)).toEqual({ status: 'refused', reason: 'implausible' })
  })

  test('accepts the oldest plausible date of birth', () => {
    expect(checkAge(dob(1906, 8, 20), MIDDAY_SAST)).toMatchObject({ status: 'pass' })
  })

  test('never throws, whatever it is handed', () => {
    // Criterion 19.
    const junk = [
      '',
      ' ',
      '0',
      '00',
      '-1',
      '1e400',
      'NaN',
      'Infinity',
      'null',
      'undefined',
      '٢١',
      '2️⃣1️⃣',
      '21\n',
      '<script>alert(1)</script>',
      "'; DROP TABLE users; --",
      '99999999999999999999',
      '21;04;1994',
      ' ',
    ]

    for (const day of junk) {
      for (const month of junk) {
        for (const year of junk) {
          const outcome = checkAge({ day, month, year }, MIDDAY_SAST)

          expect(['pass', 'refused']).toContain(outcome.status)
          expect(outcome.status).toBe('refused')
        }
      }
    }
  })
})

describe('reading a refusal back off the query string', () => {
  test('recognises every reason the check can return', () => {
    expect([...AGE_CHECK_REFUSALS].sort()).toEqual(
      [
        'implausible',
        'in-the-future',
        'incomplete',
        'not-a-number',
        'not-a-real-date',
        'under-age',
      ].sort(),
    )

    for (const reason of AGE_CHECK_REFUSALS) expect(isAgeCheckRefusal(reason)).toBe(true)
  })

  test.each([
    ['nothing', undefined],
    ['an empty string', ''],
    ['a made-up reason', 'because-we-said-so'],
    ['the wrong case', 'UNDER-AGE'],
    ['a status rather than a reason', 'refused'],
    ['a list, as a repeated query parameter arrives', ['under-age', 'implausible']],
  ])('refuses %s', (_name, value) => {
    expect(isAgeCheckRefusal(value)).toBe(false)
  })
})

describe('the storage format', () => {
  test('writes a calendar date as an ISO date, zero padded', () => {
    expect(toIsoDate({ year: 1994, month: 4, day: 7 })).toBe('1994-04-07')
  })

  test('reads one back', () => {
    expect(fromIsoDate('1994-04-07')).toEqual({ year: 1994, month: 4, day: 7 })
  })

  test.each([
    ['an empty string', ''],
    ['a timestamp', '1994-04-07T00:00:00.000Z'],
    ['South African order', '07/04/1994'],
    ['an unpadded month', '1994-4-07'],
    ['a date that does not exist', '1994-02-31'],
    ['a month out of range', '1994-13-01'],
    ['words', 'yesterday'],
  ])('refuses to read %s', (_name, value) => {
    expect(fromIsoDate(value)).toBeNull()
  })
})

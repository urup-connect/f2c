import { describe, expect, test } from 'vitest'
import { AGE_CHECK, ALL_AGE_CHECK_COPY } from './age-gate-content'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'
import { ALL_COPY } from './landing-content'
import type { AgeCheckRefusal } from './age-gate'

/* design/features/age-gate-before-sign-up.md criteria 26, 29, 30 and section 6.3. */

describe('the age check copy', () => {
  test('heads the screen and says why the date is asked for', () => {
    // Criterion 29.
    expect(AGE_CHECK.heading.length).toBeGreaterThan(0)
    expect(AGE_CHECK.hint).toMatch(/date of birth/i)
  })

  test('names the group and each of the three fields', () => {
    expect(AGE_CHECK.legend).toBe('Date of birth')
    expect(AGE_CHECK.fields).toEqual({ day: 'Day', month: 'Month', year: 'Year' })
  })

  test('offers the same way back the other signed-out screens do', () => {
    expect(AGE_CHECK.back).toBe('Back to Cultivators Collective')
  })

  test('carries a message for every refusal the check can return', () => {
    // Criterion 26. A refusal the copy has no words for would show a blank error.
    const reasons: readonly AgeCheckRefusal[] = [
      'incomplete',
      'not-a-number',
      'not-a-real-date',
      'in-the-future',
      'implausible',
      'under-age',
    ]

    expect(Object.keys(AGE_CHECK.refusals).sort()).toEqual([...reasons].sort())
    for (const reason of reasons) expect(AGE_CHECK.refusals[reason].length).toBeGreaterThan(10)
  })

  test('says plainly, in words, that joining is limited to eighteen and over', () => {
    // Criterion 42: the signal is never colour alone.
    expect(AGE_CHECK.refusals['under-age']).toMatch(/\b18\b/)
  })

  test('collects every line for review in one place', () => {
    expect(ALL_AGE_CHECK_COPY).toContain(AGE_CHECK.heading)
    expect(ALL_AGE_CHECK_COPY).toContain(AGE_CHECK.hint)
    expect(ALL_AGE_CHECK_COPY).toContain(AGE_CHECK.refusals['under-age'])
    expect(ALL_AGE_CHECK_COPY.length).toBeGreaterThan(10)
  })
})

describe('every line of copy on the age check', () => {
  // Criterion 30. The same checks the landing copy passes, bar eligibility — see below.
  test('makes no medical, therapeutic or dosage claim', () => {
    for (const line of ALL_AGE_CHECK_COPY) expect(line).not.toMatch(CLINICAL_CLAIM)
  })

  test('reads as a club rather than a shop', () => {
    for (const line of ALL_AGE_CHECK_COPY) expect(line).not.toMatch(RETAIL_VOICE)
  })

  test('quotes no currency amount', () => {
    for (const line of ALL_AGE_CHECK_COPY) {
      for (const pattern of CURRENCY) expect(line).not.toMatch(pattern)
    }
  })
})

describe('eligibility wording stays on this screen alone', () => {
  /*
   * The landing corpus is checked to contain no eligibility wording, because legal has not
   * written that position. This screen is the one place a minimum age is stated, because
   * refusing a visitor without saying why is not a usable screen. Section 6.3.
   */
  test('the age check states the minimum age', () => {
    expect(ALL_AGE_CHECK_COPY.some((line) => ELIGIBILITY_CLAIM.test(line))).toBe(true)
  })

  test('the landing page still states nothing about who may join', () => {
    for (const line of ALL_COPY) expect(line).not.toMatch(ELIGIBILITY_CLAIM)
  })

  test('the two corpora are separate, so one cannot leak into the other', () => {
    for (const line of ALL_AGE_CHECK_COPY) expect(ALL_COPY).not.toContain(line)
  })
})

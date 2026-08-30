import { describe, expect, test } from 'vitest'
import {
  NON_MOBILE_PREFIXES,
  checkSaMobileNumber,
  filterSaMobileInput,
  formatSaMobileNumber,
} from './sa-mobile-number'
import type { SaMobileCheck } from './sa-mobile-number'

/*
 * A copy of the club's suite, because it is a copy of the club's rule. If the two files ever
 * diverge, one of these tests is what says so.
 *
 * Every number is invented. `082 123 4567` is not allocated to anyone and is the number South
 * African form examples have used for years.
 *
 * The range rule is deliberately permissive: it accepts anything starting 6, 7 or 8 except the
 * service ranges that plainly are not handsets. Refusing a real member's real number is worse
 * than accepting one that turns out not to be a phone. See section 6.4 and section 10, risk 5.
 */

const accepted = (result: SaMobileCheck) => (result.status === 'valid' ? result.mobile : null)
const refusal = (result: SaMobileCheck) => (result.status === 'invalid' ? result.reason : null)

describe('the same number, written six ways', () => {
  // Criterion 23.
  test.each([
    ['spaced national', '082 123 4567'],
    ['bare national', '0821234567'],
    ['spaced international', '+27 82 123 4567'],
    ['bare international', '+27821234567'],
    ['double-zero international', '0027821234567'],
    ['country code with no plus', '27821234567'],
  ])('normalises %s to one stored form', (_label, written) => {
    expect(accepted(checkSaMobileNumber(written))).toBe('+27821234567')
  })
})

describe('separators', () => {
  // Criterion 24.
  test.each([
    ['hyphens', '082-123-4567'],
    ['brackets', '(082) 123 4567'],
    ['dots', '082.123.4567'],
    ['a non-breaking space', '082\u00a0123\u00a04567'],
    ['a mixture', '+27 (82) 123-4567'],
    ['surrounding whitespace', '  0821234567  '],
  ])('ignores %s', (_label, written) => {
    expect(accepted(checkSaMobileNumber(written))).toBe('+27821234567')
  })
})

describe('a number the rule accepts', () => {
  test.each([
    ['an 06 number', '0612345678', '+27612345678'],
    ['an 07 number', '0712345678', '+27712345678'],
    ['an 08 number', '0812345678', '+27812345678'],
    ['an 083 number', '0831234567', '+27831234567'],
    ['an 084 number', '0841234567', '+27841234567'],
    ['an 085 number', '0851234567', '+27851234567'],
  ])('accepts %s', (_label, written, expected) => {
    expect(accepted(checkSaMobileNumber(written))).toBe(expected)
  })
})

describe('a number that is not there', () => {
  test.each([
    ['empty', ''],
    ['whitespace only', '   '],
    ['separators only', '()- '],
    ['a lone plus', '+'],
  ])('refuses %s as missing', (_label, written) => {
    expect(refusal(checkSaMobileNumber(written))).toBe('missing')
  })
})

describe('a number of the wrong length', () => {
  // Criterion 25.
  test.each([
    ['a digit short', '082123456'],
    ['a digit long', '08212345678'],
    ['far too short', '0821'],
    ['a digit short internationally', '+2782123456'],
    ['a digit long internationally', '+278212345678'],
  ])('refuses %s', (_label, written) => {
    expect(refusal(checkSaMobileNumber(written))).toBe('length')
  })
})

describe('a number that is not a mobile', () => {
  // Criterion 26.
  test.each([
    ['toll-free 080', '0801234567'],
    ['share-call 086', '0861234567'],
    ['VoIP 087', '0871234567'],
    ['088', '0881234567'],
    ['089', '0891234567'],
  ])('refuses %s', (_label, written) => {
    expect(refusal(checkSaMobileNumber(written))).toBe('not-a-mobile')
  })

  test('refuses the same ranges written internationally', () => {
    expect(refusal(checkSaMobileNumber('+27861234567'))).toBe('not-a-mobile')
  })

  test('refuses a number in another country', () => {
    // A valid number, just not one the store can reach a South African customer on.
    expect(refusal(checkSaMobileNumber('+44821234567'))).toBe('not-a-mobile')
  })

  // Criterion 27.
  test.each([
    ['a Johannesburg landline', '0111234567'],
    ['a Cape Town landline', '0211234567'],
    ['an 03 number', '0311234567'],
    ['an 04 number', '0411234567'],
    ['an 05 number', '0511234567'],
    ['an 09 number', '0911234567'],
  ])('refuses %s as not a mobile', (_label, written) => {
    expect(refusal(checkSaMobileNumber(written))).toBe('not-a-mobile')
  })

  test('names the excluded ranges as data rather than burying them in a condition', () => {
    expect([...NON_MOBILE_PREFIXES]).toEqual(['080', '086', '087', '088', '089'])
  })
})

describe('a number carrying something that is not a number', () => {
  // Criterion 28.
  test.each([
    ['a letter', '082123456a'],
    ['a word', 'call me'],
    ['an extension marker', '0821234567 ext 4'],
    ['a plus in the middle', '082+1234567'],
    ['a slash', '082/123/4567'],
  ])('refuses %s', (_label, written) => {
    expect(refusal(checkSaMobileNumber(written))).toBe('unexpected-characters')
  })
})

describe('grouping a number for the screen', () => {
  // Criterion 53. Three, three, four - the national form of what will be stored.
  test.each([
    ['bare national', '0821234567'],
    ['spaced national', '082 123 4567'],
    ['hyphenated', '082-123-4567'],
    ['bracketed', '(082) 123 4567'],
    ['international', '+27821234567'],
    ['spaced international', '+27 82 123 4567'],
    ['double-zero international', '0027821234567'],
    ['country code with no plus', '27821234567'],
    ['surrounding whitespace', '  0821234567  '],
  ])('rewrites %s as 082 123 4567', (_label, written) => {
    expect(formatSaMobileNumber(written)).toBe('082 123 4567')
  })

  test('groups an 06 number the same way', () => {
    expect(formatSaMobileNumber('0612345678')).toBe('061 234 5678')
  })

  // Criterion 54.
  test.each([
    ['a service range', '0861234567'],
    ['a landline', '0111234567'],
    ['too few digits', '082123456'],
    ['too many digits', '08212345678'],
    ['words', 'call me'],
    ['another country', '+44821234567'],
    ['nothing at all', ''],
    ['whitespace only', '   '],
  ])('leaves %s exactly as typed', (_label, written) => {
    // Rewriting a value the rule has already refused only hides what needs correcting.
    expect(formatSaMobileNumber(written)).toBe(written)
  })

  test('is idempotent, so blurring twice changes nothing the second time', () => {
    const once = formatSaMobileNumber('+27821234567')

    expect(formatSaMobileNumber(once)).toBe(once)
  })
})

describe('what the field lets through as it is typed', () => {
  // Criterion 57.
  test.each([
    ['a letter on its own', 'a', ''],
    ['letters among digits', '082abc123', '082123'],
    ['a whole word', 'abc', ''],
    ['an emoji', '082\u{1f60a}123', '082123'],
    ['a slash', '082/123', '082123'],
    ['a comma', '082,123', '082123'],
  ])('drops %s', (_label, typed, expected) => {
    expect(filterSaMobileInput(typed)).toBe(expected)
  })

  test.each([
    ['spaces', '082 123 4567'],
    ['hyphens', '082-123-4567'],
    ['brackets', '(082) 123-4567'],
    ['dots', '082.123.4567'],
    ['a leading plus', '+27 82 123 4567'],
    ['a double-zero prefix', '0027821234567'],
  ])('keeps %s, because the rule accepts it', (_label, typed) => {
    expect(filterSaMobileInput(typed)).toBe(typed)
  })

  test('keeps a plus only at the start', () => {
    // A plus anywhere else is not acceptable in any form of the number.
    expect(filterSaMobileInput('082+1234567')).toBe('0821234567')
    expect(filterSaMobileInput('++27821234567')).toBe('+27821234567')
  })

  test('treats a plus as leading once whatever precedes it is dropped', () => {
    expect(filterSaMobileInput('a+27821234567')).toBe('+27821234567')
  })

  test('leaves an already acceptable value untouched, so typing never fights itself', () => {
    for (const value of ['', '0', '08', '082', '082 1', '+27']) {
      expect(filterSaMobileInput(value)).toBe(value)
    }
  })

  test('is idempotent', () => {
    const once = filterSaMobileInput('082abc123')

    expect(filterSaMobileInput(once)).toBe(once)
  })

  test('does not cap the length, because the rule reports a wrong one in words', () => {
    expect(filterSaMobileInput('08212345678901234')).toBe('08212345678901234')
  })
})

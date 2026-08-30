import { describe, expect, test } from 'vitest'
import { PERSON_NAME_MAX_LENGTH, checkPersonName } from './person-name'
import type { PersonNameCheck } from './person-name'

/*
 * A copy of the club's suite, because it is a copy of the club's rule. If the two files ever
 * diverge, one of these tests is what says so.
 *
 * Every name here is invented. The point of most of these cases is what the rule must *not*
 * refuse: this is South Africa, and a name field that argues with its owner is a defect.
 */

const accepted = (result: PersonNameCheck) => (result.status === 'valid' ? result.name : null)
const refusal = (result: PersonNameCheck) => (result.status === 'invalid' ? result.reason : null)

describe('a name the rule must accept', () => {
  // Criterion 5.
  test.each([
    ['a single given name', 'Thandiwe'],
    ['a hyphen and a particle', 'Nkosi-van der Merwe'],
    ['a diacritic', 'Zoë'],
    ['a straight apostrophe', "O'Brien"],
    ['a typographic apostrophe', 'O’Brien'],
    ['initials with full stops', 'A.B. Dlamini'],
    ['a Tamil name', 'அருள்'],
    ['a name in Cyrillic script', 'Анна'],
    ['a single letter', 'S'],
    ['no vowel', 'Ngcwabe'],
    ['lower case throughout', 'de villiers'],
  ])('accepts %s', (_label, name) => {
    expect(accepted(checkPersonName(name))).toBe(name)
  })

  test('accepts a name of exactly the maximum length', () => {
    const name = 'A'.repeat(PERSON_NAME_MAX_LENGTH)

    expect(accepted(checkPersonName(name))).toBe(name)
  })

  test('has a maximum length of 70', () => {
    expect(PERSON_NAME_MAX_LENGTH).toBe(70)
  })
})

describe('whitespace', () => {
  // Criterion 11.
  test('is trimmed at both ends', () => {
    expect(accepted(checkPersonName('  Thandiwe  '))).toBe('Thandiwe')
  })

  test('is collapsed inside the name', () => {
    expect(accepted(checkPersonName('Thandiwe   Nomsa'))).toBe('Thandiwe Nomsa')
  })

  test('collapses a non-breaking space to an ordinary one', () => {
    expect(accepted(checkPersonName('Thandiwe\u00a0Nomsa'))).toBe('Thandiwe Nomsa')
  })

  test('is measured against the maximum after collapsing, not before', () => {
    const name = `${'A'.repeat(PERSON_NAME_MAX_LENGTH - 2)}   B`

    expect(accepted(checkPersonName(name))).toBe(`${'A'.repeat(PERSON_NAME_MAX_LENGTH - 2)} B`)
  })
})

describe('a name that is not there', () => {
  // Criterion 8.
  test.each([
    ['empty', ''],
    ['spaces only', '   '],
    ['a non-breaking space only', '\u00a0'],
  ])('refuses %s as missing', (_label, name) => {
    expect(refusal(checkPersonName(name))).toBe('missing')
  })
})

describe('a name carrying something that is not part of a name', () => {
  // Criterion 9.
  test.each([
    ['a digit', 'Thabo3'],
    ['an exclamation mark', 'Thabo!'],
    ['markup', '<script>'],
    ['an at sign', 'thabo@example.com'],
    ['a comma', 'Dlamini, A'],
    ['an underscore', 'Thabo_M'],
    ['an emoji', 'Thabo 🙂'],
  ])('refuses %s', (_label, name) => {
    expect(refusal(checkPersonName(name))).toBe('unexpected-characters')
  })

  test('refuses punctuation with no letter in it at all', () => {
    // Permitted characters are not sufficient: a name has to contain a letter.
    expect(refusal(checkPersonName('---'))).toBe('unexpected-characters')
  })
})

describe('a name longer than the maximum', () => {
  // Criterion 10.
  test('is refused as too long', () => {
    expect(refusal(checkPersonName('A'.repeat(PERSON_NAME_MAX_LENGTH + 1)))).toBe('too-long')
  })

  test('is reported as unexpected characters when it also contains a digit', () => {
    // The more specific complaint wins: length is not what is wrong with it.
    expect(refusal(checkPersonName(`${'A'.repeat(PERSON_NAME_MAX_LENGTH)}9`))).toBe(
      'unexpected-characters',
    )
  })
})

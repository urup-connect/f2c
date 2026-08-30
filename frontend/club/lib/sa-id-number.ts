/**
 * The South African identity number, as pure logic.
 *
 * Thirteen digits in five parts: a two-digit-year birth date, a sequence within that date, a
 * citizenship digit, a digit that once classified race, and a Luhn check digit.
 *
 * Two of those parts are deliberately not read. The sequence encodes sex and digit 12 is a
 * historical race classifier; deriving either would put the member record under POPIA section 26
 * and its narrower processing grounds for no product benefit at all. The result of this module
 * carries the thirteen digits and nothing else, and a test asserts that.
 *
 * The date of birth is always an argument, never parsed out of the number. Six digits carry a
 * two-digit year, so `900315` is 1990 or 1890 and the number does not say which; guessing a
 * century is a rule about who may join, dressed up as parsing. The age gate has already validated
 * a four-digit date, so this module compares against that instead.
 *
 * See design/features/member-details-at-sign-up.md sections 6.3 and 9.
 */

import type { CalendarDate } from './age-gate'

export const SA_ID_LENGTH = 13

/** Where the birth date ends and the sequence begins. */
const DATE_DIGITS = 6

/** Zero-based index of the citizenship digit: `0` citizen, `1` permanent resident. */
const CITIZENSHIP_INDEX = 10

const CITIZENSHIP_VALUES = ['0', '1'] as const

export type SaIdRefusal =
  | 'missing'
  | 'length'
  | 'not-digits'
  | 'checksum'
  | 'date-mismatch'
  | 'not-recognised'

/**
 * Every refusal this module can return, as values, in the order the checks apply them.
 *
 * A refusal travels to the form as a code rather than a message, so it has to be narrowed from an
 * arbitrary string on the way back in.
 */
export const SA_ID_REFUSALS = [
  'missing',
  'length',
  'not-digits',
  'checksum',
  'date-mismatch',
  'not-recognised',
] as const satisfies readonly SaIdRefusal[]

export const isSaIdRefusal = (value: unknown): value is SaIdRefusal =>
  typeof value === 'string' && SA_ID_REFUSALS.some((refusal): boolean => refusal === value)

export type SaIdCheck =
  | { readonly status: 'valid'; readonly idNumber: string }
  | { readonly status: 'invalid'; readonly reason: SaIdRefusal }

/**
 * Whitespace and hyphens, wherever they fall.
 *
 * `\s` already covers the non-breaking space a copied number brings with it, but it is named
 * explicitly so a future reader does not have to take that on trust.
 */
const SEPARATORS = /[\s -]+/g

const NOT_A_DIGIT = /\D/

/** The same class, swept across a whole value rather than tested for one. */
const NOT_A_DIGIT_GLOBAL = /\D/g

const invalid = (reason: SaIdRefusal): SaIdCheck => ({ status: 'invalid', reason })

const pad = (value: number) => String(value).padStart(2, '0')

/** The six digits an ID number must open with, for a given date of birth. */
const expectedDatePrefix = ({ year, month, day }: CalendarDate) =>
  `${pad(year % 100)}${pad(month)}${pad(day)}`

/**
 * The Luhn check digit for the first twelve digits.
 *
 * Every second digit counting back from the check digit is doubled, and a doubled result above
 * nine has nine subtracted — which is the same thing as summing its two digits. This is the
 * algorithm the Department of Home Affairs applies, usually written as an odd-position sum plus
 * the digit sum of the even positions concatenated and doubled; the two are arithmetically the
 * same and this form is the one worth reading.
 */
const luhnCheckDigit = (payload: string) => {
  let sum = 0

  for (let offset = 0; offset < payload.length; offset += 1) {
    const digit = Number(payload[payload.length - 1 - offset])
    const doubled = offset % 2 === 0 ? digit * 2 : digit

    sum += doubled > 9 ? doubled - 9 : doubled
  }

  return (10 - (sum % 10)) % 10
}

/**
 * The whole check, from what the visitor typed to an outcome. Never throws for any input.
 *
 * The order matters and is not arbitrary. Shape first, so a value that is not a number at all is
 * told so. Then the checksum, because a single fumbled digit anywhere — including inside the date
 * — breaks it, and "this number does not add up" names a typo the visitor can find. Only then the
 * date, because a mismatch on a number that does add up is a genuine disagreement between two
 * values rather than a slip, and the date of birth cannot be corrected on this screen. The
 * citizenship digit is last, being the least likely of the three to be a typo.
 */
export const checkSaIdNumber = (input: string, dateOfBirth: CalendarDate): SaIdCheck => {
  const idNumber = input.replace(SEPARATORS, '')

  if (idNumber.length === 0) return invalid('missing')
  if (NOT_A_DIGIT.test(idNumber)) return invalid('not-digits')
  if (idNumber.length !== SA_ID_LENGTH) return invalid('length')

  const payload = idNumber.slice(0, SA_ID_LENGTH - 1)

  if (Number(idNumber[SA_ID_LENGTH - 1]) !== luhnCheckDigit(payload)) return invalid('checksum')

  if (idNumber.slice(0, DATE_DIGITS) !== expectedDatePrefix(dateOfBirth)) {
    return invalid('date-mismatch')
  }

  const citizenship = idNumber[CITIZENSHIP_INDEX]

  if (!CITIZENSHIP_VALUES.some((value): boolean => value === citizenship)) {
    return invalid('not-recognised')
  }

  return { status: 'valid', idNumber }
}

/**
 * What the field lets through as it is typed: thirteen digits, and nothing else at all.
 *
 * The separators are dropped rather than kept, unlike the mobile number. There is one way to write
 * an ID number and it is thirteen digits, so a space in the middle is a habit rather than a form,
 * and a pasted number carrying them arrives clean.
 *
 * **The cap counts digits, not characters, which is the whole reason it is here rather than on the
 * input's own `maxlength`.** `900315 5009 082` is fifteen characters and thirteen digits; a
 * character cap would truncate it to `900315 5009 0`, leaving eleven digits and a refusal no
 * member could account for.
 *
 * Idempotent, and a no-op on anything already acceptable. See
 * design/features/member-details-at-sign-up.md section 6.3 and criteria 58 and 59.
 */
export const filterSaIdInput = (value: string) =>
  value.replace(NOT_A_DIGIT_GLOBAL, '').slice(0, SA_ID_LENGTH)

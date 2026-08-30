/**
 * A South African mobile number, as pure logic.
 *
 * Email is how a member signs in, so this is a contact number rather than a credential. It exists
 * to be reachable, which is why the rule excludes the service ranges that cannot reach a person.
 *
 * One stored form, `+27` and nine digits, so the same handset cannot become two members by being
 * written with different punctuation.
 *
 * The range rule is deliberately permissive: anything starting 6, 7 or 8, less the service ranges
 * below. An allow-list of every allocated prefix would be more precise today and wrong within a
 * year, and its failure mode is refusing a real member's real number — worse than accepting one
 * that turns out not to be a handset. See design/features/member-details-at-sign-up.md section 6.4
 * and section 10, risk 5.
 */

/** Nine digits after the trunk zero or the country code. */
const NATIONAL_LENGTH = 9

/** First digits that carry a handset. */
const MOBILE_LEADING_DIGITS = ['6', '7', '8'] as const

/**
 * Ranges inside `08` that are not mobile: toll-free, share-call and VoIP. Written as a member
 * would write them, with the trunk zero, so the list reads as the numbers people recognise.
 */
export const NON_MOBILE_PREFIXES = ['080', '086', '087', '088', '089'] as const

export type SaMobileRefusal = 'missing' | 'unexpected-characters' | 'length' | 'not-a-mobile'

export const SA_MOBILE_REFUSALS = [
  'missing',
  'unexpected-characters',
  'length',
  'not-a-mobile',
] as const satisfies readonly SaMobileRefusal[]

export type SaMobileCheck =
  | { readonly status: 'valid'; readonly mobile: string }
  | { readonly status: 'invalid'; readonly reason: SaMobileRefusal }

/**
 * How people punctuate a phone number: spaces of every kind, hyphens, brackets and dots.
 *
 * A slash is not here on purpose. `082/123/4567` is usually two numbers, and guessing which one
 * is meant is worse than asking.
 */
const SEPARATORS = /[\s().-]+/g

const DIGITS_ONLY = /^\d+$/

const COUNTRY_CODE = '27'

const invalid = (reason: SaMobileRefusal): SaMobileCheck => ({ status: 'invalid', reason })

/**
 * The nine-digit national number, from whichever prefix the visitor used.
 *
 * `0027` is tested before `0`, and a bare `27` only counts as a country code at the length that
 * makes it one — otherwise a national number that happens to start `27` would lose two digits.
 */
const toNationalNumber = (digits: string, hadPlus: boolean) => {
  if (hadPlus) return digits.slice(COUNTRY_CODE.length)
  if (digits.startsWith(`00${COUNTRY_CODE}`)) return digits.slice(4)

  if (digits.startsWith(COUNTRY_CODE) && digits.length === COUNTRY_CODE.length + NATIONAL_LENGTH) {
    return digits.slice(COUNTRY_CODE.length)
  }

  return digits.startsWith('0') ? digits.slice(1) : digits
}

/**
 * The whole rule. Never throws for any input.
 *
 * A leading `+` that is not `+27` is refused as not a mobile rather than as a bad character: the
 * number is real, it just is not one this club can reach a South African member on.
 */
export const checkSaMobileNumber = (input: string): SaMobileCheck => {
  const stripped = input.replace(SEPARATORS, '')
  const hadPlus = stripped.startsWith('+')
  const digits = hadPlus ? stripped.slice(1) : stripped

  if (digits.length === 0) return invalid('missing')
  if (!DIGITS_ONLY.test(digits)) return invalid('unexpected-characters')
  if (hadPlus && !digits.startsWith(COUNTRY_CODE)) return invalid('not-a-mobile')

  const national = toNationalNumber(digits, hadPlus)

  if (national.length !== NATIONAL_LENGTH) return invalid('length')

  if (!MOBILE_LEADING_DIGITS.some((digit): boolean => digit === national[0])) {
    return invalid('not-a-mobile')
  }

  const asWritten = `0${national.slice(0, 2)}`

  if (NON_MOBILE_PREFIXES.some((prefix): boolean => prefix === asWritten)) {
    return invalid('not-a-mobile')
  }

  return { status: 'valid', mobile: `+${COUNTRY_CODE}${national}` }
}

/** How the number is grouped on screen: three, three, four. */
const GROUPS = [3, 3, 4] as const

/**
 * An accepted number, grouped the way people write it: `082 123 4567`.
 *
 * A value the rule refuses comes back untouched. Rewriting something already refused only obscures
 * what the member has to correct, and this runs on blur — by which point they have finished with
 * the field and a refusal is about to be shown against it.
 *
 * Idempotent, so a field that loses focus twice does not drift.
 *
 * The grouping is display only. `checkSaMobileNumber` stores `+27` and nine digits either way, and
 * nothing downstream depends on this having run: with no JavaScript it never does, and the outcome
 * is identical. See design/features/member-details-at-sign-up.md section 6.4, criteria 53 to 55.
 */
export const formatSaMobileNumber = (input: string): string => {
  const checked = checkSaMobileNumber(input)

  if (checked.status !== 'valid') return input

  // Back to the national form the groups are drawn around: a leading zero, then nine digits.
  const national = `0${checked.mobile.slice(`+${COUNTRY_CODE}`.length)}`

  const parts: string[] = []
  let start = 0

  for (const size of GROUPS) {
    parts.push(national.slice(start, start + size))
    start += size
  }

  return parts.join(' ')
}

/** Everything a member may legitimately type: digits, a plus, and the separators people use. */
const ACCEPTED_WHILE_TYPING = /[^\d+\s().-]/g

/** Every plus except one at the very start. */
const MISPLACED_PLUS = /(?!^)\+/g

/**
 * What the field lets through as it is typed.
 *
 * Anything the rule could never accept is simply dropped, so a letter keyed into a phone number
 * does nothing at all. The punctuation stays: `+27`, brackets, dots and hyphens are all forms this
 * club accepts, and filtering them out would narrow what a member may type in order to tidy what
 * they see.
 *
 * A plus survives only at the start, because there is no accepted form of the number with one
 * anywhere else. It counts as leading once whatever preceded it has been dropped.
 *
 * No length cap here, deliberately: a wrong length is worth saying out loud, and the rule says it.
 *
 * Idempotent, and a no-op on anything already acceptable, so typing never fights itself. See
 * design/features/member-details-at-sign-up.md section 6.4 and criterion 57.
 */
export const filterSaMobileInput = (value: string) =>
  value.replace(ACCEPTED_WHILE_TYPING, '').replace(MISPLACED_PLUS, '')

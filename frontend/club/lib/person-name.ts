/**
 * A person's name, as pure logic.
 *
 * The interesting part of this rule is what it refuses to refuse. It does not require two names,
 * a vowel, a capital letter, more than one character, or the Latin alphabet. Every one of those
 * conventions, applied to South African names, rejects people who exist — and a name field that
 * argues with its owner is a defect before it is anything else.
 *
 * What it does refuse is a value that is not a name at all: digits, markup, an email address, an
 * emoji, or punctuation with no letter anywhere in it.
 *
 * See design/features/member-details-at-sign-up.md section 6.5.
 */

export const PERSON_NAME_MAX_LENGTH = 70

export type PersonNameRefusal = 'missing' | 'unexpected-characters' | 'too-long'

export const PERSON_NAME_REFUSALS = [
  'missing',
  'unexpected-characters',
  'too-long',
] as const satisfies readonly PersonNameRefusal[]

export type PersonNameCheck =
  | { readonly status: 'valid'; readonly name: string }
  | { readonly status: 'invalid'; readonly reason: PersonNameRefusal }

/** Any run of whitespace, including the non-breaking space a paste brings with it. */
const WHITESPACE = /\s+/g

/**
 * Letters and combining marks from any script, plus the three punctuation marks names carry.
 *
 * Both apostrophes are permitted: a keyboard produces `'` and a word processor silently produces
 * `’`, and a member should not have to know which one they typed.
 */
const NAME_CHARACTERS = /^[\p{L}\p{M} '’.-]+$/u

const A_LETTER = /\p{L}/u

const invalid = (reason: PersonNameRefusal): PersonNameCheck => ({ status: 'invalid', reason })

/** Ends trimmed, internal runs collapsed to one space. The form that is stored and compared. */
export const normalisePersonName = (input: string) => input.replace(WHITESPACE, ' ').trim()

/**
 * The whole rule. Never throws for any input.
 *
 * Length is measured after normalising, so three spaces a visitor did not mean to type cannot
 * push an otherwise acceptable name over the limit. Characters are checked before length, because
 * "that is not a name" is the more useful complaint about a long string full of digits.
 */
export const checkPersonName = (input: string): PersonNameCheck => {
  const name = normalisePersonName(input)

  if (name.length === 0) return invalid('missing')
  if (!NAME_CHARACTERS.test(name)) return invalid('unexpected-characters')
  // Permitted characters are not sufficient. A name has to contain a letter.
  if (!A_LETTER.test(name)) return invalid('unexpected-characters')
  if (name.length > PERSON_NAME_MAX_LENGTH) return invalid('too-long')

  return { status: 'valid', name }
}

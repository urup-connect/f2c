/**
 * The details form, as pure logic. No fetching, no DOM, no clock.
 *
 * It holds no validation of its own. The two rules it needs already exist, are already tested, and
 * are already the rules the API enforces — `person-name.ts` and `sa-mobile-number.ts` — so this
 * reads the form, asks each of them about its field, and collects every refusal rather than stopping
 * at the first. Somebody with two things wrong should be told two things once.
 *
 * **Three fields, and what is absent is the design.** The email address is the sign-in identifier
 * and cannot be changed here. The nickname, the date of birth and the identity number are not on
 * this form at all — and unlike the club, where they are read-only, in the store they are usually
 * *empty*: a customer is never asked for an identity number, which is what POPIA's minimisation
 * principle requires and `design/verticals.md` section 5 records as the reason the columns became
 * optional rather than moving. A store form that displayed an identity field, even read-only, would
 * be inviting somebody to fill it in.
 *
 * The mobile number is optional, exactly as in the club's profile and for a sharper reason here: it
 * is what a driver rings from the gate, so a wrong number is worse than none.
 */

import { checkPersonName, normalisePersonName } from './person-name'
import { checkSaMobileNumber } from './sa-mobile-number'

/** In the order the form shows them, which is the order refusals are reported in. */
export const PROFILE_FIELDS = ['firstName', 'lastName', 'mobile'] as const

export type ProfileField = (typeof PROFILE_FIELDS)[number]

/**
 * Every refusal this form can produce.
 *
 * Named here rather than imported from a sign-up vocabulary, which is what the club does: the store
 * has no club-document consents, no nickname and no identity number, so there is no wider set for
 * this to be a subset of. `PROFILE_REFUSAL_MESSAGES` in `store-content.ts` is keyed by exactly these
 * strings, and a `satisfies` there would not compile if the two fell out of step.
 */
export const PROFILE_REFUSALS = [
  'name-missing',
  'name-too-long',
  'name-unexpected-characters',
  'mobile-unexpected-characters',
  'mobile-length',
  'mobile-not-a-mobile',
] as const

export type ProfileRefusal = (typeof PROFILE_REFUSALS)[number]

export type ProfileFieldRefusal = {
  readonly field: ProfileField
  readonly reason: ProfileRefusal
}

/** Exactly what the form hands over. Every value a string, because that is what a form yields. */
export type ProfileInput = { readonly [Field in ProfileField]: string }

/** What would be sent, once every field has been accepted. The normalised form. */
export type ProfileSubmission = {
  readonly first_name: string
  readonly last_name: string
  /** `+27` and nine digits, or the empty string when the customer holds no number. */
  readonly mobile: string
}

export type ProfileCheck =
  | { readonly status: 'valid'; readonly submission: ProfileSubmission }
  | { readonly status: 'invalid'; readonly refusals: readonly ProfileFieldRefusal[] }

/**
 * A name refusal, mapped onto this form's vocabulary.
 *
 * `person-name.ts` reports `missing`, `too-long` and `unexpected-characters` without saying which
 * field they came from, because it does not know. This is where they become the prefixed codes the
 * messages are keyed by.
 */
const nameRefusal = (reason: 'missing' | 'too-long' | 'unexpected-characters'): ProfileRefusal =>
  reason === 'missing'
    ? 'name-missing'
    : reason === 'too-long'
      ? 'name-too-long'
      : 'name-unexpected-characters'

/**
 * The whole form. Never throws for any input.
 *
 * Every field is checked, always — not short-circuited on the first failure.
 */
export const checkProfile = (input: ProfileInput): ProfileCheck => {
  const refusals: ProfileFieldRefusal[] = []

  const first = checkPersonName(input.firstName)
  if (first.status === 'invalid') {
    refusals.push({ field: 'firstName', reason: nameRefusal(first.reason) })
  }

  const last = checkPersonName(input.lastName)
  if (last.status === 'invalid') {
    refusals.push({ field: 'lastName', reason: nameRefusal(last.reason) })
  }

  /*
   * A blank field is an answer here ("I have no number for you"), not an omission, so the branch is
   * outside the rule rather than a second mobile rule being written to hold it.
   */
  const typed = input.mobile.trim()
  let mobile = ''

  if (typed.length > 0) {
    const checked = checkSaMobileNumber(typed)
    if (checked.status === 'valid') {
      mobile = checked.mobile
    } else if (checked.reason === 'missing') {
      /*
       * Unreachable: `typed` is non-blank, and `missing` is what a blank yields. Mapped rather than
       * ignored so the union stays exhaustive — a caller reaching this has found a bug in
       * `sa-mobile-number.ts`, and reporting "that is not a mobile number" is at least true.
       */
      refusals.push({ field: 'mobile', reason: 'mobile-not-a-mobile' })
    } else {
      refusals.push({ field: 'mobile', reason: `mobile-${checked.reason}` as ProfileRefusal })
    }
  }

  if (refusals.length > 0) return { status: 'invalid', refusals }

  return {
    status: 'valid',
    submission: {
      // Both names are already normalised by `checkPersonName`, which returns the collapsed form.
      first_name: first.status === 'valid' ? first.name : '',
      last_name: last.status === 'valid' ? last.name : '',
      mobile,
    },
  }
}

/** Just enough of `FormData` to read a form, so the reader below is testable without a DOM. */
export type FormReader = { get(name: string): unknown }

/**
 * The three fields out of a submitted form.
 *
 * A field the form did not send reads as the empty string rather than throwing, and so does a value
 * that is not a string. The rules then refuse it in the page's own words, so a tampered submission
 * and an empty one are answered the same way and neither reaches the API.
 */
export const readProfileForm = (form: FormReader): ProfileInput => ({
  firstName: readField(form, 'firstName'),
  lastName: readField(form, 'lastName'),
  mobile: readField(form, 'mobile'),
})

const readField = (form: FormReader, name: string): string => {
  const value = form.get(name)
  return typeof value === 'string' ? value : ''
}

/** The refusal against one field, or `undefined`. What a field renders under itself. */
export const profileRefusalFor = (
  refusals: readonly ProfileFieldRefusal[],
  field: ProfileField,
): ProfileRefusal | undefined => refusals.find((refusal) => refusal.field === field)?.reason

/**
 * The three fields as the screen first draws them, from the record the API returned.
 *
 * A blank mobile number arrives as `''` and stays `''`. It is not turned into a placeholder or a
 * dash: the field is empty because the store holds nothing, and an input pre-filled with a dash is
 * an input somebody has to clear before they can type.
 */
export const profileInputFrom = (profile: {
  first_name: string
  last_name: string
  mobile: string
}): ProfileInput => ({
  firstName: profile.first_name,
  lastName: profile.last_name,
  mobile: profile.mobile,
})

/**
 * What the store holds, from a profile response, in the form `profileHasChanges` compares against.
 *
 * Names are normalised on the way in so that a record stored before the rule tightened does not make
 * a freshly loaded form look dirty. The mobile number is not: the API only ever stores the normalised
 * form, so normalising it here would be a second implementation of a rule that has already run.
 */
export const profileOnFile = (profile: {
  first_name: string
  last_name: string
  mobile: string
}): ProfileSubmission => ({
  first_name: normalisePersonName(profile.first_name),
  last_name: normalisePersonName(profile.last_name),
  mobile: profile.mobile,
})

/**
 * Whether anything in the form differs from what is on file.
 *
 * Compared on the *normalised* values, not the typed ones, because the comparison is what decides
 * whether the save button does anything. Somebody who added a trailing space to their surname, or
 * who retyped `+27821234567` as `082 123 4567`, has changed nothing the store would store — and a
 * save button that lights up for that is a button that promises a change it will not make.
 *
 * A form that does not yet validate counts as changed. It cannot be normalised, so the honest answer
 * is "something is different", and pressing save is how they learn what.
 */
export const profileHasChanges = (input: ProfileInput, onFile: ProfileSubmission): boolean => {
  const checked = checkProfile(input)

  if (checked.status === 'invalid') return true

  const { submission } = checked

  return (
    submission.first_name !== normalisePersonName(onFile.first_name) ||
    submission.last_name !== normalisePersonName(onFile.last_name) ||
    submission.mobile !== onFile.mobile
  )
}

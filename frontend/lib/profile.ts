/**
 * The profile form, as pure logic. No fetching, no DOM, no clock.
 *
 * It holds no validation of its own. The two rules it needs already exist, are already tested, and
 * are already the rules the API enforces — `person-name.ts` and `sa-mobile-number.ts` — so this
 * reads the form, asks each of them about its field, and collects every refusal rather than
 * stopping at the first. The same shape as `member-details.ts`, and deliberately so: a member with
 * two things wrong should be told two things once.
 *
 * **The one place the rules differ from sign-up is the mobile number, and the difference is
 * intentional.** Sign-up requires one; this does not. It is a contact detail rather than a
 * credential — members sign in with an emailed code or a passkey — and a member who no longer has
 * the handset they gave should be able to say so, rather than leave the club a wrong number to
 * ring. A blank field is therefore accepted and clears the column. Anything non-blank is held to
 * exactly the sign-up rule.
 *
 * Three fields, and no more. What a member may *not* change here is as much a part of the design as
 * what they may, and each exclusion has its own reason recorded in `app/accounts/profile.py`: the
 * email address is the sign-in identifier, the nickname is unique across the club, and the date of
 * birth and identity number came off a document.
 *
 * The refusal wording is imported from `member-details-content.ts` rather than restated. Two copies
 * of "that does not look like a mobile number" is one of them eventually saying something the other
 * does not.
 */

import { checkPersonName, normalisePersonName } from './person-name'
import { checkSaMobileNumber } from './sa-mobile-number'
import type { MemberDetailsRefusal } from './member-details'

/** In the order the form shows them, which is the order refusals are reported in. */
export const PROFILE_FIELDS = ['firstName', 'lastName', 'mobile'] as const

export type ProfileField = (typeof PROFILE_FIELDS)[number]

/**
 * Every refusal this form can produce.
 *
 * A subset of `MemberDetailsRefusal`, typed as such so the messages can be shared: the compiler
 * refuses a reason here that has no wording there. Note what is absent — `mobile-missing`, because
 * a blank number is accepted, and every `nickname-*`, `email-*` and `id-*` reason, because those
 * fields are not on this form.
 */
export const PROFILE_REFUSALS = [
  'name-missing',
  'name-too-long',
  'name-unexpected-characters',
  'mobile-unexpected-characters',
  'mobile-length',
  'mobile-not-a-mobile',
] as const satisfies readonly MemberDetailsRefusal[]

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
  /** `+27` and nine digits, or the empty string when the member holds no number. */
  readonly mobile: string
}

export type ProfileCheck =
  | { readonly status: 'valid'; readonly submission: ProfileSubmission }
  | { readonly status: 'invalid'; readonly refusals: readonly ProfileFieldRefusal[] }

/**
 * A name refusal, mapped onto the shared vocabulary.
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
 * Every field is checked, always — not short-circuited on the first failure. A member who typed
 * their surname into a phone field and left their first name blank should see both, in the order
 * the fields appear on the screen.
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
   * The one asymmetry with sign-up, and it is checked before the rule rather than inside it: a
   * blank field is an answer here ("I have no number for you"), not an omission. `checkSaMobile
   * Number` has no way to express that — it answers `missing` — so the branch is here rather than
   * a second mobile rule being written to hold it.
   */
  const typed = input.mobile.trim()
  let mobile = ''

  if (typed.length > 0) {
    const checked = checkSaMobileNumber(typed)
    if (checked.status === 'valid') {
      mobile = checked.mobile
    } else if (checked.reason === 'missing') {
      /*
       * Unreachable: `typed` is non-blank, and `missing` is what a blank yields. Mapped rather
       * than ignored so the union stays exhaustive — a caller reaching this has found a bug in
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
      // Read from the check rather than re-normalised here, so there is one normalisation.
      first_name: first.status === 'valid' ? first.name : '',
      last_name: last.status === 'valid' ? last.name : '',
      mobile,
    },
  }
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
 * dash: the field is empty because the club holds nothing, and an input pre-filled with a dash is
 * an input a member has to clear before they can type.
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
 * Whether anything in the form differs from what is on file.
 *
 * Compared on the *normalised* values, not the typed ones, because the form is uncontrolled and the
 * comparison is what decides whether the save button does anything. A member who added a trailing
 * space to their surname, or who retyped `+27821234567` as `082 123 4567`, has changed nothing the
 * club would store — and a save button that lights up for that is a button that promises a change
 * it will not make.
 *
 * A form that does not yet validate counts as changed. It cannot be normalised, so the honest
 * answer is "something is different", and pressing save is how the member learns what.
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

/**
 * What the club holds, from a profile response, in the form `profileHasChanges` compares against.
 *
 * Names are normalised on the way in so that a record stored before the rule tightened does not
 * make a freshly loaded form look dirty. The mobile number is not: the API only ever stores the
 * normalised form, so normalising it here would be a second implementation of a rule that has
 * already run.
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

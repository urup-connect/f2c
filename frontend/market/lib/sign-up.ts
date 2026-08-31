/**
 * Creating a store account, as pure logic. No fetching, no DOM.
 *
 * **Four fields, one of them optional, and that is the whole of it.** A store customer is a `User`
 * with no row in `ClubMembership`, `StorefrontStaff` or `ProducerMembership` — `design/verticals.md`
 * section 6 — so there is nothing else to collect. No identity number, because POPIA's minimisation
 * principle refuses a field asked for on the strength of another storefront's requirement. No
 * nickname, because a customer has a name and needs no pseudonym. No password, because the platform
 * has none: a passkey or an emailed code is how anybody gets in.
 *
 * The rules are the platform's rules, imported rather than restated: `person-name.ts`,
 * `email-address.ts` and `sa-mobile-number.ts`. Every field is checked and every refusal collected,
 * in field order, so somebody with two things wrong is told two things once.
 *
 * **Document consents are absent, and their absence is dated and now enforced.** When the store's own
 * terms and privacy notice are published with `audience=customer` and `agreement=at_registration`,
 * they are collected here and posted with the rest — the machinery on the Django side is already
 * built and storefront-scoped. There is nothing to tick today because there is nothing published;
 * `design/todo.md` Block B carries it. A checkbox against a document that does not exist would be a
 * consent to nothing, recorded as though it were something.
 *
 * What is new is that the API no longer relies on this file remembering. Publishing such a document
 * makes `POST /api/customers/register` refuse every registration outright —
 * `registration.ConsentRequired` — so the day somebody publishes the store's terms before this form
 * has grown a checkbox, sign-up stops rather than quietly recording agreement to nothing.
 */

import { checkEmailAddress } from './email-address'
import { checkPersonName } from './person-name'
import { checkSaMobileNumber } from './sa-mobile-number'

/** In the order the form shows them, which is the order refusals are reported in. */
export const SIGN_UP_FIELDS = ['firstName', 'lastName', 'email', 'mobile'] as const

export type SignUpField = (typeof SIGN_UP_FIELDS)[number]

/** Every refusal this form can produce. `SIGN_UP_REFUSAL_MESSAGES` is keyed by exactly these. */
export const SIGN_UP_REFUSALS = [
  'name-missing',
  'name-too-long',
  'name-unexpected-characters',
  'email-missing',
  'email-malformed',
  'email-too-long',
  'mobile-unexpected-characters',
  'mobile-length',
  'mobile-not-a-mobile',
] as const

export type SignUpRefusal = (typeof SIGN_UP_REFUSALS)[number]

export type SignUpFieldRefusal = {
  readonly field: SignUpField
  readonly reason: SignUpRefusal
}

/** Exactly what the form hands over. Every value a string, because that is what a form yields. */
export type SignUpInput = { readonly [Field in SignUpField]: string }

/** What would be sent, once every field has been accepted. The normalised form. */
export type SignUpSubmission = {
  readonly first_name: string
  readonly last_name: string
  /** Trimmed and lower-cased: one address has exactly one stored form. */
  readonly email: string
  /** `+27` and nine digits, or the empty string. */
  readonly mobile: string
}

export type SignUpCheck =
  | { readonly status: 'valid'; readonly submission: SignUpSubmission }
  | { readonly status: 'invalid'; readonly refusals: readonly SignUpFieldRefusal[] }

const nameRefusal = (reason: 'missing' | 'too-long' | 'unexpected-characters'): SignUpRefusal =>
  reason === 'missing'
    ? 'name-missing'
    : reason === 'too-long'
      ? 'name-too-long'
      : 'name-unexpected-characters'

/**
 * The whole form. Never throws for any input.
 *
 * The mobile number is optional here as it is on the details screen, and for the same reason: it is
 * what a driver rings, so a wrong number is worse than none. A blank field is an answer.
 */
export const checkSignUp = (input: SignUpInput): SignUpCheck => {
  const refusals: SignUpFieldRefusal[] = []

  const first = checkPersonName(input.firstName)
  if (first.status === 'invalid') {
    refusals.push({ field: 'firstName', reason: nameRefusal(first.reason) })
  }

  const last = checkPersonName(input.lastName)
  if (last.status === 'invalid') {
    refusals.push({ field: 'lastName', reason: nameRefusal(last.reason) })
  }

  const email = checkEmailAddress(input.email)
  if (email.status === 'invalid') {
    refusals.push({ field: 'email', reason: `email-${email.reason}` as SignUpRefusal })
  }

  const typed = input.mobile.trim()
  let mobile = ''

  if (typed.length > 0) {
    const checked = checkSaMobileNumber(typed)
    if (checked.status === 'valid') {
      mobile = checked.mobile
    } else if (checked.reason === 'missing') {
      // Unreachable: `typed` is non-blank. Mapped rather than ignored so the union stays exhaustive.
      refusals.push({ field: 'mobile', reason: 'mobile-not-a-mobile' })
    } else {
      refusals.push({ field: 'mobile', reason: `mobile-${checked.reason}` as SignUpRefusal })
    }
  }

  if (refusals.length > 0) return { status: 'invalid', refusals }

  return {
    status: 'valid',
    submission: {
      first_name: first.status === 'valid' ? first.name : '',
      last_name: last.status === 'valid' ? last.name : '',
      email: email.status === 'valid' ? email.email : '',
      mobile,
    },
  }
}

/** The refusal against one field, or `undefined`. What a field renders under itself. */
export const signUpRefusalFor = (
  refusals: readonly SignUpFieldRefusal[],
  field: SignUpField,
): SignUpRefusal | undefined => refusals.find((refusal) => refusal.field === field)?.reason

/**
 * What comes back from a submission the form accepted.
 *
 * `accepted` says the store has taken the details and a sign-in code is on its way. **It is also
 * the answer for an address that already has an account**, and that is a disclosure decision rather
 * than laziness: an outcome that distinguished the two would turn sign-up into a way of asking
 * whether somebody shops here. It is the same reasoning `RegistrationOut` records on the Django side
 * — the status is the whole answer, whether a row was written or the submission named somebody
 * already on file — and the same reasoning that makes `/api/auth/login/start` answer `otp` for an
 * address with no account.
 *
 * `refused` carries field refusals the API made that this form did not. `unavailable` is the endpoint
 * answering 404 — no longer the normal answer, and now a routing fault rather than an unbuilt
 * endpoint; see `sign-up-api.ts`. `unusable` is everything else, including the 503 the API answers
 * if the store ever publishes a document that must be agreed to and this contract has not yet grown
 * a `consents` field.
 */
export type SignUpOutcome =
  | { readonly status: 'accepted'; readonly email: string }
  | { readonly status: 'refused'; readonly refusals: readonly SignUpFieldRefusal[] }
  | { readonly status: 'unavailable' }
  | { readonly status: 'unusable'; readonly reason: string }

/**
 * What the screen is showing, as the server action leaves it.
 *
 * `invalid` carries the values back with the refusals so the form redraws what was typed. **The
 * other states carry nothing typed at all**, which is the deliberate half: a screen that has stopped
 * asking has no reason to hold somebody's name and address in a payload that is about to be
 * serialised into the page.
 */
export type SignUpFormState =
  | { readonly status: 'idle' }
  | {
      readonly status: 'invalid'
      readonly refusals: readonly SignUpFieldRefusal[]
      readonly values: SignUpInput
    }
  | { readonly status: 'accepted'; readonly email: string }
  | { readonly status: 'unavailable' }
  | { readonly status: 'failed' }

/** The state a freshly rendered form starts in. Exported so the action and its tests share one. */
export const SIGN_UP_IDLE: SignUpFormState = { status: 'idle' }

/** Just enough of `FormData` to read a form, so the reader below is testable without a DOM. */
export type FormReader = { get(name: string): unknown }

/**
 * The four fields out of a submitted form.
 *
 * A field the form did not send reads as the empty string rather than throwing, and so does a value
 * that is not a string — which is what an uploaded file arrives as. The rules then refuse the empty
 * string in the page's own words, so a tampered submission and an empty one are answered the same
 * way and neither reaches the API.
 */
export const readSignUpForm = (form: FormReader): SignUpInput => ({
  firstName: readField(form, 'firstName'),
  lastName: readField(form, 'lastName'),
  email: readField(form, 'email'),
  mobile: readField(form, 'mobile'),
})

const readField = (form: FormReader, name: string): string => {
  const value = form.get(name)
  return typeof value === 'string' ? value : ''
}

/** `firstName` on the form, `first_name` on the wire. The API names its own fields. */
export const apiFieldName = (field: SignUpField): string =>
  field === 'firstName' ? 'first_name' : field === 'lastName' ? 'last_name' : field

/**
 * Field refusals out of an API response body, narrowed field by field.
 *
 * Here rather than in `sign-up-api.ts` because it is pure and that module is `server-only`: the
 * layering in `lib/` is rules in one file and the call that runs them in another, and it is what makes
 * this testable without a fetch.
 *
 * The body is data from another process, so nothing is asserted. A refusal naming a field this form
 * does not have, or a reason it cannot render, is **dropped rather than shown**: the alternative is
 * arbitrary text from an API response rendered beside our own wording, or a message keyed by
 * `undefined`.
 *
 * The shape read is `{"fields": {"email": ["email-malformed"]}}`, mirroring `ProfileRefusedOut` — the
 * one refusal shape this API already uses.
 */
export const readSignUpRefusals = (
  payload: Record<string, unknown>,
): readonly SignUpFieldRefusal[] => {
  const fields = payload.fields
  if (typeof fields !== 'object' || fields === null) return []

  const refusals: SignUpFieldRefusal[] = []

  for (const [field, reasons] of Object.entries(fields as Record<string, unknown>)) {
    const named = SIGN_UP_FIELDS.find((candidate) => apiFieldName(candidate) === field)
    if (named === undefined || !Array.isArray(reasons)) continue

    for (const reason of reasons) {
      const known = SIGN_UP_REFUSALS.find((candidate) => candidate === reason)
      if (known !== undefined) refusals.push({ field: named, reason: known })
    }
  }

  return refusals
}

/**
 * The two profile calls the store makes, and the shape they answer with.
 *
 * A module of its own rather than more functions in `lib/api.ts`, following the club's convention:
 * one screen's calls, in one file, so the general client stays the general client.
 *
 * **Two calls, where the club makes five.** The three avatar endpoints are not here. The photograph
 * is a platform feature and the endpoints work perfectly well for a store customer — what is missing
 * is a reason: a shopper's face is shown to nobody, since the store has no member directory, no
 * public profile and no swap zone. It is the first thing to add if that changes, and adding it means
 * this file, the cropper and one card rather than anything structural. Recorded in
 * `design/frontend.md` section 11.4 rather than left as a silent omission.
 */

import { ApiError, apiFetch } from './api'
import type { ProfileSubmission } from './profile'

/**
 * A customer's own record, mirroring `ProfileOut` in `accounts/schemas.py`.
 *
 * The club-shaped fields are declared because the payload carries them, and left unread because the
 * store has no use for them: `nickname` is blank for a customer, `id_number_masked` is blank because
 * nobody asked for a document, and `role` reports the most capable club role rather than anything
 * about shopping. A narrower type would be a second, quieter contract that drifts from the first.
 */
export type Profile = {
  first_name: string
  last_name: string
  /** The club's handle. Blank for a store customer. */
  nickname: string
  /** Shown, never editable here: it is the sign-in identifier. */
  email: string | null
  /** `+27` and nine digits, or blank. */
  mobile: string
  display_name: string
  /** ISO date, or null. A store customer is never asked for one. */
  date_of_birth: string | null
  date_of_birth_verified_at: string | null
  has_id_number: boolean
  id_number_masked: string
  has_avatar: boolean
  avatar_url: string | null
  role: string
  status: string
}

/** A refusal from a profile write, mirroring `ProfileRefusedOut`. */
export type ProfileRefusedBody = {
  detail: string
  /** Per-field messages, keyed by the API's field name (`first_name`, not `firstName`). */
  fields?: Record<string, string[]>
  /** True for the one refusal that is not about the value: the number belongs to someone else. */
  mobile_unavailable?: boolean
}

export const getProfile = () => apiFetch<Profile>('/api/accounts/me/profile')

/**
 * Save the three editable fields.
 *
 * A PUT carrying all three, matching the endpoint: the screen holds all three, so behaviour does not
 * depend on what this chose to omit.
 */
export const putProfile = (submission: ProfileSubmission) =>
  apiFetch<Profile>('/api/accounts/me/profile', {
    method: 'PUT',
    body: JSON.stringify(submission),
  })

/**
 * Whether an unknown value is a refusal body, checked field by field.
 *
 * The response is data from another process, so it is narrowed rather than asserted. A 422 whose body
 * is not the shape this expects falls through to `failed`, which says "could not be saved just
 * now" — true, and better than reading `fields` off `undefined` and rendering nothing.
 */
const isRefusalBody = (value: unknown): value is ProfileRefusedBody =>
  typeof value === 'object' &&
  value !== null &&
  'detail' in value &&
  typeof (value as { detail: unknown }).detail === 'string'

/**
 * The API's per-field messages, keyed by this form's field names.
 *
 * Django's wording is rendered as it arrives rather than translated into one of our own reasons, and
 * that is deliberate: the endpoint refuses things the form does not check — a mobile number already
 * on another account is the live example — so a mapping onto our vocabulary would have to invent a
 * reason for anything it did not recognise. What it *does* refuse to render is a field name this form
 * has no input for: a message with nowhere to appear would otherwise be dropped silently, and here it
 * is dropped deliberately, with the sentence saying so above it.
 *
 * The first message per field only. The endpoint sends a list, a field has one place to say something,
 * and stacking three sentences under one input is how a form becomes unreadable.
 */
export const refusalMessagesByField = (
  refusal: ProfileRefusedBody,
): Partial<Record<'firstName' | 'lastName' | 'mobile', string>> => {
  const byApiName = { first_name: 'firstName', last_name: 'lastName', mobile: 'mobile' } as const

  const messages: Partial<Record<'firstName' | 'lastName' | 'mobile', string>> = {}

  for (const [apiName, field] of Object.entries(byApiName)) {
    const sentences = refusal.fields?.[apiName]
    if (Array.isArray(sentences) && typeof sentences[0] === 'string' && sentences[0].length > 0) {
      messages[field] = sentences[0]
    }
  }

  return messages
}

export type SaveOutcome =
  | { readonly status: 'saved'; readonly profile: Profile }
  | { readonly status: 'refused'; readonly refusal: ProfileRefusedBody }
  | { readonly status: 'failed'; readonly reason: string }

/** The two statuses that carry a refusal the customer can act on. Anything else is a failure. */
const REFUSAL_STATUSES = [409, 422] as const

/**
 * Save, and report the three outcomes the screen draws differently.
 *
 * Never throws. A form that throws leaves somebody looking at a spinner, and the three cases here
 * genuinely are three screens: refusals marked up against their fields, one sentence about a mobile
 * number that belongs to somebody else, or "could not be saved just now".
 *
 * The per-field messages come off `ApiError.body`, which is why that property exists. `apiFetch`
 * throws before a caller could read the response, and the alternative — a second `fetch` here that
 * bypasses it — would be a second copy of the CSRF handling.
 */
export const saveProfile = async (submission: ProfileSubmission): Promise<SaveOutcome> => {
  try {
    return { status: 'saved', profile: await putProfile(submission) }
  } catch (caught) {
    const isRefusal =
      caught instanceof ApiError &&
      REFUSAL_STATUSES.some((status): boolean => status === caught.status)

    if (isRefusal && isRefusalBody(caught.body)) {
      return { status: 'refused', refusal: caught.body }
    }

    if (isRefusal) {
      // A refusal status with a body this does not recognise. The status still says the customer can
      // act on it, so the sentence is reported rather than swallowed into "try again".
      return { status: 'refused', refusal: { detail: (caught as ApiError).message } }
    }

    return {
      status: 'failed',
      reason: caught instanceof Error ? caught.message : 'The store could not be reached.',
    }
  }
}

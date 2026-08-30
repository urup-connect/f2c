/**
 * The register's calls from the browser, and the outcomes each one reports.
 *
 * A module of its own rather than more functions in `lib/api.ts`, following
 * `strain-catalogue-api.ts` and `profile-api.ts`: one area's calls, in one file,
 * so the general client stays the general client.
 *
 * Everything goes through `apiFetch`, which attaches the session cookie and the
 * CSRF token — mandatory here, because every write in this file is a POST or a
 * PUT and django-ninja's cookie auth enforces CSRF on both.
 *
 * ## Nothing here throws, except the two reads
 *
 * Every write returns an outcome, for the reason `strain-catalogue-api.ts`
 * gives: a form that throws leaves an administrator looking at a spinner, and
 * the three cases genuinely are three screens. `listMembers` and `readMember`
 * do throw, matching `listStrains` — the list screen catches and keeps its stale
 * rows on display, which is better than a table replaced by an error message.
 *
 * ## Why the identity read is a write
 *
 * `discloseIdentityNumber` is a POST, and it has to be. A GET is cacheable,
 * prefetchable and logged by every proxy between here and the administrator's
 * desk, and it has no body to carry the reason — which is the field that makes
 * the disclosure reviewable. See `app/club/membership/administration.py`.
 */

import { ApiError, apiFetch } from './api'
import type { Disclosure, Member, MemberRow, MemberSubmission } from './member-register'

/** Mirrors `MemberRefusedOut`. The same shape as `CatalogueRefusal`, deliberately. */
export type MemberRefusal = {
  detail: string
  /** Per-field messages, keyed as the API keys them (`first_name`, not `firstName`). */
  fields?: Record<string, string[]>
}

/**
 * The four narrowings the register offers.
 *
 * Blank means unfiltered, matching `RegisterFilters`: a `select` reset to "any"
 * submits an empty string, so blank and absent have to mean the same thing on
 * both sides.
 */
export type MemberQuery = {
  status?: string
  role?: string
  search?: string
  /** A number of days, as the string a `select` yields. Blank is unfiltered. */
  joined_within?: string
}

/**
 * A query object as a search string, dropping every blank.
 *
 * Blanks are dropped rather than sent, even though the API treats them as
 * absent. Two reasons, both from `catalogueQueryString`: the URL an administrator
 * can copy out of the address bar says what is actually being filtered, and
 * `?status=&role=&search=` in a server log tells nobody anything.
 *
 * There is a third reason here. A search term is a member's name or address, and
 * a query string is the part of a URL that reaches every access log — so this
 * sends the shortest one that answers the question and never a set of empty
 * keys alongside it.
 */
export const memberQueryString = (query: MemberQuery): string => {
  const parameters = new URLSearchParams()

  for (const [key, value] of Object.entries(query)) {
    const trimmed = (value ?? '').trim()
    if (trimmed !== '') parameters.set(key, trimmed)
  }

  const serialised = parameters.toString()
  return serialised === '' ? '' : `?${serialised}`
}

const MEMBERS = '/api/members'

export const listMembers = (query: MemberQuery = {}) =>
  apiFetch<MemberRow[]>(`${MEMBERS}${memberQueryString(query)}`)

export const readMember = (id: string) => apiFetch<Member>(`${MEMBERS}/${id}`)

/* -------------------------------------------------------------------------- */
/* Outcomes                                                                    */
/* -------------------------------------------------------------------------- */

export type MemberOutcome<T> =
  | { readonly status: 'saved'; readonly record: T }
  | { readonly status: 'refused'; readonly refusal: MemberRefusal }
  | { readonly status: 'failed'; readonly reason: string }

/**
 * Whether an unknown value is a refusal body, checked field by field.
 *
 * The response is data from another process, so it is narrowed rather than
 * asserted. A 422 whose body is not this shape falls through to `failed`, which
 * is true and better than reading `fields` off `undefined` and rendering
 * nothing.
 */
const isRefusal = (value: unknown): value is MemberRefusal =>
  typeof value === 'object' &&
  value !== null &&
  'detail' in value &&
  typeof (value as { detail: unknown }).detail === 'string'

/**
 * The statuses that carry something an administrator can act on.
 *
 * 422 is the service's own refusal, and on this router it is the *common* path:
 * an erased account, a sharing member, an administrator suspending themselves
 * and a reason too short to record all arrive as one. 409 is not used here and
 * is admitted anyway, for the reason `strain-catalogue-api.ts` gives.
 *
 * 403 is deliberately absent. It is not something to correct on the form — the
 * account does not hold `platform.disable_user` — so it reads as a failure,
 * which is what it is.
 */
const REFUSAL_STATUSES = [409, 422] as const

const attempt = async <T>(call: () => Promise<T>): Promise<MemberOutcome<T>> => {
  try {
    return { status: 'saved', record: await call() }
  } catch (caught) {
    const refusable =
      caught instanceof ApiError &&
      REFUSAL_STATUSES.some((status): boolean => status === caught.status)

    if (refusable && isRefusal(caught.body)) {
      return { status: 'refused', refusal: caught.body }
    }

    if (refusable) {
      // A refusal status carrying a body this does not recognise. The status
      // still says an administrator can act on it, so the sentence is reported
      // rather than swallowed into "try again".
      return { status: 'refused', refusal: { detail: caught.message } }
    }

    return {
      status: 'failed',
      reason: caught instanceof Error ? caught.message : 'The club could not be reached.',
    }
  }
}

/**
 * Save a member's details.
 *
 * A PUT carrying the whole record, matching the endpoint: the screen holds every
 * field and sends every field, so behaviour does not depend on what this chose
 * to omit.
 */
export const saveMember = (id: string, submission: MemberSubmission) =>
  attempt<Member>(() =>
    apiFetch<Member>(`${MEMBERS}/${id}`, {
      method: 'PUT',
      body: JSON.stringify(submission),
    }),
  )

/**
 * Suspend an account: block sign-in, and end every session it holds.
 *
 * A POST rather than a DELETE, because nothing is deleted. The whole record
 * comes back at its new standing, so the screen never has to guess what the
 * write did.
 */
export const suspendMember = (id: string) =>
  attempt<Member>(() => apiFetch<Member>(`${MEMBERS}/${id}/suspend`, { method: 'POST' }))

/** Lift a suspension, returning the account to Active. */
export const reinstateMember = (id: string) =>
  attempt<Member>(() => apiFetch<Member>(`${MEMBERS}/${id}/reinstate`, { method: 'POST' }))

/** The number, and the record that reading it happened. Mirrors `IdentityNumberOut`. */
export type IdentityDisclosure = {
  id_number: string
  disclosure: Disclosure
}

/**
 * Read a member's identity number in full, recording that it happened.
 *
 * The reason is required and travels in the body. It is written to the club's
 * disclosure ledger *before* the column is decrypted, so a number that comes
 * back is a number whose read is already logged — there is no call that returns
 * one without leaving the record.
 */
export const discloseIdentityNumber = (id: string, reason: string) =>
  attempt<IdentityDisclosure>(() =>
    apiFetch<IdentityDisclosure>(`${MEMBERS}/${id}/identity-number`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  )

/**
 * The catalogue calls the browser makes, and the outcomes each one reports.
 *
 * A module of its own rather than more functions in `lib/api.ts`, following
 * `profile-api.ts` and `club-documents-api.ts`: one area's calls, in one file,
 * so the general client stays the general client.
 *
 * Everything goes through `apiFetch`, which is what attaches the session cookie
 * and the CSRF token — mandatory here, because every write in this file is a
 * POST or a PUT and django-ninja's cookie auth enforces CSRF on both.
 *
 * ## Nothing here throws
 *
 * Every function returns an outcome. A form that throws leaves an administrator
 * looking at a spinner, and the three cases genuinely are three screens:
 * refusals marked up against their fields, a sentence about something the form
 * could not have known, and "could not be saved just now". The same shape as
 * `profile-api.saveProfile`, and for the same reason — but with one difference
 * worth stating, because the two files look alike.
 *
 * On the profile screen, an API refusal means the browser's rules and the
 * server's have drifted, because `checkProfile` duplicates all of them. Here it
 * is the *normal* path: whether "OG Kush" is already in the catalogue is not a
 * question a browser can answer, so `refused` is an ordinary outcome and its
 * per-field messages are the primary thing an administrator reads. See
 * `lib/strain-catalogue.ts`.
 */

import { ApiError, apiFetch } from './api'
import type {
  Strain,
  StrainRow,
  StrainSubmission,
  Term,
  Vocabularies,
} from './strain-catalogue'

/** Mirrors `RefusedOut`. The same shape as `ProfileRefusedBody`, deliberately. */
export type CatalogueRefusal = {
  detail: string
  /** Per-field messages, keyed as the API keys them (`strain_type`, not `strainType`). */
  fields?: Record<string, string[]>
}

/** What a retirement did, mirroring `StrainRetiredOut`. */
export type Retirement = {
  strain: Strain
  /**
   * How many live offers came off the shelf. Reported rather than recomputed:
   * `CultivatorStrainListingQuerySet.visible` filters on the strain's status too,
   * so after the write the browser could no longer count them.
   */
  listings_taken_down: number
}

/**
 * The three narrowings the list screen offers.
 *
 * Blank means unfiltered, matching `CatalogueFilters`: a `select` reset to "any"
 * submits an empty string, so blank and absent have to mean the same thing on
 * both sides.
 */
export type CatalogueQuery = {
  status?: string
  strain_type?: string
  search?: string
}

/**
 * A query object as a search string, dropping every blank.
 *
 * Blanks are dropped rather than sent, even though the API treats them as
 * absent. Two reasons: the URL an administrator can copy out of the address bar
 * says what is actually being filtered, and `?status=&strain_type=&search=` in a
 * server log tells nobody anything.
 */
export const catalogueQueryString = (query: CatalogueQuery): string => {
  const parameters = new URLSearchParams()

  for (const [key, value] of Object.entries(query)) {
    const trimmed = (value ?? '').trim()
    if (trimmed !== '') parameters.set(key, trimmed)
  }

  const serialised = parameters.toString()
  return serialised === '' ? '' : `?${serialised}`
}

const CATALOGUE = '/api/catalogue'

export const listStrains = (query: CatalogueQuery = {}) =>
  apiFetch<StrainRow[]>(`${CATALOGUE}/strains${catalogueQueryString(query)}`)

export const readStrain = (id: string) =>
  apiFetch<Strain>(`${CATALOGUE}/strains/${id}`)

export const listTerms = () => apiFetch<Vocabularies>(`${CATALOGUE}/terms`)

/* -------------------------------------------------------------------------- */
/* Outcomes                                                                    */
/* -------------------------------------------------------------------------- */

export type SaveOutcome<T> =
  | { readonly status: 'saved'; readonly record: T }
  | { readonly status: 'refused'; readonly refusal: CatalogueRefusal }
  | { readonly status: 'failed'; readonly reason: string }

/**
 * Whether an unknown value is a refusal body, checked field by field.
 *
 * The response is data from another process, so it is narrowed rather than
 * asserted. A 422 whose body is not this shape falls through to `failed`, which
 * is true and better than reading `fields` off `undefined` and rendering
 * nothing.
 */
const isRefusal = (value: unknown): value is CatalogueRefusal =>
  typeof value === 'object' &&
  value !== null &&
  'detail' in value &&
  typeof (value as { detail: unknown }).detail === 'string'

/**
 * The statuses that carry something an administrator can act on.
 *
 * 422 is the service's own refusal. 409 is not used by this router today and is
 * admitted anyway, because the profile endpoints use it for a uniqueness clash
 * and a catalogue endpoint growing one would otherwise silently become
 * "could not be saved just now".
 *
 * 403 is deliberately absent. It is not something to correct on the form — the
 * account does not hold `manage_strain_catalogue` — so it reads as a failure,
 * which is what it is.
 */
const REFUSAL_STATUSES = [409, 422] as const

/** Run a call and report the three outcomes the screens draw differently. */
const attempt = async <T>(call: () => Promise<T>): Promise<SaveOutcome<T>> => {
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

export const createStrain = (submission: StrainSubmission) =>
  attempt<Strain>(() =>
    apiFetch<Strain>(`${CATALOGUE}/strains`, {
      method: 'POST',
      body: JSON.stringify(submission),
    }),
  )

/**
 * Save an existing strain.
 *
 * A PUT carrying the whole record, matching the endpoint: the screen holds every
 * field and sends every field, so behaviour does not depend on what this chose
 * to omit. See `StrainIn` — the failure mode a patch has here is a cleared JSON
 * column quietly surviving the save that cleared it.
 */
export const saveStrain = (id: string, submission: StrainSubmission) =>
  attempt<Strain>(() =>
    apiFetch<Strain>(`${CATALOGUE}/strains/${id}`, {
      method: 'PUT',
      body: JSON.stringify(submission),
    }),
  )

/**
 * Retire a strain. This is what stands in for a delete.
 *
 * A POST rather than a DELETE, because nothing is deleted: both foreign keys
 * into a strain are `PROTECT`, so a strain the club has sold against cannot go
 * away, and the answer is `status = inactive` — which takes it out of the
 * member-facing catalogue and every live offer off the shelf, platform-wide, in
 * one act. Reinstating is `saveStrain` with the status set back.
 */
export const retireStrain = (id: string) =>
  attempt<Retirement>(() =>
    apiFetch<Retirement>(`${CATALOGUE}/strains/${id}/retire`, { method: 'POST' }),
  )

/** Which vocabulary a term belongs to. The segment the API names one by. */
export type TermKind = 'aromas' | 'effects'

export const createTerm = (kind: TermKind, name: string) =>
  attempt<Term>(() =>
    apiFetch<Term>(`${CATALOGUE}/terms/${kind}`, {
      method: 'POST',
      body: JSON.stringify({ name, is_available: true }),
    }),
  )

/**
 * Rename a term, or withdraw it by clearing `is_available`.
 *
 * One call for both, because they are one row. There is no delete: withdrawing a
 * term stops it being offered on new strains and leaves every strain that
 * already carries it untouched — deleting the row would strip it from all of
 * them with nothing to say it had happened.
 */
export const saveTerm = (
  kind: TermKind,
  id: string,
  name: string,
  isAvailable: boolean,
) =>
  attempt<Term>(() =>
    apiFetch<Term>(`${CATALOGUE}/terms/${kind}/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ name, is_available: isAvailable }),
    }),
  )

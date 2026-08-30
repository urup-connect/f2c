/**
 * The store's public documents, as pure logic.
 *
 * `GET /api/documents/published` answers with every document on this storefront that anybody may
 * read — the terms, the privacy notice, the data policy. The endpoint is built and storefront-scoped;
 * **the store's own documents are not written yet**, which is an item on `design/todo.md` Block B and
 * not a fault in this code. So the honest states are three rather than two, and separating them is
 * most of what this module is for:
 *
 * - `unavailable` — Django could not be asked. Something is wrong on our side and it says so.
 * - `none` — Django answered, and this storefront has nothing published. Nothing is wrong; there is
 *   simply nothing to read yet.
 * - `listed` — there are documents.
 *
 * Collapsing the first two into "no documents" is the failure worth avoiding: a shopper told the
 * store has no privacy notice, when in fact the API was unreachable, has been told something untrue
 * about a legal obligation.
 */

/** One document at the revision currently in force, mirroring `DocumentOut` in Django. */
export type PublishedDocument = {
  /** The stable slug: `terms`, `privacy-notice`, `data-policy`. */
  document: string
  title: string
  /** The revision label, as a string — a revision may be `2.1` or `2026-08`. Never parsed. */
  version: string
  /** Absolute, and Django's to build: it owns the revision, so it owns the address. */
  url: string
  /** The sentence a signing screen renders beside a checkbox. Nothing public reads it. */
  consent_text: string
  sha256: string
  requires_reacceptance: boolean
  /** ISO datetime. */
  effective_from: string
}

export type LegalList =
  | { readonly state: 'unavailable' }
  | { readonly state: 'none' }
  | { readonly state: 'listed'; readonly documents: readonly PublishedDocument[] }

/**
 * The three states, from what the server read.
 *
 * `null` is the unreachable case — `getPublishedDocuments` turns a failure into it rather than
 * throwing, so a legal page renders a sentence instead of a 500.
 */
export const legalList = (documents: readonly PublishedDocument[] | null): LegalList => {
  if (documents === null) return { state: 'unavailable' }
  if (documents.length === 0) return { state: 'none' }

  return { state: 'listed', documents: sortDocuments(documents) }
}

/**
 * Alphabetical by title, using a South African collator.
 *
 * Ordered here rather than left in the API's order because the API's order is not a promise, and a
 * legal index whose rows move between two page loads looks like a page that cannot make up its mind.
 * Alphabetical rather than by date: somebody arrives looking for a named document.
 *
 * The array is copied first — `sort` mutates, and the input is a response body that other callers on
 * the same render may still read.
 */
export const sortDocuments = (
  documents: readonly PublishedDocument[],
): readonly PublishedDocument[] =>
  [...documents].sort((left, right) => COLLATOR.compare(left.title, right.title))

const COLLATOR = new Intl.Collator('en-ZA', { sensitivity: 'base' })

const DATE = new Intl.DateTimeFormat('en-ZA', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
  calendar: 'gregory',
})

/**
 * When a revision took effect, as a South African reader writes it: 15 March 2026.
 *
 * `timeZone: 'UTC'` for the reason the club's profile formatter gives: formatted in a zone behind UTC
 * a date lands on the previous day, so a document that came into force on the first of the month
 * would be shown as the last day of the one before.
 *
 * An unparseable value reads as nothing held rather than as `Invalid Date`. Nobody should ever be
 * shown the string a date library produces when it gives up.
 */
export const formatEffectiveFrom = (iso: string): string | null => {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return null

  return DATE.format(parsed)
}

/**
 * The line under a document's title: which revision it is, and when it took effect.
 *
 * Both facts or just the revision — never a dangling "in force from" with nothing after it.
 */
export const revisionLine = (document: PublishedDocument, versionLabel: string, fromLabel: string): string => {
  const from = formatEffectiveFrom(document.effective_from)
  const version = `${versionLabel} ${document.version}`

  return from === null ? version : `${version} · ${fromLabel} ${from}`
}

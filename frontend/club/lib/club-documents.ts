/**
 * The three documents a joining member agrees to, and the rules about agreeing.
 *
 * **Django owns the file, the version and the wording.** They used to live here as constants, and
 * that is what changed: a revised document now means a revision published in the admin, and this
 * application reads whichever one is in force at the moment it renders. Nothing about a document
 * is deployable any more, which is the point — a club that revises its constitution should not
 * have to ship a frontend to say so.
 *
 * What is still here is the closed set of ids, which is a contract rather than content, and the
 * pure rules: what a ticked box posts, and what makes an agreement stale. Both run in the browser
 * and again on the server.
 *
 * See design/features/sign-up.md section 5, and documents/models.py for what is recorded against
 * each agreement.
 */

export const CLUB_DOCUMENT_IDS = ['club-rules', 'annexures', 'constitution'] as const

export type ClubDocumentId = (typeof CLUB_DOCUMENT_IDS)[number]

export const isClubDocumentId = (value: unknown): value is ClubDocumentId =>
  typeof value === 'string' && CLUB_DOCUMENT_IDS.some((id): boolean => id === value)

/**
 * What is recorded against a member for one document they agreed to.
 *
 * The revision travels with the agreement rather than being looked up later: "the current
 * document" answers what the document says today, not what the member read.
 *
 * `version` is a string, not a number. A revision may be labelled `2.1` or `2026-08`, and a
 * frontend that parsed it as a number would round-trip those into something else — recording an
 * agreement to a version that does not exist.
 */
export type ClubDocumentConsent = {
  readonly document: ClubDocumentId
  readonly version: string
}

/** One document at the revision currently in force, as Django reports it. */
export type ClubDocumentRevision = {
  readonly document: ClubDocumentId
  readonly title: string
  readonly version: string
  /** The address on the CDN. Built by Django's storage backend, never assembled here. */
  readonly url: string
  /**
   * The exact sentence rendered beside the checkbox.
   *
   * Read from the API rather than held in this application's copy, because Django records a digest
   * of it against every agreement. Two copies of the wording would eventually disagree, and the
   * one that disagreed would be the record of what a member asserted.
   */
  readonly consentText: string
}

/**
 * The revisions in force, keyed by document.
 *
 * Keyed rather than ordered, so a caller pairing a link with an agreement cannot pair it with the
 * wrong one — a checkbox saying *the constitution* that opens the annexures is not a consent.
 */
export type ClubDocumentRevisions = Readonly<Record<ClubDocumentId, ClubDocumentRevision>>

export type ClubDocumentsResult =
  | { readonly status: 'ready'; readonly revisions: ClubDocumentRevisions }
  | { readonly status: 'unusable'; readonly reason: string }

const entry = (value: unknown): ClubDocumentRevision | null => {
  if (typeof value !== 'object' || value === null) return null

  const record = value as Record<string, unknown>

  if (!isClubDocumentId(record.document)) return null
  if (typeof record.version !== 'string' || record.version.length === 0) return null
  if (typeof record.url !== 'string' || record.url.length === 0) return null
  if (typeof record.consent_text !== 'string' || record.consent_text.length === 0) return null

  return {
    document: record.document,
    title: typeof record.title === 'string' ? record.title : record.document,
    version: record.version,
    url: record.url,
    consentText: record.consent_text,
  }
}

/**
 * Narrow an API payload into the revisions in force. Pure, and never throws.
 *
 * **Refuses a partial list.** Every id in `CLUB_DOCUMENT_IDS` must be present, because a form
 * rendering two of three documents collects an agreement that is incomplete in a way nobody can
 * see. Django refuses the same case with a 503; this refuses it again rather than trusting that it
 * did, since a stale cache or a proxy can produce a body neither side sent.
 *
 * An id this application does not know is ignored rather than refused: staff adding a fourth
 * document in the admin must not take sign-up down until a deploy catches up. It will not be shown
 * or agreed to, which is the safe half of that trade — and it is why Django's own check is on
 * `required_at_signup` rather than on this list.
 */
export const readClubDocumentRevisions = (payload: unknown): ClubDocumentsResult => {
  const documents =
    typeof payload === 'object' && payload !== null
      ? (payload as { documents?: unknown }).documents
      : undefined

  if (!Array.isArray(documents)) {
    return { status: 'unusable', reason: 'The documents response carried no list.' }
  }

  const revisions: Partial<Record<ClubDocumentId, ClubDocumentRevision>> = {}

  for (const value of documents) {
    const revision = entry(value)

    if (revision) revisions[revision.document] = revision
  }

  const absent = CLUB_DOCUMENT_IDS.filter((id) => !revisions[id])

  if (absent.length > 0) {
    return {
      status: 'unusable',
      reason: `No revision is in force for: ${absent.join(', ')}.`,
    }
  }

  return { status: 'ready', revisions: revisions as ClubDocumentRevisions }
}

/**
 * The value each agreement checkbox posts when it is ticked.
 *
 * Explicit rather than the browser's default `on`, so what the rule accepts is written down in one
 * place and read by both the form and the check below.
 */
export const CLUB_CONSENT_VALUE = 'yes'

export type ClubConsentCheck =
  | { readonly status: 'valid' }
  | { readonly status: 'invalid'; readonly reason: 'required' }

/**
 * Whether a member ticked the box.
 *
 * An unticked checkbox is not posted at all, so an absent field and an empty one mean the same
 * thing here, and both are refused. Anything else — `on`, `true`, a padded value — is refused
 * rather than interpreted: no browser of ours sends it, so accepting it would only mean accepting
 * an agreement nobody made.
 */
export const checkClubConsent = (value: string): ClubConsentCheck =>
  value === CLUB_CONSENT_VALUE ? { status: 'valid' } : { status: 'invalid', reason: 'required' }

/** The hidden field carrying the revision a form was rendered against. */
export const clubVersionField = (document: ClubDocumentId) => `version-${document}`

export type ClubVersionCheck =
  | { readonly status: 'valid' }
  | { readonly status: 'invalid'; readonly reason: 'superseded' }

/**
 * Whether the revision a member was shown is still the one in force.
 *
 * A revision can be published between a page rendering and its form being submitted, and the
 * submission is then an agreement to text the member never read. Refused rather than quietly
 * upgraded to the current version, which is the only answer that keeps the ledger honest.
 */
export const checkClubDocumentVersion = (shown: string, inForce: string): ClubVersionCheck =>
  shown === inForce ? { status: 'valid' } : { status: 'invalid', reason: 'superseded' }

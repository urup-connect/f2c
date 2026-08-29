/**
 * Club document revisions for the unit suite.
 *
 * Outside `lib/` on purpose: it is neither shipped code nor a test, and the coverage report reads
 * `{app,components,lib}`.
 *
 * The addresses and versions here are invented. The real ones live in Django and are published by
 * staff, so a test that named one would be a test that fails the day a document is revised — which
 * is the whole thing this feature was built to allow.
 */

import { CLUB_DOCUMENT_IDS } from '@/lib/club-documents'
import type { ClubDocumentId, ClubDocumentRevisions } from '@/lib/club-documents'

const TITLES: Readonly<Record<ClubDocumentId, string>> = {
  'club-rules': 'Club Rules',
  annexures: 'Annexures',
  constitution: 'Constitution',
}

/**
 * The three revisions in force, all at the version given.
 *
 * `versions` overrides individual documents, which is how a test sets up the case where one
 * document has moved on and the form is still carrying the old number.
 */
export const clubDocumentRevisions = (
  versions: Partial<Record<ClubDocumentId, string>> = {},
): ClubDocumentRevisions =>
  Object.fromEntries(
    CLUB_DOCUMENT_IDS.map((document) => {
      const version = versions[document] ?? '1'

      return [
        document,
        {
          document,
          title: TITLES[document],
          version,
          url: `https://static.example.invalid/collective/documents/${document}/${version}/doc.pdf`,
          consentText: `I have read and agree to the ${TITLES[document]}`,
        },
      ]
    }),
  ) as ClubDocumentRevisions

/** The same three, as the API sends them. For testing the reader rather than its output. */
export const clubDocumentsPayload = (
  versions: Partial<Record<ClubDocumentId, string>> = {},
) => ({
  documents: Object.values(clubDocumentRevisions(versions)).map((revision) => ({
    document: revision.document,
    title: revision.title,
    version: revision.version,
    url: revision.url,
    consent_text: revision.consentText,
    sha256: 'a'.repeat(64),
    requires_reacceptance: false,
    effective_from: '2026-08-24T09:00:00Z',
  })),
})

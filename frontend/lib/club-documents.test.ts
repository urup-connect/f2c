import { describe, expect, test } from 'vitest'
import {
  CLUB_CONSENT_VALUE,
  CLUB_DOCUMENT_IDS,
  checkClubConsent,
  checkClubDocumentVersion,
  clubVersionField,
  isClubDocumentId,
  readClubDocumentRevisions,
} from './club-documents'
import { clubDocumentsPayload } from '@/test-support/club-documents'

/*
 * design/features/sign-up.md section 5.
 *
 * The file names and version numbers that used to be asserted here are gone: Django owns them now,
 * and a revised document is published rather than deployed. What is left is the closed set of ids
 * and the two pure rules — what a ticked box posts, and what makes an agreement stale.
 */

describe('the club document ids', () => {
  test('are the three a joining member agrees to, in the order the form reads them', () => {
    expect([...CLUB_DOCUMENT_IDS]).toEqual(['club-rules', 'annexures', 'constitution'])
  })

  test('are a closed set, so an id from the API cannot walk in unrecognised', () => {
    for (const id of CLUB_DOCUMENT_IDS) {
      expect(isClubDocumentId(id)).toBe(true)
    }

    for (const value of ['club-newsletter', '', 'CLUB-RULES', null, undefined, 7, {}]) {
      expect(isClubDocumentId(value)).toBe(false)
    }
  })
})

describe('reading the revisions in force', () => {
  test('keys them by document, so a link cannot be attached to the wrong agreement', () => {
    const result = readClubDocumentRevisions(clubDocumentsPayload())

    expect(result.status).toBe('ready')
    if (result.status !== 'ready') return

    for (const id of CLUB_DOCUMENT_IDS) {
      expect(result.revisions[id].document).toBe(id)
    }
  })

  test('carries the address, the version and the wording of each', () => {
    const result = readClubDocumentRevisions(clubDocumentsPayload({ constitution: '3' }))

    expect(result.status).toBe('ready')
    if (result.status !== 'ready') return

    const constitution = result.revisions.constitution

    expect(constitution.version).toBe('3')
    expect(constitution.url).toContain('/documents/constitution/3/')
    expect(constitution.consentText).toBe('I have read and agree to the Constitution')
  })

  test('keeps a version as the string it arrived as, rather than a number', () => {
    /*
     * A revision may be labelled 2.1 or 2026-08. Parsing either as a number would record an
     * agreement to a version that does not exist.
     */
    const result = readClubDocumentRevisions(clubDocumentsPayload({ annexures: '2.10' }))

    expect(result.status).toBe('ready')
    if (result.status !== 'ready') return

    expect(result.revisions.annexures.version).toBe('2.10')
  })

  test('refuses a partial list rather than returning the documents it did get', () => {
    /*
     * The point of the whole reader. A form rendering two of three documents collects an agreement
     * that is incomplete in a way nobody can see, including the club later in a dispute.
     */
    const payload = clubDocumentsPayload()
    payload.documents = payload.documents.filter(({ document }) => document !== 'annexures')

    const result = readClubDocumentRevisions(payload)

    expect(result.status).toBe('unusable')
    if (result.status !== 'unusable') return

    expect(result.reason).toContain('annexures')
  })

  test.each([
    ['nothing at all', undefined],
    ['a body that is not an object', 'documents'],
    ['a body with no list', { documents: 'club-rules' }],
    ['an empty list', { documents: [] }],
  ])('refuses %s', (_name, payload) => {
    expect(readClubDocumentRevisions(payload).status).toBe('unusable')
  })

  test('refuses an entry missing the version, the address or the wording', () => {
    for (const field of ['version', 'url', 'consent_text']) {
      const payload = clubDocumentsPayload()
      const entry = payload.documents[0] as unknown as Record<string, unknown>

      delete entry[field]

      expect(readClubDocumentRevisions(payload).status).toBe('unusable')
    }
  })

  test('ignores a document it does not know, rather than refusing the lot', () => {
    /*
     * Staff adding a fourth document in the admin must not take sign-up down until a deploy catches
     * up. It cannot be shown or agreed to, which is the safe half of that trade.
     */
    const payload = clubDocumentsPayload()

    // Cast deliberately: the point is an id from outside the closed set, which is what a fourth
    // document published in the admin would be until a deploy catches up.
    payload.documents.push({
      ...payload.documents[0],
      document: 'privacy-notice' as (typeof CLUB_DOCUMENT_IDS)[number],
    })

    expect(readClubDocumentRevisions(payload).status).toBe('ready')
  })
})

describe('an agreement', () => {
  test('is accepted when the form sends the value it sends', () => {
    expect(checkClubConsent(CLUB_CONSENT_VALUE)).toEqual({ status: 'valid' })
  })

  test('is refused when the box was never ticked, so nothing was posted', () => {
    // An unticked checkbox posts nothing at all, which arrives as an empty value.
    expect(checkClubConsent('')).toEqual({ status: 'invalid', reason: 'required' })
  })

  test.each(['on', 'true', '1', 'YES', ' yes', 'yes '])(
    'is refused for %o, which no browser of ours would send',
    (value) => {
      // Refused rather than interpreted.
      expect(checkClubConsent(value)).toEqual({ status: 'invalid', reason: 'required' })
    },
  )
})

describe('the version an agreement was given against', () => {
  test('travels in a field named for its document', () => {
    // Keyed, like the revisions themselves: one document's version cannot land on another's box.
    const names = CLUB_DOCUMENT_IDS.map(clubVersionField)

    expect(new Set(names).size).toBe(CLUB_DOCUMENT_IDS.length)
    expect(clubVersionField('constitution')).toBe('version-constitution')
  })

  test('is valid while it is still the one in force', () => {
    expect(checkClubDocumentVersion('2', '2')).toEqual({ status: 'valid' })
  })

  test('is refused once the document has moved on', () => {
    // Refused rather than upgraded: a tick beside v1's wording is not an agreement to v2.
    expect(checkClubDocumentVersion('1', '2')).toEqual({
      status: 'invalid',
      reason: 'superseded',
    })
  })

  test('is refused when the form carried no version at all', () => {
    expect(checkClubDocumentVersion('', '1')).toEqual({
      status: 'invalid',
      reason: 'superseded',
    })
  })
})

import { describe, expect, test } from 'vitest'
import { PENDING_PAYMENT, readRegistrationRefusals } from './registration'
import { MEMBER_CONSENT_FIELDS, isMemberDetailsRefusal } from './member-details'
import { CLUB_DOCUMENT_IDS } from './club-documents'

/*
 * design/features/sign-up.md section 6.
 *
 * This module is the join between Django's refusal and the form's own error handling, and the
 * failure it exists to prevent is silent: a refusal that maps to nothing lands on no field, the
 * error summary shows nothing, and the member is returned to a form that looks as though it
 * submitted. So the tests are mostly about a refusal *arriving* rather than about its wording.
 */

describe('a taken nickname', () => {
  test('lands on the nickname field', () => {
    expect(readRegistrationRefusals({ nickname_unavailable: true })).toEqual([
      { field: 'nickname', reason: 'nickname-unavailable' },
    ])
  })

  test('is only read from `true`, not from anything truthy', () => {
    /*
     * A body that carries a string, a number or a missing field is not a body saying the nickname
     * is taken. Refusing to interpret one means a malformed answer becomes unusable — which the
     * caller shows as a fault of ours — rather than an error against a field the member chose
     * correctly.
     */
    for (const value of ['true', 1, 'yes', {}, null, undefined]) {
      expect(readRegistrationRefusals({ nickname_unavailable: value })).toEqual([])
    }
  })
})

describe('a superseded document', () => {
  test('lands on that document’s checkbox', () => {
    expect(readRegistrationRefusals({ superseded_documents: ['annexures'] })).toEqual([
      { field: 'agreeAnnexures', reason: 'consent-superseded' },
    ])
  })

  test('maps every document the form can show', () => {
    // What stops a fourth document arriving with no box for its refusal to land on.
    for (const document of CLUB_DOCUMENT_IDS) {
      expect(readRegistrationRefusals({ superseded_documents: [document] })).toHaveLength(1)
    }
  })

  test('maps each one to its own field, never to another’s', () => {
    /*
     * A refusal about the constitution shown against the annexures is worse than no refusal: the
     * member re-reads the wrong document and submits the same thing again.
     */
    for (const { field, document } of MEMBER_CONSENT_FIELDS) {
      expect(readRegistrationRefusals({ superseded_documents: [document] })).toEqual([
        { field, reason: 'consent-superseded' },
      ])
    }
  })

  test('reports all of them when several moved at once', () => {
    const refusals = readRegistrationRefusals({
      superseded_documents: ['club-rules', 'constitution'],
    })

    expect(refusals.map(({ field }) => field)).toEqual([
      'agreeClubRules',
      'agreeConstitution',
    ])
  })

  test('ignores a document id this application does not know', () => {
    /*
     * The same trade `readClubDocumentRevisions` makes: staff publishing a fourth document must
     * not take sign-up down until a deploy catches up.
     */
    expect(readRegistrationRefusals({ superseded_documents: ['code-of-conduct'] })).toEqual([])
  })

  test('ignores entries that are not strings', () => {
    expect(readRegistrationRefusals({ superseded_documents: [1, null, {}] })).toEqual([])
  })

  test('reads nothing from a value that is not a list', () => {
    for (const value of ['club-rules', 1, {}, null, undefined]) {
      expect(readRegistrationRefusals({ superseded_documents: value })).toEqual([])
    }
  })
})

describe('both refusals at once', () => {
  test('are both reported, nickname first, so the summary reads top to bottom', () => {
    const refusals = readRegistrationRefusals({
      nickname_unavailable: true,
      superseded_documents: ['annexures'],
    })

    expect(refusals).toEqual([
      { field: 'nickname', reason: 'nickname-unavailable' },
      { field: 'agreeAnnexures', reason: 'consent-superseded' },
    ])
  })
})

describe('an answer carrying no refusal', () => {
  test('reads as none, which the caller must treat as unusable', () => {
    // Asserted here so the contract the API module relies on is written down.
    expect(readRegistrationRefusals({})).toEqual([])
    expect(readRegistrationRefusals({ detail: 'something went wrong' })).toEqual([])
  })
})

describe('every reason this module produces', () => {
  test('is one the form already knows how to render', () => {
    // Otherwise a refusal survives the query string and is dropped on the way back in.
    const produced = readRegistrationRefusals({
      nickname_unavailable: true,
      superseded_documents: [...CLUB_DOCUMENT_IDS],
    })

    expect(produced).toHaveLength(CLUB_DOCUMENT_IDS.length + 1)

    for (const { reason } of produced) {
      expect(isMemberDetailsRefusal(reason)).toBe(true)
    }
  })
})

describe('the status a registration lands at', () => {
  test('is the one Django reports', () => {
    // Mirrors UserStatus.PENDING_PAYMENT. A drift here shows the confirmation screen as unusable.
    expect(PENDING_PAYMENT).toBe('pending_payment')
  })
})

import { describe, expect, test } from 'vitest'
import {
  formatEffectiveFrom,
  legalList,
  revisionLine,
  sortDocuments,
  type PublishedDocument,
} from './documents'

const document = (overrides: Partial<PublishedDocument> = {}): PublishedDocument => ({
  document: 'terms',
  title: 'Terms of use',
  version: '1.0',
  url: 'https://api.example.co.za/media/documents/market/terms/1.0/terms.pdf',
  consent_text: 'I agree to the terms of use.',
  sha256: 'a'.repeat(64),
  requires_reacceptance: false,
  effective_from: '2026-03-15T00:00:00Z',
  ...overrides,
})

describe('legalList', () => {
  test('separates an unreachable API from a storefront with nothing published', () => {
    /*
     * The distinction this module exists for. Telling a shopper the store has no privacy notice, on a
     * day when it has one and the network was down, is an untrue statement about a legal obligation.
     */
    expect(legalList(null)).toEqual({ state: 'unavailable' })
    expect(legalList([])).toEqual({ state: 'none' })
  })

  test('lists what there is', () => {
    const list = legalList([document()])

    expect(list.state).toBe('listed')
    expect(list.state === 'listed' && list.documents).toHaveLength(1)
  })
})

describe('sortDocuments', () => {
  test('orders by title, so the index does not move between two page loads', () => {
    const sorted = sortDocuments([
      document({ document: 'terms', title: 'Terms of use' }),
      document({ document: 'data', title: 'Data policy' }),
      document({ document: 'privacy', title: 'Privacy notice' }),
    ])

    expect(sorted.map((entry) => entry.title)).toEqual([
      'Data policy',
      'Privacy notice',
      'Terms of use',
    ])
  })

  test('does not mutate what it was given', () => {
    // The input is a response body other callers on the same render may still read.
    const documents = [document({ title: 'Terms of use' }), document({ title: 'Data policy' })]

    sortDocuments(documents)

    expect(documents[0].title).toBe('Terms of use')
  })
})

describe('formatEffectiveFrom', () => {
  test('writes a date the way a South African reader does', () => {
    expect(formatEffectiveFrom('2026-03-15T00:00:00Z')).toBe('15 March 2026')
  })

  test('does not shift the day, whatever the reader is set to', () => {
    // An ISO date is read as midnight UTC; formatted in a zone behind UTC it lands on the day before,
    // which would show a document as taking effect on the last day of the previous month.
    expect(formatEffectiveFrom('2026-03-01T00:00:00Z')).toBe('1 March 2026')
  })

  test('reads an unparseable value as nothing held', () => {
    expect(formatEffectiveFrom('not a date')).toBeNull()
    expect(formatEffectiveFrom('')).toBeNull()
  })
})

describe('revisionLine', () => {
  test('names the revision and when it took effect', () => {
    expect(revisionLine(document(), 'Revision', 'in force from')).toBe(
      'Revision 1.0 · in force from 15 March 2026',
    )
  })

  test('drops the date rather than dangling the phrase that introduces it', () => {
    expect(
      revisionLine(document({ effective_from: 'nonsense' }), 'Revision', 'in force from'),
    ).toBe('Revision 1.0')
  })

  test('keeps a version label that is not a number', () => {
    // A revision may be labelled 2.1 or 2026-08. Never parsed, only shown.
    expect(revisionLine(document({ version: '2026-08' }), 'Revision', 'from')).toContain(
      'Revision 2026-08',
    )
  })
})

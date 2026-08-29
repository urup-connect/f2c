import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { legalList, type PublishedDocument } from '@/lib/documents'
import { LEGAL } from '@/lib/legal-content'
import { DocumentList } from './DocumentList'

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

describe('DocumentList', () => {
  test('lists each document with its revision and effective date', () => {
    render(<DocumentList list={legalList([document()])} />)

    expect(screen.getByRole('heading', { name: 'Terms of use' })).toBeInTheDocument()
    expect(screen.getByText(/Revision 1\.0/)).toBeInTheDocument()
    expect(screen.getByText(/15 March 2026/)).toBeInTheDocument()
  })

  test('names the document in its own link, and points at what Django serves', () => {
    render(<DocumentList list={legalList([document()])} />)

    expect(screen.getByRole('link', { name: 'Read Terms of use' })).toHaveAttribute(
      'href',
      'https://api.example.co.za/media/documents/market/terms/1.0/terms.pdf',
    )
  })

  test('opens documents in place rather than hijacking the tab', () => {
    render(<DocumentList list={legalList([document()])} />)

    expect(screen.getByRole('link', { name: 'Read Terms of use' })).not.toHaveAttribute('target')
  })

  test('says nothing is published yet, without reading as an error', () => {
    render(<DocumentList list={legalList([])} />)

    expect(screen.getByText(LEGAL.noneHeading)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('says an unreachable API is our fault, and says it as a refusal', () => {
    /*
     * The distinction the whole module exists for: telling a shopper the store has no privacy notice
     * when in fact the API was down is an untrue statement about a legal obligation.
     */
    render(<DocumentList list={legalList(null)} />)

    expect(screen.getByRole('alert')).toHaveTextContent(LEGAL.unavailableBody)
    expect(screen.queryByText(LEGAL.noneHeading)).not.toBeInTheDocument()
  })
})

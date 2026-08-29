import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { DetailList } from './DetailList'
import { DETAILS_CARD } from '@/lib/club-content'
import type { DetailRow } from '@/lib/club-account'

const ROWS: readonly DetailRow[] = [
  { key: 'name', label: 'Name', value: 'Thandi Mokoena' },
  { key: 'nickname', label: 'Nickname', value: 'greenfingers' },
  { key: 'mobile', label: 'Mobile number', value: null },
]

describe('DetailList', () => {
  test('shows every label', () => {
    render(<DetailList rows={ROWS} />)

    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Nickname')).toBeInTheDocument()
    expect(screen.getByText('Mobile number')).toBeInTheDocument()
  })

  test('shows every value the club holds', () => {
    render(<DetailList rows={ROWS} />)

    expect(screen.getByText('Thandi Mokoena')).toBeInTheDocument()
    expect(screen.getByText('greenfingers')).toBeInTheDocument()
  })

  test('says a field is absent rather than leaving a blank line', () => {
    // A blank reads as a page that failed to draw. This is a fact about the record.
    render(<DetailList rows={ROWS} />)

    expect(screen.getByText(DETAILS_CARD.blank)).toBeInTheDocument()
  })

  test('pairs each value with its own label', () => {
    const { container } = render(<DetailList rows={ROWS} />)

    const terms = [...container.querySelectorAll('dt')].map((node) => node.textContent)
    const values = [...container.querySelectorAll('dd')].map((node) => node.textContent)

    expect(terms).toEqual(['Name', 'Nickname', 'Mobile number'])
    expect(values).toEqual(['Thandi Mokoena', 'greenfingers', DETAILS_CARD.blank])
  })

  test('renders nothing at all for no rows', () => {
    const { container } = render(<DetailList rows={[]} />)

    expect(container.querySelectorAll('dt')).toHaveLength(0)
  })
})

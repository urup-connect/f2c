import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { VALUES } from '@/lib/landing-content'
import { BrandValues } from './BrandValues'

/* design/features/landing-page-engagement.md criteria 6, 10 and 11. */

describe('BrandValues', () => {
  test('is headed at level two, below the page heading', () => {
    render(<BrandValues />)

    expect(screen.getByRole('heading', { level: 2, name: VALUES.heading })).toBeInTheDocument()
  })

  test('shows all four values the guidelines deck names', () => {
    render(<BrandValues />)

    const cards = screen.getAllByRole('heading', { level: 3 })

    expect(cards.map((card) => card.textContent)).toEqual(VALUES.items.map((item) => item.label))
  })

  test('shows each value description', () => {
    render(<BrandValues />)

    for (const item of VALUES.items) {
      expect(screen.getByText(item.description)).toBeInTheDocument()
    }
  })

  test('is a landmark named by its own heading, so it can be navigated to', () => {
    render(<BrandValues />)

    expect(screen.getByRole('region', { name: VALUES.heading })).toBeInTheDocument()
  })

  test('announces no icon, the labels carrying the meaning', () => {
    const { container } = render(<BrandValues />)
    const icons = container.querySelectorAll('svg')

    expect(icons.length).toBe(VALUES.items.length)
    for (const icon of icons) expect(icon).toHaveAttribute('aria-hidden', 'true')
  })
})

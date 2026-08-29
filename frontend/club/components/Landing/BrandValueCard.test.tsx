import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { BrandValueCard } from './BrandValueCard'

/* design/features/landing-page-engagement.md criteria 10 and 11. */

describe('BrandValueCard', () => {
  test('shows the value and its one-line description', () => {
    render(
      <BrandValueCard
        iconKey="community"
        label="Community first"
        description="We grow together and succeed together."
      />,
    )

    expect(screen.getByRole('heading', { level: 3, name: 'Community first' })).toBeInTheDocument()
    expect(screen.getByText('We grow together and succeed together.')).toBeInTheDocument()
  })

  test('the icon adds nothing for a screen reader to announce', () => {
    const { container } = render(
      <BrandValueCard iconKey="trust" label="Trust and transparency" description="Open." />,
    )

    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  test('carries no interactive control, being a statement rather than an action', () => {
    render(<BrandValueCard iconKey="quality" label="Quality and care" description="Premium." />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

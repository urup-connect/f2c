import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { STRAPLINE_SEGMENTS } from '@/lib/landing-content'
import { StraplineRibbon } from './StraplineRibbon'

/* design/features/landing-page-engagement.md criterion 9. */

describe('StraplineRibbon', () => {
  test.each(STRAPLINE_SEGMENTS)('shows the "%s" segment', (segment) => {
    render(<StraplineRibbon />)

    expect(screen.getByText(segment)).toBeInTheDocument()
  })

  test('the separators between segments are not announced', () => {
    /*
     * Criterion 9. Without this the strapline reads as three phrases joined by punctuation
     * a screen reader has no reason to say out loud.
     */
    const { container } = render(<StraplineRibbon />)
    const separators = container.querySelectorAll('[aria-hidden="true"]')

    expect(separators.length).toBe(STRAPLINE_SEGMENTS.length - 1)
  })

  test('carries no heading, being a band rather than a section', () => {
    render(<StraplineRibbon />)

    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  test('does not move, so there is nothing a reader has to pause', () => {
    /*
     * WCAG 2.2.2. A looping marquee would need a pause control, and a scroll-triggered reveal
     * would make the front door depend on JavaScript to show its own content.
     * See design/features/landing-page-engagement.md section 6.6.
     */
    const { container } = render(<StraplineRibbon />)

    expect(container.innerHTML).not.toMatch(/animate-|animation|marquee|transition-transform/)
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { BRAND_IMAGERY } from '@/lib/brand'
import { STORY } from '@/lib/landing-content'
import { BrandStory } from './BrandStory'

/* design/features/landing-page-engagement.md criteria 6, 12, 16 and 17. */

describe('BrandStory', () => {
  test('is headed at level two, below the page heading', () => {
    render(<BrandStory />)

    expect(screen.getByRole('heading', { level: 2, name: STORY.heading })).toBeInTheDocument()
  })

  test('tells the roots-and-badge story in body copy', () => {
    render(<BrandStory />)

    for (const paragraph of STORY.paragraphs) {
      expect(screen.getByText(paragraph)).toBeInTheDocument()
    }
  })

  test('shows the three steps, in order', () => {
    render(<BrandStory />)

    const steps = screen.getAllByRole('heading', { level: 3 })

    expect(steps.map((step) => step.textContent)).toEqual(['Planted', 'Tended', 'Shared'])
  })

  test('shows a photograph for the section and one for each step', () => {
    render(<BrandStory />)

    const alts = [STORY.imageKey, ...STORY.steps.map((step) => step.imageKey)].map(
      (key) => BRAND_IMAGERY[key].alt,
    )

    for (const alt of alts) expect(screen.getByAltText(alt)).toBeInTheDocument()
  })

  test('is a landmark named by its own heading', () => {
    render(<BrandStory />)

    expect(screen.getByRole('region', { name: STORY.heading })).toBeInTheDocument()
  })

  test('reads without its photographs, which illustrate rather than inform', () => {
    /*
     * The imagery licence is not confirmed for web use, so the section is built to survive
     * losing it. See design/features/landing-page-engagement.md risk 1.
     */
    render(<BrandStory />)

    for (const step of STORY.steps) {
      expect(screen.getByText(step.description)).toBeInTheDocument()
    }
  })
})

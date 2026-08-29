import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { BRAND_IMAGERY, type BrandImageKey } from '@/lib/brand'
import { STEP_IMAGE_WIDTH, StoryStep } from './StoryStep'

/* design/features/landing-page-engagement.md criteria 12, 16 and 17. */

describe('StoryStep', () => {
  test('shows the step and its one line', () => {
    render(
      <StoryStep
        imageKey="handsSeedling"
        label="Planted"
        description="Every plant starts with a cultivator who chose it."
      />,
    )

    expect(screen.getByRole('heading', { level: 3, name: 'Planted' })).toBeInTheDocument()
    expect(
      screen.getByText('Every plant starts with a cultivator who chose it.'),
    ).toBeInTheDocument()
  })

  test('shows the photograph the manifest names, with its alt text', () => {
    render(<StoryStep imageKey="glovedHarvest" label="Tended" description="Grown with care." />)

    expect(screen.getByAltText(BRAND_IMAGERY.glovedHarvest.alt)).toBeInTheDocument()
  })

  test('draws every step at the same width, so the labels sit on one line', () => {
    for (const imageKey of ['handsSeedling', 'glovedHarvest', 'fieldSunrise'] as const) {
      const { unmount } = render(
        <StoryStep imageKey={imageKey} label="Step" description="A line." />,
      )

      expect(screen.getByAltText(BRAND_IMAGERY[imageKey].alt)).toHaveAttribute(
        'width',
        String(STEP_IMAGE_WIDTH),
      )
      unmount()
    }
  })

  test('that shared width is within every step image ceiling', () => {
    /*
     * Criterion 16. A uniform box only works while it fits the smallest file — this is what
     * fails if a future step image cannot carry 140px at 2x.
     */
    const stepKeys: BrandImageKey[] = ['handsSeedling', 'glovedHarvest', 'fieldSunrise']

    for (const imageKey of stepKeys) {
      expect(STEP_IMAGE_WIDTH).toBeLessThanOrEqual(BRAND_IMAGERY[imageKey].maxRenderedWidth)
    }
  })
})

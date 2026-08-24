import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { BRAND_IMAGERY, type BrandImageKey } from '@/lib/brand'
import { BrandImage } from './BrandImage'

/* design/features/landing-page-engagement.md criteria 16 and 17, sections 6.2 and 6.3. */

const keys = Object.keys(BRAND_IMAGERY) as BrandImageKey[]

describe('BrandImage', () => {
  test.each(keys)('renders %s with the alt text the manifest supplies', (imageKey) => {
    const { alt, maxRenderedWidth } = BRAND_IMAGERY[imageKey]
    render(<BrandImage imageKey={imageKey} width={maxRenderedWidth} />)

    expect(screen.getByAltText(alt)).toBeInTheDocument()
  })

  test.each(keys)('%s reserves its own space, so the page does not shift', (imageKey) => {
    const { alt, width, height, maxRenderedWidth } = BRAND_IMAGERY[imageKey]
    render(<BrandImage imageKey={imageKey} width={maxRenderedWidth} />)

    const image = screen.getByAltText(alt)

    expect(image).toHaveAttribute('width', String(maxRenderedWidth))
    expect(image).toHaveAttribute(
      'height',
      String(Math.round((maxRenderedWidth * height) / width)),
    )
  })

  test('reserves the exact box it is given, when the caller crops to its own shape', () => {
    /*
     * Criterion 17. A derived height rounds to a whole pixel while the browser lays out the
     * half, and the two then disagree by one — which is both a reserved box that is fractionally
     * wrong and a next/image development warning. An explicit height is honoured as given.
     */
    render(<BrandImage imageKey="leafCanopy" width={520} height={347} />)

    const image = screen.getByAltText(BRAND_IMAGERY.leafCanopy.alt)

    expect(image).toHaveAttribute('width', '520')
    expect(image).toHaveAttribute('height', '347')
  })

  test('still refuses an over-wide request when a height is given', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => render(<BrandImage imageKey="handsSeedling" width={500} height={200} />)).toThrow(
      /handsSeedling/,
    )

    consoleError.mockRestore()
  })

  test('renders the artwork for the requested entry', () => {
    const { alt, src, maxRenderedWidth } = BRAND_IMAGERY.leafCanopy
    render(<BrandImage imageKey="leafCanopy" width={maxRenderedWidth} />)

    // next/image rewrites the src through its optimiser, so the original path is a substring.
    expect(screen.getByAltText(alt)).toHaveAttribute(
      'src',
      expect.stringContaining(encodeURIComponent(src)),
    )
  })

  test('lazy loads by default, and eagerly when asked', () => {
    const { alt } = BRAND_IMAGERY.handsSeedling
    const { unmount } = render(<BrandImage imageKey="handsSeedling" width={140} />)

    expect(screen.getByAltText(alt)).toHaveAttribute('loading', 'lazy')
    unmount()

    render(<BrandImage imageKey="handsSeedling" width={140} loading="eager" />)

    expect(screen.getByAltText(alt)).toHaveAttribute('loading', 'eager')
  })

  test('refuses a width the source file cannot support', () => {
    /*
     * Criterion 16. The deck's photographs are small. Rather than trusting everyone who
     * reaches for one to check the manifest, the component refuses.
     */
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() =>
      render(
        <BrandImage
          imageKey="handsSeedling"
          width={BRAND_IMAGERY.handsSeedling.maxRenderedWidth + 1}
        />,
      ),
    ).toThrow(/handsSeedling/)

    consoleError.mockRestore()
  })

  test('accepts the ceiling itself', () => {
    const { maxRenderedWidth, alt } = BRAND_IMAGERY.fieldSunrise

    expect(() =>
      render(<BrandImage imageKey="fieldSunrise" width={maxRenderedWidth} />),
    ).not.toThrow()
    expect(screen.getByAltText(alt)).toBeInTheDocument()
  })
})

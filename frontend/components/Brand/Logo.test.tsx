import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { BRAND_LOGOS, type BrandLogoVariant } from '@/lib/brand'
import { Logo } from './Logo'

/* design/features/public-landing-and-auth-routing.md section 6.2 and criterion 1. */

const variants = Object.keys(BRAND_LOGOS) as BrandLogoVariant[]

describe('Logo', () => {
  test.each(variants)('renders %s with the alt text supplied by the brand', (variant) => {
    render(<Logo variant={variant} width={120} />)

    expect(screen.getByAltText(BRAND_LOGOS[variant].alt)).toBeInTheDocument()
  })

  test('renders the artwork for the requested variant', () => {
    render(<Logo variant="onForestGreen" width={120} />)

    // next/image rewrites the src through its optimiser, so the original path is a substring.
    expect(screen.getByAltText(BRAND_LOGOS.onForestGreen.alt)).toHaveAttribute(
      'src',
      expect.stringContaining(encodeURIComponent(BRAND_LOGOS.onForestGreen.src)),
    )
  })

  test('keeps the artwork aspect ratio when given a width', () => {
    render(<Logo variant="mark" width={200} />)

    const { width, height } = BRAND_LOGOS.mark
    const image = screen.getByAltText(BRAND_LOGOS.mark.alt)

    expect(image).toHaveAttribute('width', '200')
    expect(image).toHaveAttribute('height', String(Math.round((200 * height) / width)))
  })

  test('lazy loads by default', () => {
    render(<Logo variant="onCream" width={120} />)

    expect(screen.getByAltText(BRAND_LOGOS.onCream.alt)).toHaveAttribute('loading', 'lazy')
  })

  test('loads eagerly when asked, for above-the-fold use', () => {
    render(<Logo variant="onCream" width={120} loading="eager" />)

    expect(screen.getByAltText(BRAND_LOGOS.onCream.alt)).toHaveAttribute('loading', 'eager')
  })
})

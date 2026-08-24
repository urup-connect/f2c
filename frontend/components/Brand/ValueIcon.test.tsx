import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { VALUE_ICONS, type BrandValueIconKey } from '@/lib/brand-icons'
import { ValueIcon } from './ValueIcon'

/* design/features/landing-page-engagement.md criteria 10 and 11, section 6.3. */

const keys = Object.keys(VALUE_ICONS) as BrandValueIconKey[]

describe('ValueIcon', () => {
  test.each(keys)('draws the %s artwork in its own coordinate space', (iconKey) => {
    const { container } = render(<ValueIcon iconKey={iconKey} size={40} />)
    const svg = container.querySelector('svg')

    expect(svg).toHaveAttribute('viewBox', VALUE_ICONS[iconKey].viewBox)
    expect(container.querySelector('path')).toHaveAttribute('d', VALUE_ICONS[iconKey].path)
  })

  test.each(keys)('%s is hidden from assistive technology', (iconKey) => {
    /*
     * Criterion 11. The label beside the icon carries the meaning, so announcing the icon
     * would only repeat it.
     */
    const { container } = render(<ValueIcon iconKey={iconKey} size={40} />)

    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  test('renders at the requested size', () => {
    const { container } = render(<ValueIcon iconKey="community" size={48} />)
    const svg = container.querySelector('svg')

    expect(svg).toHaveAttribute('width', '48')
    expect(svg).toHaveAttribute('height', '48')
  })

  test('takes its colour from the text colour around it', () => {
    // Not a hardcoded fill, so the same artwork works on cream and on green.
    const { container } = render(<ValueIcon iconKey="trust" size={40} />)

    expect(container.querySelector('path')).toHaveAttribute('fill', 'currentColor')
  })

  test('accepts a class name, so the caller places it', () => {
    const { container } = render(<ValueIcon iconKey="quality" size={40} className="shrink-0" />)

    expect(container.querySelector('svg')).toHaveClass('shrink-0')
  })
})

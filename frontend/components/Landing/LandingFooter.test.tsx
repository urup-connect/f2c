import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { FOOTER } from '@/lib/landing-content'
import { LandingFooter } from './LandingFooter'

/* design/features/landing-page-engagement.md criterion 5, section 6.5. */

describe('LandingFooter', () => {
  test('is the page footer landmark', () => {
    render(<LandingFooter />)

    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
  })

  test('carries the rights line', () => {
    render(<LandingFooter />)

    expect(screen.getByText(FOOTER.rights)).toBeInTheDocument()
  })

  test('shows the brand mark', () => {
    render(<LandingFooter />)

    expect(screen.getByAltText('Cultivators Collective')).toBeInTheDocument()
  })

  test('links nowhere, there being no privacy or terms page to link to yet', () => {
    // Added when the auth forms start collecting something. Follow-up in section 11.
    render(<LandingFooter />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

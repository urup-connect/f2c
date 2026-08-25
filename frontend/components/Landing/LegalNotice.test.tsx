import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { LEGAL } from '@/lib/landing-content'
import { LegalNotice } from './LegalNotice'

/* design/features/landing.md section 4. */

describe('LegalNotice', () => {
  test('is headed at level two, below the page heading', () => {
    render(<LegalNotice />)

    expect(screen.getByRole('heading', { level: 2, name: LEGAL.heading })).toBeInTheDocument()
  })

  test('marks the points up as a list', () => {
    render(<LegalNotice />)

    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      ...LEGAL.points,
    ])
  })

  test('is a landmark named by its own heading', () => {
    render(<LegalNotice />)

    expect(screen.getByRole('region', { name: LEGAL.heading })).toBeInTheDocument()
  })
})

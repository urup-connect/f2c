import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { JOIN } from '@/lib/landing-content'
import { JoinBand } from './JoinBand'

/* design/features/landing-page-engagement.md criteria 6 and 13. */

describe('JoinBand', () => {
  test('is headed at level two, below the page heading', () => {
    render(<JoinBand />)

    expect(screen.getByRole('heading', { level: 2, name: JOIN.heading })).toBeInTheDocument()
  })

  test('repeats both ways in, for a reader who has scrolled the page', () => {
    render(<JoinBand />)

    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveAttribute('href', '/join')
    expect(screen.getByRole('link', { name: 'Log In' })).toHaveAttribute('href', '/login')
  })

  test('says plainly that the club is not yet open', () => {
    /*
     * Criterion 13. Sign-up cannot work until the access mechanism is decided, so a reader
     * who follows the button is told what to expect before they do.
     * See design/features/landing-page-engagement.md risk 5.
     */
    render(<JoinBand />)

    expect(screen.getByText(JOIN.note)).toBeInTheDocument()
  })

  test('is a landmark named by its own heading', () => {
    render(<JoinBand />)

    expect(screen.getByRole('region', { name: JOIN.heading })).toBeInTheDocument()
  })
})

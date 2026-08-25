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

  test('carries no caveat about the club being closed', () => {
    /*
     * The band used to say the club was not yet open. The page now describes the members area
     * in the present tense and the two cannot both stand, so the line went with the client's
     * decision. See design/features/landing.md risk 1.
     */
    render(<JoinBand />)

    expect(screen.queryByText(/not yet open/i)).not.toBeInTheDocument()
  })

  test('is a landmark named by its own heading', () => {
    render(<JoinBand />)

    expect(screen.getByRole('region', { name: JOIN.heading })).toBeInTheDocument()
  })
})

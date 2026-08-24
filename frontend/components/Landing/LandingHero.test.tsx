import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, test } from 'vitest'
import { HERO } from '@/lib/landing-content'
import { LandingHero } from './LandingHero'

/*
 * design/features/public-landing-and-auth-routing.md criteria 1, 2 and 3, carried forward as
 * design/features/landing-page-engagement.md criteria 1, 2, 3, 7 and 8.
 */

describe('LandingHero', () => {
  test('names the club in a single level-one heading', () => {
    render(<LandingHero />)

    const headings = screen.getAllByRole('heading', { level: 1 })

    expect(headings).toHaveLength(1)
    expect(headings[0]).toHaveTextContent(/cultivators collective/i)
  })

  test('carries the tagline inside that same heading', () => {
    /*
     * Criterion 7. The tagline is the line that carries the page visually, but the club's name
     * has to stay inside the heading as text — otherwise the name is left to the badge alone.
     */
    render(<LandingHero />)

    const heading = screen.getByRole('heading', { level: 1 })

    expect(heading).toHaveAccessibleName(/Cultivators Collective/)
    expect(heading).toHaveAccessibleName(/Growing together\. Delivering excellence\./)
  })

  test('states the club proposition in body copy', () => {
    render(<LandingHero />)

    expect(screen.getByText(HERO.proposition)).toBeInTheDocument()
  })

  test('shows the brand logo', () => {
    render(<LandingHero />)

    expect(screen.getByAltText('Cultivators Collective')).toBeInTheDocument()
  })

  test('loads the logo eagerly, being the first thing above the fold', () => {
    render(<LandingHero />)

    expect(screen.getByAltText('Cultivators Collective')).toHaveAttribute('loading', 'eager')
  })

  test('offers a way to sign up and a way to log in', () => {
    render(<LandingHero />)

    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveAttribute('href', '/join')
    expect(screen.getByRole('link', { name: 'Log In' })).toHaveAttribute('href', '/login')
  })

  test('puts sign up before log in, joining being what the page is for', () => {
    // Criterion 8.
    render(<LandingHero />)

    expect(screen.getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Sign Up',
      'Log In',
    ])
  })

  test('reaches both calls to action by keyboard alone', async () => {
    const user = userEvent.setup()
    render(<LandingHero />)

    await user.tab()
    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveFocus()

    await user.tab()
    expect(screen.getByRole('link', { name: 'Log In' })).toHaveFocus()
  })

  test('sets both controls up for the green ground they sit on', () => {
    render(<LandingHero />)

    // A forest-green focus ring on the forest-green hero would be invisible.
    for (const name of ['Sign Up', 'Log In']) {
      expect(screen.getByRole('link', { name }).className).toContain(
        'focus-visible:outline-cream-warm',
      )
    }
  })

  test('carries no starter-template content', () => {
    const { container } = render(<LandingHero />)

    expect(container.textContent).not.toMatch(/page\.tsx|create next app|vercel|next\.js/i)
    expect(container.querySelector('a[href*="vercel.com"]')).toBeNull()
    expect(container.querySelector('a[href*="nextjs.org"]')).toBeNull()
  })
})

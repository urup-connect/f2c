import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { brandFilmSource } from '@/lib/brand-film'
import {
  ALL_COPY,
  FILM,
  HERO,
  JOIN,
  LEGAL,
  STORY,
  STRAPLINE_SEGMENTS,
  VALUES,
  WHY_JOIN,
} from '@/lib/landing-content'
import { SITE_CONFIG } from '@/lib/site'
import Home, { metadata } from './page'

/*
 * design/features/public-landing-and-auth-routing.md criteria 1, 2 and 3, carried forward as
 * design/features/landing-page-engagement.md criteria 1 to 6 and 14.
 */

describe('the landing page', () => {
  test('names the club in a single level-one heading', () => {
    render(<Home />)

    const headings = screen.getAllByRole('heading', { level: 1 })

    expect(headings).toHaveLength(1)
    expect(headings[0]).toHaveTextContent(/cultivators collective/i)
  })

  test('offers a way to sign up and a way to log in', () => {
    render(<Home />)

    const signUp = screen.getAllByRole('link', { name: 'Sign Up' })
    const logIn = screen.getAllByRole('link', { name: 'Log In' })

    // Twice each: once in the hero, once in the join band a reader reaches by scrolling.
    expect(signUp).toHaveLength(2)
    expect(logIn).toHaveLength(2)
    for (const link of signUp) expect(link).toHaveAttribute('href', '/join')
    for (const link of logIn) expect(link).toHaveAttribute('href', '/login')
  })

  test('leads with sign up, before anything else on the page', () => {
    // Criterion 8.
    render(<Home />)

    expect(screen.getAllByRole('link').slice(0, 2).map((link) => link.textContent)).toEqual([
      'Sign Up',
      'Log In',
    ])
  })

  test('permits indexing, being the one route in the product that may be indexed', () => {
    expect(metadata.robots).toEqual({ index: true, follow: true })
  })

  test('runs hero, ribbon, film, why join, values, story, legal, join and footer in that order', () => {
    // Criterion 5, extended by the film and the two sections the client supplied.
    const { container } = render(<Home />)
    const text = container.textContent ?? ''

    const positions = [
      HERO.tagline,
      STRAPLINE_SEGMENTS[0],
      FILM.heading,
      WHY_JOIN.heading,
      VALUES.heading,
      STORY.heading,
      LEGAL.heading,
      JOIN.heading,
      'All rights reserved',
    ].map((marker) => text.indexOf(marker))

    for (const position of positions) expect(position).toBeGreaterThan(-1)
    expect(positions).toEqual([...positions].sort((a, b) => a - b))
  })

  test('descends through heading levels without skipping one', () => {
    // Criterion 6.
    const { container } = render(<Home />)
    const levels = [...container.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((heading) =>
      Number(heading.tagName[1]),
    )

    expect(levels[0]).toBe(1)
    for (const [index, level] of levels.entries()) {
      if (index === 0) continue
      expect(level - levels[index - 1]).toBeLessThanOrEqual(1)
    }
  })

  test('names each section as a landmark, so a reader can jump between them', () => {
    render(<Home />)

    for (const name of [
      FILM.heading,
      WHY_JOIN.heading,
      VALUES.heading,
      STORY.heading,
      LEGAL.heading,
      JOIN.heading,
    ]) {
      expect(screen.getByRole('region', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('contentinfo')).toBeInTheDocument()
  })

  test('shows every word the content module declares', () => {
    // Criterion 14 is asserted against the copy module; this is what ties it to the page.
    const { container } = render(<Home />)
    const text = container.textContent ?? ''

    for (const line of ALL_COPY) expect(text).toContain(line)
  })

  test('serves no photograph of an identifiable person', () => {
    // Criterion 18.
    const { container } = render(<Home />)
    const sources = [...container.querySelectorAll('img')].map((image) => image.src)

    for (const source of sources) {
      expect(source).not.toMatch(/cultivator-portrait|face|person|portrait/i)
    }
  })

  test('serves the club film from the deployment CDN', () => {
    // The first thing in the product to read CDN_BASE_URL. See lib/site.ts.
    const { container } = render(<Home />)
    const video = container.querySelector('video')

    expect(video).not.toBeNull()
    expect(video?.getAttribute('src')).toBe(brandFilmSource(SITE_CONFIG))
  })

  test('carries no starter-template content', () => {
    const { container } = render(<Home />)

    expect(container.textContent).not.toMatch(/page\.tsx|create next app|vercel|next\.js/i)
    expect(container.querySelector('a[href*="vercel.com"]')).toBeNull()
    expect(container.querySelector('a[href*="nextjs.org"]')).toBeNull()
  })

  test('moves nothing on its own, so there is nothing a reader has to pause', () => {
    // WCAG 2.2.2. See design/features/landing-page-engagement.md section 6.6.
    const { container } = render(<Home />)

    expect(container.innerHTML).not.toMatch(/animate-|animation:|marquee/)
  })
})

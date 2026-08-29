import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { AuthCard } from './AuthCard'

/*
 * design/features/member-details-at-sign-up.md criterion 51, and section 5.
 *
 * What this card is for is its width, and width does not exist under jsdom: the unit environment
 * applies no stylesheet, so a test here could only assert the class names that produce the layout,
 * which tests the implementation rather than the result. The measurements are in
 * tests/e2e/member-details.spec.ts, against real viewports. What is worth covering here is that
 * the card renders what it is given and stays out of the way of the page's own landmarks.
 */

describe('AuthCard', () => {
  test('renders what the page puts inside it', () => {
    render(
      <AuthCard>
        <h1>Log In</h1>
      </AuthCard>,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Log In' })).toBeInTheDocument()
  })

  test('renders the same content at either width', () => {
    render(
      <AuthCard width="wide">
        <h1>Your details</h1>
      </AuthCard>,
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Your details' })).toBeInTheDocument()
  })

  test('adds no landmark of its own, so the page keeps one main region', () => {
    // The layout owns <main>. A second landmark here would give a screen reader two to choose from.
    const { container } = render(
      <AuthCard>
        <p>Members will sign in here once the club opens.</p>
      </AuthCard>,
    )

    expect(container.querySelector('main')).toBeNull()
    expect(screen.queryByRole('main')).not.toBeInTheDocument()
  })

  test('is a plain container, not a control', () => {
    render(
      <AuthCard>
        <p>Anything at all.</p>
      </AuthCard>,
    )

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

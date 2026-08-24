import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, test } from 'vitest'
import { ButtonLink } from './ButtonLink'

/* design/features/public-landing-and-auth-routing.md section 6.2 and criterion 3. */

describe('ButtonLink', () => {
  test('renders a link carrying its accessible name and destination', () => {
    render(<ButtonLink href="/signup">Sign Up</ButtonLink>)

    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveAttribute('href', '/signup')
  })

  test('is reachable by keyboard', async () => {
    const user = userEvent.setup()
    render(<ButtonLink href="/login">Log In</ButtonLink>)

    await user.tab()

    expect(screen.getByRole('link', { name: 'Log In' })).toHaveFocus()
  })

  test('shows a visible focus ring, so keyboard users can see where they are', () => {
    render(<ButtonLink href="/login">Log In</ButtonLink>)

    expect(screen.getByRole('link', { name: 'Log In' }).className).toMatch(/focus-visible:/)
  })

  test('is a link rather than a button, because it navigates', () => {
    render(<ButtonLink href="/login">Log In</ButtonLink>)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  test('renders on the primary tone by default', () => {
    render(<ButtonLink href="/signup">Sign Up</ButtonLink>)

    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveClass('bg-primary')
  })

  test('renders the secondary tone when asked', () => {
    render(
      <ButtonLink href="/login" tone="secondary">
        Log In
      </ButtonLink>,
    )

    const link = screen.getByRole('link', { name: 'Log In' })

    expect(link).not.toHaveClass('bg-primary')
    expect(link).toHaveClass('border-primary')
  })
})

/* design/features/landing-page-engagement.md section 6.3. */

describe('ButtonLink on a green ground', () => {
  test('sits on the cream ground by default, as it always has', () => {
    render(<ButtonLink href="/signup">Sign Up</ButtonLink>)

    expect(screen.getByRole('link', { name: 'Sign Up' })).toHaveClass('bg-primary')
  })

  test('reverses the primary control out of the green', () => {
    render(
      <ButtonLink href="/signup" ground="green">
        Sign Up
      </ButtonLink>,
    )

    const link = screen.getByRole('link', { name: 'Sign Up' })

    expect(link).toHaveClass('bg-cream-warm')
    expect(link).toHaveClass('text-forest-green')
  })

  test('outlines the secondary control in cream', () => {
    render(
      <ButtonLink href="/login" ground="green" tone="secondary">
        Log In
      </ButtonLink>,
    )

    const link = screen.getByRole('link', { name: 'Log In' })

    expect(link).not.toHaveClass('bg-cream-warm')
    expect(link).toHaveClass('border-cream-warm')
    expect(link).toHaveClass('text-cream-warm')
  })

  test.each(['primary', 'secondary'] as const)(
    'moves the %s focus ring to a colour visible against green',
    (tone) => {
      /*
       * A forest-green focus ring on a forest-green ground is invisible, which is why the
       * ground is a prop rather than a colour override at the call site.
       */
      render(
        <ButtonLink href="/login" ground="green" tone={tone}>
          Log In
        </ButtonLink>,
      )

      const { className } = screen.getByRole('link', { name: 'Log In' })

      expect(className).toContain('focus-visible:outline-cream-warm')
      expect(className).not.toContain('focus-visible:outline-forest-green')
    },
  )

  test.each(['primary', 'secondary'] as const)(
    'keeps the %s focus ring green on the cream ground',
    (tone) => {
      render(
        <ButtonLink href="/login" tone={tone}>
          Log In
        </ButtonLink>,
      )

      expect(screen.getByRole('link', { name: 'Log In' }).className).toContain(
        'focus-visible:outline-forest-green',
      )
    },
  )
})

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { SignOutButton } from './SignOutButton'
import { CLUB_SHELL } from '@/lib/club-content'

const push = vi.fn()
const refresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh }),
}))

const logout = vi.hoisted(() => vi.fn())

vi.mock('@/lib/api', () => ({ logout }))

beforeEach(() => {
  logout.mockResolvedValue({ detail: 'Logged out.' })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('SignOutButton', () => {
  test('offers a way out', () => {
    render(<SignOutButton />)

    expect(screen.getByRole('button', { name: CLUB_SHELL.signOut })).toBeInTheDocument()
  })

  test('ends the session', async () => {
    render(<SignOutButton />)

    await userEvent.click(screen.getByRole('button', { name: CLUB_SHELL.signOut }))

    await waitFor(() => expect(logout).toHaveBeenCalledOnce())
  })

  test('discards the rendered session before navigating', async () => {
    // Every club screen is a Server Component that read the session when it rendered.
    // Without the refresh, the router serves one of those from its cache after the
    // cookie is gone.
    render(<SignOutButton />)

    await userEvent.click(screen.getByRole('button', { name: CLUB_SHELL.signOut }))

    await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
    expect(push).toHaveBeenCalledWith('/')
  })

  test('leaves anyway when the API cannot be reached', async () => {
    // They asked to leave. The next screen asks Django who they are.
    logout.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<SignOutButton />)

    await userEvent.click(screen.getByRole('button', { name: CLUB_SHELL.signOut }))

    await waitFor(() => expect(push).toHaveBeenCalledWith('/'))
  })

  test('shows no error message when it fails, because there is nothing to do about it', async () => {
    logout.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<SignOutButton />)

    await userEvent.click(screen.getByRole('button', { name: CLUB_SHELL.signOut }))

    await waitFor(() => expect(push).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('cannot be pressed twice', async () => {
    render(<SignOutButton />)

    const button = screen.getByRole('button', { name: CLUB_SHELL.signOut })
    await userEvent.click(button)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: CLUB_SHELL.signingOut })).toBeDisabled(),
    )
  })
})

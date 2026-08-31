import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { BLOCKED_COPY } from '@/lib/blocked-content'
import type { User } from '@/lib/api'

/*
 * The blocked-membership screen, and the two things about it that are not obvious from reading it:
 * it derives its own reason from the session rather than trusting the URL, and it forwards anybody
 * whose situation belongs on a different screen.
 */

const redirect = vi.fn((path: string) => {
  // Next's `redirect` throws to unwind the render. Mimicking that is what lets a test assert the
  // page stopped rather than carried on and rendered a notice for a reason it had rejected.
  throw new Error(`REDIRECT:${path}`)
})

const requireSession = vi.fn<() => Promise<User>>()

vi.mock('next/navigation', () => ({ redirect: (path: string) => redirect(path) }))
vi.mock('@/lib/club-session', () => ({ requireSession: () => requireSession() }))

const account = (over: Partial<User> = {}): User =>
  ({
    membership_status: 'suspended',
    role: 'member',
    permissions: [],
    ...over,
  }) as User

const renderPage = async () => {
  const { default: Blocked } = await import('./page')
  render(await Blocked())
}

describe('the blocked screen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('tells a suspended member the club has placed a hold, and offers the address', async () => {
    requireSession.mockResolvedValue(account({ membership_status: 'suspended' }))

    await renderPage()

    expect(screen.getByRole('heading', { name: BLOCKED_COPY.blocked.heading })).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: BLOCKED_COPY.blocked.contact as string }),
    ).toHaveAttribute('href', expect.stringContaining('mailto:'))
  })

  test('tells a member awaiting verification to wait, and offers nobody to chase', async () => {
    requireSession.mockResolvedValue(account({ membership_status: 'pending' }))

    await renderPage()

    expect(
      screen.getByRole('heading', { name: BLOCKED_COPY['awaiting-verification'].heading }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /email the club/i })).not.toBeInTheDocument()
  })

  test('does not trust a URL for the reason', async () => {
    /*
     * **The reason a query parameter was rejected.** The page takes no input at all — the wording
     * follows the session, so a visitor cannot choose which situation the screen describes by
     * typing one. A suspended member gets the suspension wording whatever they append.
     */
    requireSession.mockResolvedValue(account({ membership_status: 'suspended' }))

    await renderPage()

    expect(screen.getByRole('heading', { name: BLOCKED_COPY.blocked.heading })).toBeInTheDocument()
  })

  test('sends a member who owes money to the payment screen instead', async () => {
    // Their situation has a screen that can help them, and this one cannot.
    requireSession.mockResolvedValue(account({ membership_status: 'pending_payment' }))

    await expect(renderPage()).rejects.toThrow('REDIRECT:/pay')
  })

  test('sends an account with no club membership to the front door', async () => {
    requireSession.mockResolvedValue(account({ membership_status: null }))

    await expect(renderPage()).rejects.toThrow('REDIRECT:/')
  })

  test('sends a reinstated member to their own home rather than a stale refusal', async () => {
    /*
     * The tab that sat open while an administrator lifted the hold. The gate is asked live on every
     * request, so this is the same answer the club layout would give a moment later.
     */
    requireSession.mockResolvedValue(account({ membership_status: 'active', role: 'member' }))

    await expect(renderPage()).rejects.toThrow('REDIRECT:/member')
  })
})

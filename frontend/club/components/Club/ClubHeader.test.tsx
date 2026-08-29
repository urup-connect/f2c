import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { ClubHeader } from './ClubHeader'
import { CLUB_SHELL } from '@/lib/club-content'
import type { ClubDestination } from '@/lib/club-navigation'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

vi.mock('@/lib/api', () => ({ logout: vi.fn() }))

const A_LINK: ClubDestination = {
  key: 'own-inventory',
  label: 'Your plants',
  description: 'Everything you own.',
  permission: 'platform.view_own_inventory',
  section: 'plants',
  state: 'ready',
  href: '/member/plants',
}

describe('ClubHeader', () => {
  test('shows who is signed in', () => {
    render(<ClubHeader displayName="greenfingers" homeHref="/member" navigable={[]} />)

    expect(screen.getByText('greenfingers')).toBeInTheDocument()
  })

  test('shows no name for an account that has none', () => {
    // An erased account keeps its row with every name cleared. It cannot sign in, but
    // the shape has to survive it: better nothing than an empty line.
    const { container } = render(
      <ClubHeader displayName={null} homeHref="/member" navigable={[]} />,
    )

    expect(container.querySelectorAll('p')).toHaveLength(0)
  })

  test('sends the badge to this account own home', () => {
    render(<ClubHeader displayName="greenfingers" homeHref="/cultivator" navigable={[]} />)

    expect(screen.getByRole('link', { name: CLUB_SHELL.homeLabel })).toHaveAttribute(
      'href',
      '/cultivator',
    )
  })

  test('offers a way out', () => {
    render(<ClubHeader displayName="greenfingers" homeHref="/member" navigable={[]} />)

    expect(screen.getByRole('button', { name: CLUB_SHELL.signOut })).toBeInTheDocument()
  })

  test('renders no navigation landmark while there is nowhere to go', () => {
    // An empty landmark invites a screen-reader user in for no reason. This test
    // changes on the day the first destination gains an href.
    render(<ClubHeader displayName="greenfingers" homeHref="/member" navigable={[]} />)

    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  test('renders the navigation once there is somewhere to go', () => {
    render(<ClubHeader displayName="greenfingers" homeHref="/member" navigable={[A_LINK]} />)

    const nav = screen.getByRole('navigation', { name: CLUB_SHELL.navLabel })

    expect(nav).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Your plants' })).toHaveAttribute(
      'href',
      '/member/plants',
    )
  })
})

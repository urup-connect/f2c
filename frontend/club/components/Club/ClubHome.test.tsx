import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { ClubHome } from './ClubHome'
import type { User } from '@/lib/api'
import { CLUB_HOMES_COPY, DETAILS_CARD, MEMBERSHIP_CARD } from '@/lib/club-content'

vi.mock('@simplewebauthn/browser', () => ({
  browserSupportsWebAuthn: () => false,
  startRegistration: vi.fn(),
}))

const base: User = {
  id: '2b0d3a2c-6e0f-4a3f-8f4b-9b6c1f0d1a11',
  email: 'thandi@example.co.za',
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  mobile: '+27821234567',
  display_name: 'greenfingers',
  date_of_birth: '1990-03-15',
  date_of_birth_verified_at: null,
  status: 'active',
  // The card reads the membership's standing, not the account's — C27.
  membership_status: 'active',
  role: 'member',
  permissions: ['platform.purchase_plants', 'platform.manage_own_profile'],
  is_staff: false,
}

const renderHome = (overrides: Partial<User> = {}, role: 'member' | 'cultivator' | 'admin' = 'member') =>
  render(
    <ClubHome
      role={role}
      user={{ ...base, ...overrides }}
      passkeys={[]}
      passkeysUnavailable={false}
    />,
  )

describe('the greeting', () => {
  test('names the member', () => {
    renderHome()

    expect(
      screen.getByRole('heading', { level: 1, name: /Welcome back, greenfingers/ }),
    ).toBeInTheDocument()
  })

  test('degrades to a sentence when the account has no name at all', () => {
    // An erased account. It cannot sign in; the greeting must still not read
    // "Welcome back, ".
    renderHome({ display_name: '' })

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/^Welcome back$/)
  })
})

describe('each role gets its own home', () => {
  test('a member is told what their area is for', () => {
    renderHome({}, 'member')

    expect(screen.getByText(CLUB_HOMES_COPY.member.title)).toBeInTheDocument()
    expect(screen.getByText(CLUB_HOMES_COPY.member.standfirst)).toBeInTheDocument()
  })

  test('a cultivator is told something different', () => {
    renderHome({ role: 'cultivator' }, 'cultivator')

    expect(screen.getByText(CLUB_HOMES_COPY.cultivator.title)).toBeInTheDocument()
    expect(screen.queryByText(CLUB_HOMES_COPY.member.standfirst)).not.toBeInTheDocument()
  })

  test('an administrator is told something different again', () => {
    renderHome({ role: 'admin' }, 'admin')

    expect(screen.getByText(CLUB_HOMES_COPY.admin.title)).toBeInTheDocument()
    expect(screen.getByText(CLUB_HOMES_COPY.admin.standfirst)).toBeInTheDocument()
  })
})

describe('the cards', () => {
  test('shows what the club holds', () => {
    renderHome()

    expect(screen.getByRole('region', { name: DETAILS_CARD.heading })).toBeInTheDocument()
    expect(screen.getByText('Thandi Mokoena')).toBeInTheDocument()
    expect(screen.getByText('greenfingers')).toBeInTheDocument()
  })

  test('does not show the date of birth, and points at where it lives', () => {
    renderHome()

    // The card is now four rows and a link. The date is on /profile, beside the identity number it
    // was taken from.
    expect(screen.queryByText('15 March 1990')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: DETAILS_CARD.editLabel })).toHaveAttribute(
      'href',
      '/profile',
    )
  })

  test('shows how the account stands', () => {
    renderHome()

    expect(screen.getByRole('region', { name: MEMBERSHIP_CARD.heading })).toBeInTheDocument()
    expect(screen.getByText(MEMBERSHIP_CARD.statusLabels.active)).toBeInTheDocument()
  })

  test('shows how they sign in', () => {
    renderHome()

    expect(screen.getByRole('region', { name: /How you sign in/ })).toBeInTheDocument()
  })

  test('never puts an identity number on screen', () => {
    const { container } = renderHome()

    expect(container.textContent).not.toMatch(/\b\d{13}\b/)
  })
})

describe('what is offered', () => {
  test('is drawn from the permissions on the session, not from the page', () => {
    // The same component renders all three homes. An administrator's screen is this
    // one drawing a different catalogue.
    renderHome({ permissions: ['platform.manage_cultivators'] }, 'admin')

    expect(screen.getByText('Cultivators')).toBeInTheDocument()
    expect(screen.queryByText('Buy a plant')).not.toBeInTheDocument()
  })

  test('offers a member what a member holds', () => {
    renderHome()

    expect(screen.getByText('Buy a plant')).toBeInTheDocument()
    expect(screen.getByText('Your details')).toBeInTheDocument()
  })
})

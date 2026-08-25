import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { PROFILE_COPY } from '@/lib/club-content'
import { UNREADABLE_ID_NUMBER } from '@/lib/profile-display'
import type { Profile } from '@/lib/profile-api'
import { IdentityCard } from './IdentityCard'

const PROFILE: Profile = {
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  email: 'thandi@example.co.za',
  mobile: '+27821234567',
  display_name: 'greenfingers',
  date_of_birth: '1980-01-01',
  date_of_birth_verified_at: '2026-08-12T09:30:00Z',
  has_id_number: true,
  id_number_masked: '*********9087',
  has_avatar: false,
  avatar_url: null,
  role: 'member',
  status: 'active',
}

describe('the identity card', () => {
  test('is a named region, so it appears in a landmark list', () => {
    render(<IdentityCard profile={PROFILE} />)

    expect(
      screen.getByRole('region', { name: PROFILE_COPY.identity.heading }),
    ).toBeInTheDocument()
  })

  test('shows the date and the masked number', () => {
    render(<IdentityCard profile={PROFILE} />)

    expect(screen.getByText('1 January 1980')).toBeInTheDocument()
    expect(screen.getByText('*********9087')).toBeInTheDocument()
  })

  test('has no input, anywhere', () => {
    /*
     * The reason these two fields get a card of their own rather than disabled inputs in the form
     * above. A disabled input still looks like an input, so a member spends a moment trying to
     * click into it before concluding it is broken.
     */
    const { container } = render(<IdentityCard profile={PROFILE} />)

    expect(container.querySelector('input')).toBeNull()
    expect(container.querySelector('textarea')).toBeNull()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  test('says why neither can be changed here, and who to ask', () => {
    // A read-only field with no explanation is the commonest way a screen invites a support
    // request.
    render(<IdentityCard profile={PROFILE} />)

    expect(screen.getByText(PROFILE_COPY.identity.standfirst)).toBeInTheDocument()
  })

  test('never renders a whole identity number', () => {
    const { container } = render(<IdentityCard profile={PROFILE} />)

    expect(container.textContent).not.toMatch(/\d{13}/)
  })

  test('says a field is absent rather than drawing an empty line', () => {
    render(
      <IdentityCard
        profile={{
          ...PROFILE,
          date_of_birth: null,
          date_of_birth_verified_at: null,
          has_id_number: false,
          id_number_masked: '',
        }}
      />,
    )

    expect(screen.getAllByText(PROFILE_COPY.identity.blank)).toHaveLength(2)
  })

  test('distinguishes a document it cannot read from one it does not hold', () => {
    render(
      <IdentityCard profile={{ ...PROFILE, id_number_masked: UNREADABLE_ID_NUMBER }} />,
    )

    expect(screen.getByText(PROFILE_COPY.identity.unreadable)).toBeInTheDocument()
    // And does not print the sentinel at a member, which would be a word from a log file on a
    // screen.
    expect(screen.queryByText(UNREADABLE_ID_NUMBER)).not.toBeInTheDocument()
  })

  test('reports an unchecked date as unchecked', () => {
    render(<IdentityCard profile={{ ...PROFILE, date_of_birth_verified_at: null }} />)

    expect(screen.getByText(PROFILE_COPY.identity.unverified)).toBeInTheDocument()
  })

  test('pairs each label with its value for a screen reader', () => {
    // A description list, so the pair is announced. A run of paragraphs would lose the pairing.
    const { container } = render(<IdentityCard profile={PROFILE} />)

    expect(container.querySelectorAll('dt')).toHaveLength(2)
    expect(container.querySelectorAll('dd')).toHaveLength(2)
  })
})

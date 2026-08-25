import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { PROFILE_COPY } from '@/lib/club-content'
import type { Profile } from '@/lib/profile-api'
import { ProfileScreen } from './ProfileScreen'

/*
 * The screen, and the one thing it exists to own: which record is current.
 *
 * Everything else is tested where it lives. What can only be tested here is the property that made
 * this a component rather than three cards on a page — **a write in one card is seen by the
 * others**. Without one owner, saving a surname and then uploading a photograph would send the
 * pre-rename record back to the server, because the avatar card would still be holding the profile
 * it was mounted with. That bug is invisible in either card's own tests.
 */

const { saveProfile, postAvatar, deleteAvatar } = vi.hoisted(() => ({
  saveProfile: vi.fn(),
  postAvatar: vi.fn(),
  deleteAvatar: vi.fn(),
}))

vi.mock('@/lib/profile-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/profile-api')>()),
  saveProfile,
  postAvatar,
  deleteAvatar,
}))

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

beforeEach(() => {
  saveProfile.mockReset()
  postAvatar.mockReset()
  deleteAvatar.mockReset()
})

describe('the screen', () => {
  test('draws the whole record in the first paint, fetching nothing', () => {
    // A member should never see their own profile blank for a frame; that reads as though the club
    // had lost the record.
    render(<ProfileScreen initial={PROFILE} />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(PROFILE_COPY.heading)
    expect(screen.getByLabelText(PROFILE_COPY.details.firstNameLabel)).toHaveValue('Thandi')
    expect(screen.getByText('*********9087')).toBeInTheDocument()
    expect(screen.getByText('1 January 1980')).toBeInTheDocument()
  })

  test('shows all three cards, in the order a member needs them', () => {
    render(<ProfileScreen initial={PROFILE} />)

    const headings = screen
      .getAllByRole('heading', { level: 2 })
      .map((heading) => heading.textContent)

    expect(headings).toEqual([
      PROFILE_COPY.details.heading,
      PROFILE_COPY.photograph.heading,
      PROFILE_COPY.identity.heading,
    ])
  })

  test('never renders a whole identity number', () => {
    const { container } = render(<ProfileScreen initial={PROFILE} />)

    expect(container.textContent).not.toMatch(/\d{13}/)
  })
})

describe('the record every card is looking at', () => {
  test('a saved name reaches the photograph card', async () => {
    /*
     * The reason this component exists. `initials` is drawn from the names, so a rename that did not
     * propagate would leave the old initials beside the new surname -- the visible half of a bug
     * whose invisible half is the stale record being sent to the server on the next write.
     */
    const user = userEvent.setup()
    saveProfile.mockResolvedValue({
      status: 'saved',
      profile: { ...PROFILE, first_name: 'Ayanda', last_name: 'Zulu' },
    })
    render(<ProfileScreen initial={PROFILE} />)

    expect(screen.getByText('TM')).toBeInTheDocument()

    const field = screen.getByLabelText(PROFILE_COPY.details.firstNameLabel)
    await user.clear(field)
    await user.type(field, 'Ayanda')
    await user.tab()
    await user.click(screen.getByRole('button', { name: PROFILE_COPY.details.save }))

    expect(await screen.findByText('AZ')).toBeInTheDocument()
  })

  test('a removed photograph reaches the card that offered to remove it', async () => {
    const user = userEvent.setup()
    deleteAvatar.mockResolvedValue({ ...PROFILE, has_avatar: false, avatar_url: null })
    render(
      <ProfileScreen
        initial={{ ...PROFILE, has_avatar: true, avatar_url: '/api/accounts/me/avatar?v=1' }}
      />,
    )

    await user.click(screen.getByRole('button', { name: PROFILE_COPY.photograph.remove }))

    // The button goes, because there is nothing left to remove, and the initials come back.
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: PROFILE_COPY.photograph.remove }),
      ).not.toBeInTheDocument(),
    )
    expect(screen.getByText(PROFILE_COPY.photograph.empty)).toBeInTheDocument()
  })

  test('a record that changes underneath still shows the identity fields it came with', async () => {
    // The identity card reads the same state, so a write that returned a different masked number --
    // it cannot today, but the card must not be holding its own copy -- would be seen here.
    const user = userEvent.setup()
    saveProfile.mockResolvedValue({
      status: 'saved',
      profile: { ...PROFILE, first_name: 'Ayanda', id_number_masked: '*********1234' },
    })
    render(<ProfileScreen initial={PROFILE} />)

    const field = screen.getByLabelText(PROFILE_COPY.details.firstNameLabel)
    await user.clear(field)
    await user.type(field, 'Ayanda')
    await user.tab()
    await user.click(screen.getByRole('button', { name: PROFILE_COPY.details.save }))

    expect(await screen.findByText('*********1234')).toBeInTheDocument()
  })
})

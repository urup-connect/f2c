import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import type { Profile } from '@/lib/profile-api'
import { PROFILE_COPY, PROFILE_REFUSAL_MESSAGES } from '@/lib/store-content'
import { DetailsForm } from './DetailsForm'

const api = vi.hoisted(() => ({ saveProfile: vi.fn() }))

vi.mock('@/lib/profile-api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/profile-api')>('@/lib/profile-api')
  return { ...actual, ...api }
})

const profile = (overrides: Partial<Profile> = {}): Profile => ({
  first_name: 'Thandiwe',
  last_name: 'Mokoena',
  nickname: '',
  email: 'thandiwe@example.co.za',
  mobile: '+27821234567',
  display_name: 'Thandiwe Mokoena',
  date_of_birth: null,
  date_of_birth_verified_at: null,
  has_id_number: false,
  id_number_masked: '',
  has_avatar: false,
  avatar_url: null,
  role: 'member',
  status: 'active',
  ...overrides,
})

const save = async () => {
  await userEvent.click(screen.getByRole('button', { name: PROFILE_COPY.save }))
}

beforeEach(() => {
  api.saveProfile.mockResolvedValue({ status: 'saved', profile: profile() })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('what the form holds', () => {
  test('draws the three editable fields from the record', () => {
    render(<DetailsForm initial={profile()} />)

    expect(screen.getByLabelText(PROFILE_COPY.firstNameLabel)).toHaveValue('Thandiwe')
    expect(screen.getByLabelText(PROFILE_COPY.lastNameLabel)).toHaveValue('Mokoena')
    expect(screen.getByLabelText(PROFILE_COPY.mobileLabel)).toHaveValue('+27821234567')
  })

  test('shows the email address without an input, and says why', () => {
    // A disabled input would look like an oversight. It is the sign-in identifier, and changing it is
    // a different act with different checks.
    render(<DetailsForm initial={profile()} />)

    expect(screen.queryByLabelText(PROFILE_COPY.emailLabel)).not.toBeInTheDocument()
    expect(screen.getByText('thandiwe@example.co.za')).toBeInTheDocument()
    expect(screen.getByText(PROFILE_COPY.emailNote)).toBeInTheDocument()
  })

  test('asks for nothing the store has no business holding', () => {
    // No identity number and no nickname: a produce customer is never asked for a document, and a
    // read-only field would invite somebody to fill one in.
    render(<DetailsForm initial={profile()} />)

    expect(screen.queryByLabelText(/identity/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/nickname/i)).not.toBeInTheDocument()
  })
})

describe('saving', () => {
  test('sends the normalised values, not what was typed', async () => {
    render(<DetailsForm initial={profile({ mobile: '' })} />)

    await userEvent.type(screen.getByLabelText(PROFILE_COPY.mobileLabel), '082 123 4567')
    await save()

    await waitFor(() =>
      expect(api.saveProfile).toHaveBeenCalledWith({
        first_name: 'Thandiwe',
        last_name: 'Mokoena',
        mobile: '+27821234567',
      }),
    )
  })

  test('accepts a cleared mobile number, which is an answer rather than an omission', async () => {
    render(<DetailsForm initial={profile()} />)

    await userEvent.clear(screen.getByLabelText(PROFILE_COPY.mobileLabel))
    await save()

    await waitFor(() =>
      expect(api.saveProfile).toHaveBeenCalledWith(
        expect.objectContaining({ mobile: '' }),
      ),
    )
  })

  test('says so when it worked', async () => {
    render(<DetailsForm initial={profile()} />)
    await save()

    expect(await screen.findByRole('status')).toHaveTextContent(PROFILE_COPY.saved)
  })
})

describe('refusals', () => {
  test('refuses a bad value before sending it, in our own wording', async () => {
    render(<DetailsForm initial={profile()} />)

    await userEvent.clear(screen.getByLabelText(PROFILE_COPY.firstNameLabel))
    await save()

    const field = screen.getByLabelText(PROFILE_COPY.firstNameLabel)

    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(field).toHaveAccessibleDescription(
      expect.stringContaining(PROFILE_REFUSAL_MESSAGES['name-missing']),
    )
    expect(api.saveProfile).not.toHaveBeenCalled()
  })

  test("renders the API's own per-field message when it refuses something we cannot check", async () => {
    api.saveProfile.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'Refused.', fields: { mobile: ['Already in use.'] } },
    })

    render(<DetailsForm initial={profile()} />)
    await save()

    await waitFor(() =>
      expect(screen.getByLabelText(PROFILE_COPY.mobileLabel)).toHaveAccessibleDescription(
        expect.stringContaining('Already in use.'),
      ),
    )
  })

  test('has its own sentence for a number that belongs to somebody else', async () => {
    // The value is a perfectly good number, so a message saying it is invalid would be wrong.
    api.saveProfile.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'Refused.', mobile_unavailable: true },
    })

    render(<DetailsForm initial={profile()} />)
    await save()

    expect(await screen.findByRole('alert')).toHaveTextContent(PROFILE_COPY.mobileUnavailable)
  })

  test('says the fault is ours when the save could not be made at all', async () => {
    api.saveProfile.mockResolvedValue({ status: 'failed', reason: 'Failed to fetch' })

    render(<DetailsForm initial={profile()} />)
    await save()

    expect(await screen.findByRole('alert')).toHaveTextContent(PROFILE_COPY.failed)
  })

  test('clears a previous refusal on the next attempt', async () => {
    render(<DetailsForm initial={profile()} />)

    await userEvent.clear(screen.getByLabelText(PROFILE_COPY.firstNameLabel))
    await save()

    await userEvent.type(screen.getByLabelText(PROFILE_COPY.firstNameLabel), 'Naledi')
    await save()

    await waitFor(() =>
      expect(screen.getByLabelText(PROFILE_COPY.firstNameLabel)).not.toHaveAttribute('aria-invalid'),
    )
  })
})

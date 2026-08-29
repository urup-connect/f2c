import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { PROFILE_COPY } from '@/lib/club-content'
import type { Profile } from '@/lib/profile-api'
import { ProfileDetailsForm } from './ProfileDetailsForm'

/*
 * The form a member changes their own details on.
 *
 * `saveProfile` is mocked. What is under test is what this component does with each of the three
 * outcomes it can get back -- which is three different screens -- rather than the fetch, which
 * `lib/profile-api.ts` owns and `apiFetch` already covers.
 *
 * The assertions cluster around two properties. **The save button does nothing while nothing has
 * changed**, because a button that saves an identical record reports success for having done
 * nothing. And **a refusal never leaves the record looking saved**, because the worst outcome here
 * is a member walking away believing an edit took.
 */

const { saveProfile } = vi.hoisted(() => ({ saveProfile: vi.fn() }))

vi.mock('@/lib/profile-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/profile-api')>()),
  saveProfile,
}))

const PROFILE: Profile = {
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  email: 'thandi@example.co.za',
  mobile: '+27821234567',
  display_name: 'greenfingers',
  date_of_birth: '1980-01-01',
  date_of_birth_verified_at: null,
  has_id_number: true,
  id_number_masked: '*********9087',
  has_avatar: false,
  avatar_url: null,
  role: 'member',
  status: 'active',
}

const copy = PROFILE_COPY.details

const renderForm = (onSaved = vi.fn()) => {
  render(<ProfileDetailsForm profile={PROFILE} onSaved={onSaved} />)
  return onSaved
}

const saveButton = () => screen.getByRole('button', { name: copy.save })

/** Replace a field's contents, then leave it — the moment this form reads a value. */
const retype = async (label: string, value: string) => {
  const user = userEvent.setup()
  const field = screen.getByLabelText(label)

  await user.clear(field)
  if (value) await user.type(field, value)
  await user.tab()
}

beforeEach(() => {
  saveProfile.mockReset()
  saveProfile.mockResolvedValue({ status: 'saved', profile: PROFILE })
})

describe('what the form shows', () => {
  test('offers the three fields a member may change', () => {
    renderForm()

    expect(screen.getByLabelText(copy.firstNameLabel)).toHaveValue('Thandi')
    expect(screen.getByLabelText(copy.lastNameLabel)).toHaveValue('Mokoena')
    expect(screen.getByLabelText(copy.mobileLabel)).toHaveValue('+27821234567')
  })

  test('shows the nickname and email address, and says who changes them', () => {
    /*
     * Shown rather than omitted: a member came here to check what the club holds, and leaving these
     * off would send them back to their home page for the other half of their own record.
     */
    renderForm()

    expect(screen.getByText('greenfingers')).toBeInTheDocument()
    expect(screen.getByText('thandi@example.co.za')).toBeInTheDocument()
    expect(screen.getByText(copy.fixedNote)).toBeInTheDocument()
  })

  test('gives the nickname and email no input to type into', () => {
    renderForm()

    // Three inputs, not five. The other two are a description list.
    expect(screen.getAllByRole('textbox')).toHaveLength(3)
  })

  test('offers no way to change the date of birth or the identity number', () => {
    renderForm()

    expect(screen.queryByLabelText(/date of birth/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/identity/i)).not.toBeInTheDocument()
  })
})

describe('the save button', () => {
  test('does nothing until something changes', () => {
    renderForm()

    expect(saveButton()).toBeDisabled()
    expect(screen.getByText(copy.unchanged)).toBeInTheDocument()
  })

  test('wakes up on a real edit', async () => {
    renderForm()

    await retype(copy.firstNameLabel, 'Thandiwe')

    expect(saveButton()).toBeEnabled()
  })

  test('stays asleep for whitespace nobody meant to type', async () => {
    // Compared on the normalised values. A button that lights up for a trailing space is a button
    // that promises a change it will not make.
    renderForm()

    await retype(copy.firstNameLabel, 'Thandi  ')

    expect(saveButton()).toBeDisabled()
  })

  test('stays asleep for the same number written differently', async () => {
    renderForm()

    await retype(copy.mobileLabel, '082 123 4567')

    expect(saveButton()).toBeDisabled()
  })

  test('wakes up on clearing the number, which is a change', async () => {
    renderForm()

    await retype(copy.mobileLabel, '')

    expect(saveButton()).toBeEnabled()
  })
})

describe('saving', () => {
  test('sends the normalised values, not what was typed', async () => {
    const user = userEvent.setup()
    renderForm()

    await retype(copy.mobileLabel, '083 765 4321')
    await user.click(saveButton())

    await waitFor(() =>
      expect(saveProfile).toHaveBeenCalledWith({
        first_name: 'Thandi',
        last_name: 'Mokoena',
        mobile: '+27837654321',
      }),
    )
  })

  test('tells its caller the record as it now stands', async () => {
    const user = userEvent.setup()
    const saved = { ...PROFILE, first_name: 'Thandiwe' }
    saveProfile.mockResolvedValue({ status: 'saved', profile: saved })
    const onSaved = renderForm()

    await retype(copy.firstNameLabel, 'Thandiwe')
    await user.click(saveButton())

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved))
  })

  test('says so, and goes quiet again', async () => {
    const user = userEvent.setup()
    renderForm()

    await retype(copy.firstNameLabel, 'Thandiwe')
    await user.click(saveButton())

    expect(await screen.findByText(copy.saved)).toBeInTheDocument()
    // Nothing left to save, so the button sleeps rather than offering to store it again.
    await waitFor(() => expect(saveButton()).toBeDisabled())
  })

  test('clears the confirmation as soon as anything is retyped', async () => {
    // Leaving "saved" on screen beside a field being edited would claim the new value is stored.
    const user = userEvent.setup()
    renderForm()

    await retype(copy.firstNameLabel, 'Thandiwe')
    await user.click(saveButton())
    expect(await screen.findByText(copy.saved)).toBeInTheDocument()

    await retype(copy.lastNameLabel, 'Mokoena-Smith')

    expect(screen.queryByText(copy.saved)).not.toBeInTheDocument()
  })
})

describe('refusals', () => {
  test('refuses a bad field itself, without asking the API', async () => {
    // The common case never leaves the browser. The rules here are the rules the API enforces.
    const user = userEvent.setup()
    renderForm()

    await retype(copy.firstNameLabel, '')
    await user.click(saveButton())

    expect(saveProfile).not.toHaveBeenCalled()
    expect(screen.getByLabelText(copy.firstNameLabel)).toHaveAttribute('aria-invalid', 'true')
  })

  test('marks the field and words the refusal', async () => {
    const user = userEvent.setup()
    renderForm()

    await retype(copy.mobileLabel, '0860001234')
    await user.click(saveButton())

    const field = screen.getByLabelText(copy.mobileLabel)
    expect(field).toHaveAttribute('aria-invalid', 'true')
    // Described by its own refusal, so a screen reader reads it with the field rather than
    // somewhere else on the page.
    expect(field.getAttribute('aria-describedby')).toContain('member-mobile-error')
  })

  test('reports a number that belongs to another account', async () => {
    /*
     * The one refusal the browser cannot make for itself: whether a well-formed number is already
     * held. It arrives as a sentence rather than marked against the field, because nothing about
     * what the member typed is wrong.
     */
    const user = userEvent.setup()
    saveProfile.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'Another account already holds that mobile number.' },
    })
    renderForm()

    await retype(copy.mobileLabel, '083 765 4321')
    await user.click(saveButton())

    // `role="alert"`, so it is announced without the member having to go looking: it arrives after
    // they pressed save and is the answer to it.
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Another account already holds that mobile number.')
    // Not marked against the field: nothing about what they typed is wrong.
    expect(screen.getByLabelText(copy.mobileLabel)).not.toHaveAttribute('aria-invalid')
  })

  test('never reports a refused save as saved', async () => {
    const user = userEvent.setup()
    saveProfile.mockResolvedValue({ status: 'refused', refusal: { detail: 'No.' } })
    const onSaved = renderForm()

    await retype(copy.mobileLabel, '083 765 4321')
    await user.click(saveButton())

    await screen.findByText('No.')
    expect(screen.queryByText(copy.saved)).not.toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()
  })

  test('says the club could not be reached rather than blaming the member', async () => {
    const user = userEvent.setup()
    saveProfile.mockResolvedValue({ status: 'failed', reason: 'The API is unreachable.' })
    renderForm()

    await retype(copy.firstNameLabel, 'Thandiwe')
    await user.click(saveButton())

    expect(await screen.findByText('The API is unreachable.')).toBeInTheDocument()
    // And the edit is still in the form, so the member can press save again rather than retype it.
    expect(screen.getByLabelText(copy.firstNameLabel)).toHaveValue('Thandiwe')
  })
})

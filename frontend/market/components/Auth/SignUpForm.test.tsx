import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import type { SignUpFormState } from '@/lib/sign-up'
import { SIGN_UP, SIGN_UP_OUTCOME, SIGN_UP_REFUSAL_MESSAGES } from '@/lib/sign-up-content'
import { SignUpForm } from './SignUpForm'

/**
 * The action is a prop rather than an import, which is what makes this testable: the component is a
 * plain form over a function, and the function here is a stub returning whichever state is under test.
 */
const actionReturning = (state: SignUpFormState) =>
  vi.fn(async (previous: SignUpFormState, form: FormData) => {
    // Both arguments are named so the mock carries their types, and the submitted form can be read
    // back off `mock.calls`.
    void previous
    void form

    return state
  })

describe('SignUpForm', () => {
  test('asks for four fields and no password', async () => {
    render(<SignUpForm action={actionReturning({ status: 'idle' })} />)

    expect(screen.getByLabelText(SIGN_UP.firstNameLabel)).toBeInTheDocument()
    expect(screen.getByLabelText(SIGN_UP.lastNameLabel)).toBeInTheDocument()
    expect(screen.getByLabelText(SIGN_UP.emailLabel)).toBeInTheDocument()
    expect(screen.getByLabelText(SIGN_UP.mobileLabel)).toBeInTheDocument()

    // Not a field anybody could type into, and said out loud so nobody hunts for it.
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument()
    expect(screen.getByText(SIGN_UP.noPassword)).toBeInTheDocument()
  })

  test('sends the submission to the action', async () => {
    const action = actionReturning({ status: 'idle' })

    render(<SignUpForm action={action} />)

    await userEvent.type(screen.getByLabelText(SIGN_UP.emailLabel), 'thandiwe@example.com')
    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    expect(action).toHaveBeenCalled()

    const form = action.mock.calls[0][1]
    expect(form.get('email')).toBe('thandiwe@example.com')
  })

  test('redraws what was typed, with the refusal against the field it concerns', async () => {
    const action = actionReturning({
      status: 'invalid',
      refusals: [{ field: 'email', reason: 'email-malformed' }],
      values: { firstName: 'Thandiwe', lastName: 'Mokoena', email: 'nope', mobile: '' },
    })

    render(<SignUpForm action={action} />)

    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    const email = await screen.findByLabelText(SIGN_UP.emailLabel)

    expect(email).toHaveValue('nope')
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveAccessibleDescription(
      expect.stringContaining(SIGN_UP_REFUSAL_MESSAGES['email-malformed']),
    )
    // What was already correct is not thrown away.
    expect(screen.getByLabelText(SIGN_UP.firstNameLabel)).toHaveValue('Thandiwe')
  })

  test('interrupts once for the whole form rather than summarising every field', async () => {
    const action = actionReturning({
      status: 'invalid',
      refusals: [{ field: 'firstName', reason: 'name-missing' }],
      values: { firstName: '', lastName: '', email: '', mobile: '' },
    })

    render(<SignUpForm action={action} />)
    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    expect(await screen.findByRole('alert')).toHaveTextContent(SIGN_UP_OUTCOME.refusedHeading)
  })

  test('replaces the form with the confirmation, so the same details cannot be sent twice', async () => {
    const action = actionReturning({ status: 'accepted', email: 'thandiwe@example.com' })

    render(<SignUpForm action={action} />)
    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    expect(await screen.findByText(SIGN_UP_OUTCOME.acceptedHeading)).toBeInTheDocument()
    expect(screen.queryByLabelText(SIGN_UP.emailLabel)).not.toBeInTheDocument()
  })

  test('words the confirmation conditionally, so it discloses nothing about the address', async () => {
    /*
     * The store answers identically for an address already on file. "Your account has been created"
     * would be untrue for one of the two cases, and "that address already has one" would tell anybody
     * who asks who shops here.
     */
    const action = actionReturning({ status: 'accepted', email: 'thandiwe@example.com' })

    render(<SignUpForm action={action} />)
    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    const said = (await screen.findByRole('status')).textContent ?? ''

    expect(said).toContain('thandiwe@example.com')
    expect(said.toLowerCase()).toContain('if')
    expect(said.toLowerCase()).not.toContain('already has an account')
  })

  test('says accounts are not open yet, and does not dress it as an error', async () => {
    const action = actionReturning({ status: 'unavailable' })

    render(<SignUpForm action={action} />)
    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    expect(await screen.findByText(SIGN_UP_OUTCOME.unavailableHeading)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('keeps the form up when the fault was ours, so it can be tried again', async () => {
    const action = actionReturning({ status: 'failed' })

    render(<SignUpForm action={action} />)
    await userEvent.click(screen.getByRole('button', { name: SIGN_UP.submit }))

    expect(await screen.findByRole('alert')).toHaveTextContent(SIGN_UP_OUTCOME.failedBody)
    expect(screen.getByLabelText(SIGN_UP.emailLabel)).toBeInTheDocument()
  })
})

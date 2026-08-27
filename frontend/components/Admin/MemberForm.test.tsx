import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MEMBER_RECORD } from '@/lib/member-register-content'
import type { Member } from '@/lib/member-register'
import { member } from '@/test-support/members'
import { MemberForm } from './MemberForm'

/*
 * The five details an administrator may correct.
 *
 * The tests split three ways: what the form refuses before it asks (the
 * browser's own rules), what it does with the two kinds of refusal the API
 * sends back, and what it deliberately does not offer at all.
 */

const onSubmit = vi.fn()
const onSaved = vi.fn()

const setup = (record: Member = member()) => {
  render(<MemberForm member={record} onSubmit={onSubmit} onSaved={onSaved} />)
}

const field = (label: string) => screen.getByRole('textbox', { name: new RegExp(label) })

const save = () => screen.getByRole('button', { name: MEMBER_RECORD.save })

beforeEach(() => {
  onSubmit.mockReset()
  onSaved.mockReset()
  onSubmit.mockResolvedValue({ status: 'saved', record: member() })
})

describe('the fields it offers', () => {
  test('draws the record as stored', () => {
    setup(member({ first_name: 'Thabo', last_name: 'Mahlangu' }))

    expect(field(MEMBER_RECORD.firstNameLabel)).toHaveValue('Thabo')
    expect(field(MEMBER_RECORD.lastNameLabel)).toHaveValue('Mahlangu')
    expect(field(MEMBER_RECORD.emailLabel)).toHaveValue('thabo@example.com')
  })

  test('offers no role field', () => {
    /*
     * Appointing a cultivator or an administrator is done in the back office and
     * nowhere else — `design/backend.md` section 10. Handing out authority over
     * other members' records is not a form field, and the API's own allow-list
     * refuses `role` as a `ValueError` rather than a refusal, because a field
     * reaching it means a schema has drifted.
     */
    setup()

    expect(screen.queryByRole('combobox', { name: /role/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /role/i })).not.toBeInTheDocument()
  })

  test('offers no standing field', () => {
    // Suspension confirms first and ends the member's sessions. A dropdown that
    // did it silently on save would be the same act with none of that.
    setup()

    expect(screen.queryByRole('combobox', { name: /standing/i })).not.toBeInTheDocument()
  })

  test('offers no identity number field', () => {
    setup()

    expect(screen.queryByRole('textbox', { name: /identity/i })).not.toBeInTheDocument()
  })
})

describe('the save button', () => {
  test('is inert until something changes', () => {
    // A save button that is live on a form nobody has touched promises a change
    // it will not make.
    setup()

    expect(save()).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(MEMBER_RECORD.unchanged)
  })

  test('stays inert for a change the club would not store', async () => {
    setup()

    const surname = field(MEMBER_RECORD.lastNameLabel)
    await userEvent.clear(surname)
    await userEvent.type(surname, '  Mahlangu  ')
    await userEvent.tab()

    expect(save()).toBeDisabled()
  })

  test('comes alive for a real change', async () => {
    setup()

    const surname = field(MEMBER_RECORD.lastNameLabel)
    await userEvent.clear(surname)
    await userEvent.type(surname, 'Ncube')
    await userEvent.tab()

    expect(save()).toBeEnabled()
  })
})

describe('what the browser refuses before asking', () => {
  test('marks the field and does not call the API', async () => {
    setup()

    const email = field(MEMBER_RECORD.emailLabel)
    await userEvent.clear(email)
    await userEvent.type(email, 'not-an-address')
    await userEvent.tab()
    await userEvent.click(save())

    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(MEMBER_RECORD.refusedSummary)
    expect(field(MEMBER_RECORD.emailLabel)).toHaveAttribute('aria-invalid', 'true')
  })
})

describe('what the API refuses', () => {
  test('renders a per-field refusal against its field', async () => {
    /*
     * The normal path here, unlike on the profile form. Whether another account
     * already holds an address is not a question a browser can answer, so this
     * is the primary way an administrator learns what is wrong — not a sign that
     * two rule sets have drifted.
     */
    onSubmit.mockResolvedValue({
      status: 'refused',
      refusal: {
        detail: 'That could not be saved.',
        fields: { email: ['Another account already uses that email address.'] },
      },
    })
    setup()

    const email = field(MEMBER_RECORD.emailLabel)
    await userEvent.clear(email)
    await userEvent.type(email, 'taken@example.com')
    await userEvent.tab()
    await userEvent.click(save())

    expect(
      await screen.findByText('Another account already uses that email address.'),
    ).toBeInTheDocument()
  })

  test('renders a record-level refusal as a sentence, with no field marked', async () => {
    // An erased account is not a field an administrator can correct, so marking
    // it up against an input would point at nothing.
    onSubmit.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'This account was erased at the member’s request.', fields: {} },
    })
    setup()

    const surname = field(MEMBER_RECORD.lastNameLabel)
    await userEvent.clear(surname)
    await userEvent.type(surname, 'Ncube')
    await userEvent.tab()
    await userEvent.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This account was erased at the member’s request.',
    )
  })

  test('reports an unreachable API as its own kind of failure', async () => {
    onSubmit.mockResolvedValue({ status: 'failed', reason: 'down' })
    setup()

    const surname = field(MEMBER_RECORD.lastNameLabel)
    await userEvent.clear(surname)
    await userEvent.type(surname, 'Ncube')
    await userEvent.tab()
    await userEvent.click(save())

    expect(await screen.findByRole('alert')).toHaveTextContent(MEMBER_RECORD.failed)
  })
})

describe('a successful save', () => {
  test('tells the screen, and redraws from what the server stored', async () => {
    /*
     * Not from what was typed. Both names and the mobile number come back
     * normalised, and an administrator who typed `082 123 4567` should see the
     * club's own form come back rather than the string they entered.
     */
    onSubmit.mockResolvedValue({
      status: 'saved',
      record: member({ last_name: 'Ncube', mobile: '+27829998888' }),
    })
    setup()

    const surname = field(MEMBER_RECORD.lastNameLabel)
    await userEvent.clear(surname)
    await userEvent.type(surname, 'ncube')
    await userEvent.tab()
    await userEvent.click(save())

    expect(await screen.findByText(MEMBER_RECORD.saved)).toBeInTheDocument()
    expect(onSaved).toHaveBeenCalledWith(
      expect.objectContaining({ last_name: 'Ncube' }),
    )
    expect(field(MEMBER_RECORD.mobileLabel)).toHaveValue('+27829998888')
  })

  test('leaves the button inert again, because nothing differs any more', async () => {
    onSubmit.mockResolvedValue({ status: 'saved', record: member({ last_name: 'Ncube' }) })
    setup()

    const surname = field(MEMBER_RECORD.lastNameLabel)
    await userEvent.clear(surname)
    await userEvent.type(surname, 'Ncube')
    await userEvent.tab()
    await userEvent.click(save())

    await screen.findByText(MEMBER_RECORD.saved)
    expect(save()).toBeDisabled()
  })
})

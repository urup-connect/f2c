import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, test } from 'vitest'
import { AGE_CHECK } from '@/lib/age-gate-content'
import { DateOfBirthFields } from './DateOfBirthFields'

/* design/features/age-gate-before-sign-up.md criteria 21, 22 and 27. */

describe('DateOfBirthFields', () => {
  test('groups the three fields under one legend', () => {
    // Criterion 21. A screen reader announces "Date of birth" before "Day".
    render(<DateOfBirthFields />)

    expect(screen.getByRole('group', { name: AGE_CHECK.legend })).toBeInTheDocument()
  })

  test('asks for day, month and year, in that order', () => {
    render(<DateOfBirthFields />)

    const fields = screen.getAllByRole('textbox')

    expect(fields.map((field) => field.getAttribute('name'))).toEqual(['day', 'month', 'year'])
  })

  test('labels each field visibly', () => {
    render(<DateOfBirthFields />)

    for (const label of Object.values(AGE_CHECK.fields)) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
  })

  test('shows a number keypad on a phone and accepts autofill', () => {
    // Criterion 22.
    render(<DateOfBirthFields />)

    const expected = [
      [AGE_CHECK.fields.day, 'bday-day', '2'],
      [AGE_CHECK.fields.month, 'bday-month', '2'],
      [AGE_CHECK.fields.year, 'bday-year', '4'],
    ] as const

    for (const [label, autoComplete, maxLength] of expected) {
      const field = screen.getByLabelText(label)

      expect(field).toHaveAttribute('inputmode', 'numeric')
      expect(field).toHaveAttribute('autocomplete', autoComplete)
      expect(field).toHaveAttribute('maxlength', maxLength)
    }
  })

  test('is a text field rather than a number spinner', () => {
    // A number input brings a spinner, a scroll-wheel hazard and inconsistent announcement,
    // for no gain on a fixed-length number. See section 8.
    render(<DateOfBirthFields />)

    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
    expect(screen.getAllByRole('textbox')).toHaveLength(3)
  })

  test('reaches all three fields by keyboard, in reading order', async () => {
    const user = userEvent.setup()
    render(<DateOfBirthFields />)

    const [day, month, year] = screen.getAllByRole('textbox')

    await user.tab()
    expect(day).toHaveFocus()

    await user.tab()
    expect(month).toHaveFocus()

    await user.tab()
    expect(year).toHaveFocus()
  })

  test('marks nothing invalid until something is', () => {
    render(<DateOfBirthFields />)

    for (const field of screen.getAllByRole('textbox')) {
      expect(field).not.toHaveAttribute('aria-invalid')
    }
  })

  test('marks every field invalid on a refusal, because the date is what was wrong', () => {
    // Criterion 27.
    render(<DateOfBirthFields invalid />)

    for (const field of screen.getAllByRole('textbox')) {
      expect(field).toHaveAttribute('aria-invalid', 'true')
    }
  })

  test('describes the group with whatever the caller points it at', () => {
    // Criterion 27. The hint and any refusal are described against the group, not one field.
    render(<DateOfBirthFields describedBy={['a-hint', 'an-error']} />)

    expect(screen.getByRole('group', { name: AGE_CHECK.legend })).toHaveAttribute(
      'aria-describedby',
      'a-hint an-error',
    )
  })

  test('carries no description when the caller supplies none', () => {
    render(<DateOfBirthFields />)

    expect(screen.getByRole('group', { name: AGE_CHECK.legend })).not.toHaveAttribute(
      'aria-describedby',
    )
  })

  test('shows a visible focus ring on every field', () => {
    render(<DateOfBirthFields />)

    for (const field of screen.getAllByRole('textbox')) {
      expect(field.className).toMatch(/focus-visible:/)
    }
  })

  test('puts the visitor back in the first field after a refusal', () => {
    /*
     * Criterion 27. A role="alert" that is already in the document when the page loads is not
     * reliably announced — live regions announce changes, and a refusal here arrives as a fresh
     * page. Focusing the first field is declarative HTML, so it works with JavaScript off, and
     * it brings the group's description with it.
     */
    render(<DateOfBirthFields invalid />)

    expect(screen.getByLabelText(AGE_CHECK.fields.day)).toHaveFocus()
  })

  test('carries the focus in the served HTML, so it happens without JavaScript too', () => {
    // React applies autoFocus imperatively when it renders in the browser, and emits the
    // attribute when it renders on the server. Only the second is what a visitor with
    // JavaScript disabled receives, so it is asserted against the server markup.
    const markup = renderToStaticMarkup(<DateOfBirthFields invalid />)

    expect(markup).toMatch(/id="dob-day"[^>]*autofocus/)
    expect(markup).not.toMatch(/id="dob-month"[^>]*autofocus/)
  })

  test('does not grab focus when there is nothing wrong', () => {
    render(<DateOfBirthFields />)

    expect(renderToStaticMarkup(<DateOfBirthFields />)).not.toContain('autofocus')
    expect(document.body).toHaveFocus()
  })

  test('takes the error colour on the field borders when invalid', () => {
    // Criterion 42, the colour half of it. The words are the form's job.
    render(<DateOfBirthFields invalid />)

    for (const field of screen.getAllByRole('textbox')) {
      expect(field).toHaveClass('border-error')
    }
  })
})

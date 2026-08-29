import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { TextField } from './TextField'

/* design/features/member-details-at-sign-up.md criterion 2, and section 8. */

describe('TextField', () => {
  test('labels the input visibly, with no placeholder standing in for a label', () => {
    render(<TextField name="nickname" label="Nickname" />)

    const field = screen.getByLabelText('Nickname')

    expect(field).toBeInTheDocument()
    expect(field).not.toHaveAttribute('placeholder')
  })

  test('names the input so the form can read it', () => {
    render(<TextField name="nickname" label="Nickname" />)

    expect(screen.getByLabelText('Nickname')).toHaveAttribute('name', 'nickname')
  })

  test('describes the input with its hint', () => {
    render(<TextField name="nickname" label="Nickname" hint="What other members see." />)

    expect(screen.getByLabelText('Nickname')).toHaveAccessibleDescription(
      'What other members see.',
    )
  })

  test('carries no description when there is no hint and no error', () => {
    render(<TextField name="nickname" label="Nickname" />)

    expect(screen.getByLabelText('Nickname')).not.toHaveAttribute('aria-describedby')
  })

  test('marks the input invalid and describes it with the error', () => {
    render(<TextField name="nickname" label="Nickname" error="That nickname is taken." />)

    const field = screen.getByLabelText('Nickname')

    expect(field).toHaveAttribute('aria-invalid', 'true')
    expect(field).toHaveAccessibleDescription('That nickname is taken.')
  })

  test('describes the input with both the hint and the error, in that order', () => {
    render(
      <TextField
        name="nickname"
        label="Nickname"
        hint="What other members see."
        error="That nickname is taken."
      />,
    )

    expect(screen.getByLabelText('Nickname')).toHaveAccessibleDescription(
      'What other members see. That nickname is taken.',
    )
  })

  test('is not marked invalid when there is no error', () => {
    render(<TextField name="nickname" label="Nickname" hint="What other members see." />)

    expect(screen.getByLabelText('Nickname')).not.toHaveAttribute('aria-invalid')
  })

  test('shows the error as text, not as colour alone', () => {
    render(<TextField name="nickname" label="Nickname" error="That nickname is taken." />)

    expect(screen.getByText('That nickname is taken.')).toBeInTheDocument()
  })

  test('passes through the autofill token, keypad and maximum length', () => {
    render(
      <TextField
        name="idNumber"
        label="South African ID number"
        autoComplete="off"
        inputMode="numeric"
        maxLength={13}
      />,
    )

    const field = screen.getByLabelText('South African ID number')

    expect(field).toHaveAttribute('autocomplete', 'off')
    expect(field).toHaveAttribute('inputmode', 'numeric')
    expect(field).toHaveAttribute('maxlength', '13')
  })

  test('is a text input, never a number input', () => {
    // `type="number"` strips a leading zero, which is fatal for both a mobile number and an ID.
    render(<TextField name="idNumber" label="ID" inputMode="numeric" />)

    expect(screen.getByLabelText('ID')).toHaveAttribute('type', 'text')
  })

  test('keeps what the visitor typed', async () => {
    render(<TextField name="nickname" label="Nickname" />)

    await userEvent.type(screen.getByLabelText('Nickname'), 'GreenThumb')

    expect(screen.getByLabelText('Nickname')).toHaveValue('GreenThumb')
  })

  test('tidies its own value when it loses focus, when asked to', async () => {
    // Criterion 53. The field does the rewriting; deciding what to rewrite is the caller's job.
    render(
      <TextField name="mobile" label="Mobile number" formatOnBlur={(value) => value.trim()} />,
    )

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, '  0821234567  ')
    await userEvent.tab()

    expect(field).toHaveValue('0821234567')
  })

  test('leaves its value alone on blur when given nothing to do', async () => {
    render(<TextField name="nickname" label="Nickname" />)

    const field = screen.getByLabelText('Nickname')

    await userEvent.type(field, '  GreenThumb  ')
    await userEvent.tab()

    expect(field).toHaveValue('  GreenThumb  ')
  })

  test('drops a character it is told not to accept, as it is typed', async () => {
    // Criterion 57. Nothing is announced: the keystroke simply does not land.
    render(
      <TextField
        name="idNumber"
        label="ID"
        filterOnInput={(value) => value.replace(/\D/g, '')}
      />,
    )

    const field = screen.getByLabelText('ID')

    await userEvent.type(field, '9a0b0c3')

    expect(field).toHaveValue('9003')
  })

  test('leaves the caret where it was when a character is dropped', async () => {
    /*
     * The reason this is filtered on input rather than blocked on keypress: a paste has to be
     * cleaned too, and cleaning a value moves the caret to the end unless it is put back.
     */
    render(
      <TextField
        name="idNumber"
        label="ID"
        defaultValue="9003"
        filterOnInput={(value) => value.replace(/\D/g, '')}
      />,
    )

    const field = screen.getByLabelText('ID')

    await userEvent.type(field, 'x', { initialSelectionStart: 2, initialSelectionEnd: 2 })

    expect(field).toHaveValue('9003')
    expect((field as HTMLInputElement).selectionStart).toBe(2)
  })

  test('keeps the caret in place when a dropped character sits mid-value', async () => {
    render(
      <TextField
        name="idNumber"
        label="ID"
        defaultValue="9003"
        filterOnInput={(value) => value.replace(/\D/g, '')}
      />,
    )

    const field = screen.getByLabelText('ID')

    await userEvent.type(field, '5', { initialSelectionStart: 2, initialSelectionEnd: 2 })

    expect(field).toHaveValue('90503')
    expect((field as HTMLInputElement).selectionStart).toBe(3)
  })

  test('accepts everything when given no filter', async () => {
    render(<TextField name="firstName" label="First name" />)

    await userEvent.type(screen.getByLabelText('First name'), "O'Brien")

    expect(screen.getByLabelText('First name')).toHaveValue("O'Brien")
  })

  test('starts from the value the page gives it', () => {
    render(<TextField name="nickname" label="Nickname" defaultValue="GreenThumb" />)

    expect(screen.getByLabelText('Nickname')).toHaveValue('GreenThumb')
  })
  test('describes the input with a notice, without marking it invalid', () => {
    /*
     * A notice is not a refusal. The field is still acceptable, so nothing about it may say
     * otherwise — an `aria-invalid` on a valid field tells a screen reader user to fix something
     * that is not broken.
     */
    render(
      <TextField name="nickname" label="Nickname" notice="We could not confirm that just now." />,
    )

    const field = screen.getByLabelText('Nickname')

    expect(field).toHaveAccessibleDescription('We could not confirm that just now.')
    expect(field).not.toHaveAttribute('aria-invalid')
  })

  test('announces a notice politely, because it arrives after the visitor has moved on', () => {
    render(<TextField name="nickname" label="Nickname" notice="Could not confirm." />)

    expect(screen.getByRole('status')).toHaveTextContent('Could not confirm.')
  })

  test('describes the input with its hint and its notice together', () => {
    render(
      <TextField
        name="nickname"
        label="Nickname"
        hint="What other members see."
        notice="Could not confirm."
      />,
    )

    expect(screen.getByLabelText('Nickname')).toHaveAccessibleDescription(
      'What other members see. Could not confirm.',
    )
  })

  test('tells the caller what the field holds once it loses focus', async () => {
    const onBlurValue = vi.fn()

    render(<TextField name="nickname" label="Nickname" onBlurValue={onBlurValue} />)

    await userEvent.type(screen.getByLabelText('Nickname'), 'GreenThumb')
    await userEvent.tab()

    expect(onBlurValue).toHaveBeenCalledWith('GreenThumb')
  })

  test('does not tell the caller anything while the field still has focus', async () => {
    const onBlurValue = vi.fn()

    render(<TextField name="nickname" label="Nickname" onBlurValue={onBlurValue} />)

    await userEvent.type(screen.getByLabelText('Nickname'), 'GreenThumb')

    // Asking on every keystroke would ask about a dozen values the visitor never finished typing.
    expect(onBlurValue).not.toHaveBeenCalled()
  })

  test('tells the caller the formatted value, not the raw one', async () => {
    const onBlurValue = vi.fn()

    render(
      <TextField
        name="mobile"
        label="Mobile number"
        formatOnBlur={(value) => value.replace(/\D/g, '')}
        onBlurValue={onBlurValue}
      />,
    )

    await userEvent.type(screen.getByLabelText('Mobile number'), '082 123 4567')
    await userEvent.tab()

    // What leaves the field is what the visitor can now see in it.
    expect(onBlurValue).toHaveBeenCalledWith('0821234567')
    expect(screen.getByLabelText('Mobile number')).toHaveValue('0821234567')
  })
})

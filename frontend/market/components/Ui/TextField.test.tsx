import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { TextField } from './TextField'

describe('TextField', () => {
  test('labels the input, so clicking the label focuses it', async () => {
    render(<TextField name="firstName" label="First name" />)

    const input = screen.getByLabelText('First name')

    await userEvent.click(screen.getByText('First name'))

    expect(input).toHaveFocus()
  })

  test('describes the input with its hint', () => {
    render(<TextField name="mobile" label="Mobile number" hint="Optional." />)

    expect(screen.getByLabelText('Mobile number')).toHaveAccessibleDescription('Optional.')
  })

  test('marks a refused field invalid and describes it with the refusal', () => {
    render(<TextField name="mobile" label="Mobile number" error="That is not a mobile number." />)

    const input = screen.getByLabelText('Mobile number')

    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAccessibleDescription('That is not a mobile number.')
  })

  test('is not marked invalid when there is no refusal', () => {
    render(<TextField name="firstName" label="First name" />)

    expect(screen.getByLabelText('First name')).not.toHaveAttribute('aria-invalid')
  })

  test('describes the input with both the hint and the refusal, in that order', () => {
    render(
      <TextField name="mobile" label="Mobile number" hint="Optional." error="Not a number." />,
    )

    expect(screen.getByLabelText('Mobile number')).toHaveAccessibleDescription(
      'Optional. Not a number.',
    )
  })

  test('is always type=text, whatever keypad it asks for', () => {
    // A number input strips a leading zero, which is fatal for a mobile number written 082…
    render(<TextField name="mobile" label="Mobile number" inputMode="tel" />)

    const input = screen.getByLabelText('Mobile number')

    expect(input).toHaveAttribute('type', 'text')
    expect(input).toHaveAttribute('inputmode', 'tel')
  })

  test('carries no placeholder, ever', () => {
    render(<TextField name="firstName" label="First name" hint="Your first name." />)

    expect(screen.getByLabelText('First name')).not.toHaveAttribute('placeholder')
  })

  test('carries no required attribute, so refusals are worded by us and not by the browser', () => {
    render(<TextField name="firstName" label="First name" />)

    expect(screen.getByLabelText('First name')).not.toHaveAttribute('required')
  })

  test('drops characters the field will never accept, as they are typed', async () => {
    render(
      <TextField
        name="mobile"
        label="Mobile number"
        filterOnInput={(value) => value.replace(/[^\d]/g, '')}
      />,
    )

    const input = screen.getByLabelText('Mobile number')

    await userEvent.type(input, '08a2b1')

    expect(input).toHaveValue('0821')
  })

  test('formats the value once the field loses focus, never while typing', async () => {
    render(
      <TextField
        name="mobile"
        label="Mobile number"
        formatOnBlur={() => '082 123 4567'}
      />,
    )

    const input = screen.getByLabelText('Mobile number')

    await userEvent.type(input, '0821234567')
    expect(input).toHaveValue('0821234567')

    await userEvent.tab()
    expect(input).toHaveValue('082 123 4567')
  })

  test('tells a caller what the field holds after formatting, not before', async () => {
    const onBlurValue = vi.fn()

    render(
      <TextField
        name="mobile"
        label="Mobile number"
        formatOnBlur={() => '082 123 4567'}
        onBlurValue={onBlurValue}
      />,
    )

    await userEvent.type(screen.getByLabelText('Mobile number'), '0821234567')
    await userEvent.tab()

    expect(onBlurValue).toHaveBeenCalledWith('082 123 4567')
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { TextAreaField } from './TextAreaField'

/*
 * The third sibling to `TextField` and `SelectField`.
 *
 * The property worth testing is the one that makes it a separate component:
 * **it reports on every keystroke, not on blur**. The form's "nothing has changed
 * yet" state has to notice a description being typed, and on blur it would not
 * until the administrator clicked somewhere else -- so a save button would stay
 * inert beneath a field somebody was filling in, which reads as a broken form.
 */

const setup = (props: Partial<Parameters<typeof TextAreaField>[0]> = {}) => {
  const onValue = vi.fn()
  render(
    <TextAreaField
      name="description"
      label="Description"
      value=""
      onValue={onValue}
      {...props}
    />,
  )
  return { onValue }
}

describe('reporting', () => {
  test('reports on every keystroke rather than on blur', async () => {
    const { onValue } = setup()

    await userEvent.type(screen.getByRole('textbox', { name: 'Description' }), 'Tall')

    // Four keystrokes, four calls. Controlled, so each carries one character --
    // what matters is that the caller heard about the first one immediately.
    expect(onValue).toHaveBeenCalledTimes(4)
    expect(onValue).toHaveBeenNthCalledWith(1, 'T')
  })

  test('shows the value it was given', () => {
    setup({ value: 'A tall, quick sativa.' })

    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveValue(
      'A tall, quick sativa.',
    )
  })

  test('is controlled, so the caller can reset it', () => {
    // The property the profile form's remount trick works around and this does
    // not need: a new `value` prop replaces what is on screen.
    const { rerender } = render(
      <TextAreaField name="d" label="D" value="First" onValue={vi.fn()} />,
    )

    rerender(<TextAreaField name="d" label="D" value="Second" onValue={vi.fn()} />)

    expect(screen.getByRole('textbox', { name: 'D' })).toHaveValue('Second')
  })
})

describe('the label, hint and refusal', () => {
  test('the label names the control', () => {
    setup()

    expect(screen.getByRole('textbox', { name: 'Description' })).toBeInTheDocument()
  })

  test('a hint is announced with the control', () => {
    setup({ hint: 'Claim nothing about what it treats.' })

    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveAccessibleDescription(
      'Claim nothing about what it treats.',
    )
  })

  test('a refusal marks the field invalid and is announced', () => {
    setup({ error: 'Too long.' })

    const field = screen.getByRole('textbox', { name: 'Description' })

    expect(field).toBeInvalid()
    expect(field).toHaveAccessibleDescription('Too long.')
  })
})

describe('what it deliberately does not do', () => {
  test('sets no maxLength', () => {
    // `Strain.description` is an unbounded TextField. A limit here would be this
    // component enforcing a rule the column does not have.
    setup()

    expect(
      screen.getByRole('textbox', { name: 'Description' }),
    ).not.toHaveAttribute('maxlength')
  })

  test('takes a row count so prose gets more room than a lineage', () => {
    setup({ rows: 5 })

    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveAttribute(
      'rows',
      '5',
    )
  })
})

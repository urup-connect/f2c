import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { SelectField } from './SelectField'

/*
 * `TextField`'s sibling for a fixed set of values.
 *
 * The assertions cluster on one property: **"not chosen" is a visible state**. A
 * `select` with no empty option opens showing its first choice as though somebody
 * had picked it, and an administrator who agrees with what they see submits a
 * value nobody selected. Everything else here is the accessibility wiring, which
 * is easy to leave out and impossible to notice with a mouse.
 */

const CHOICES = [
  { value: 'indica', label: 'Indica' },
  { value: 'sativa', label: 'Sativa' },
] as const

const setup = (props: Partial<Parameters<typeof SelectField>[0]> = {}) => {
  const onValue = vi.fn()
  render(
    <SelectField
      name="strain-type"
      label="Type"
      value=""
      choices={CHOICES}
      placeholder="Choose one"
      onValue={onValue}
      {...props}
    />,
  )
  return { onValue }
}

describe('the empty option', () => {
  test('is rendered on every select', () => {
    setup()

    expect(screen.getByRole('option', { name: 'Choose one' })).toBeInTheDocument()
  })

  test('is what is selected when nothing has been chosen', () => {
    setup({ value: '' })

    expect(screen.getByRole('combobox', { name: 'Type' })).toHaveValue('')
  })

  test('carries an empty value, so a blank submission is distinguishable', () => {
    setup()

    expect(screen.getByRole('option', { name: 'Choose one' })).toHaveValue('')
  })
})

describe('the choices', () => {
  test('are all offered', () => {
    setup()

    expect(screen.getByRole('option', { name: 'Indica' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Sativa' })).toBeInTheDocument()
  })

  test('show the current value as selected', () => {
    setup({ value: 'sativa' })

    expect(screen.getByRole('combobox', { name: 'Type' })).toHaveValue('sativa')
  })

  test('report what was chosen', async () => {
    const { onValue } = setup()

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'indica')

    expect(onValue).toHaveBeenCalledWith('indica')
  })

  test('report a return to the empty option', async () => {
    // Clearing a filter has to be reportable, or "any status" is unreachable
    // once a status has been picked.
    const { onValue } = setup({ value: 'indica' })

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Type' }), '')

    expect(onValue).toHaveBeenCalledWith('')
  })
})

describe('the label, hint and refusal', () => {
  test('the label names the control', () => {
    setup()

    expect(screen.getByRole('combobox', { name: 'Type' })).toBeInTheDocument()
  })

  test('a hint is announced with the control', () => {
    setup({ hint: 'The classification, not the parentage.' })

    expect(screen.getByRole('combobox', { name: 'Type' })).toHaveAccessibleDescription(
      'The classification, not the parentage.',
    )
  })

  test('a refusal is announced with the control', () => {
    setup({ error: 'Choose Indica, Sativa or Hybrid.' })

    expect(screen.getByRole('combobox', { name: 'Type' })).toHaveAccessibleDescription(
      'Choose Indica, Sativa or Hybrid.',
    )
  })

  test('a hint and a refusal are announced together', () => {
    // Not one replacing the other: the hint says what the field wants and the
    // refusal says what is wrong with what is in it.
    setup({ hint: 'A hint.', error: 'A refusal.' })

    expect(screen.getByRole('combobox', { name: 'Type' })).toHaveAccessibleDescription(
      'A hint. A refusal.',
    )
  })

  test('a refused field is marked invalid', () => {
    setup({ error: 'Choose one.' })

    expect(screen.getByRole('combobox', { name: 'Type' })).toBeInvalid()
  })

  test('a field with no refusal is not marked invalid', () => {
    setup()

    expect(screen.getByRole('combobox', { name: 'Type' })).toBeValid()
  })
})

describe('what it deliberately does not do', () => {
  test('has no required attribute', () => {
    // Same reason `TextField` has none: it would hand a browser-worded bubble to
    // whoever has JavaScript and our own wording to whoever does not, so the two
    // would not behave alike. `checkStrain` refuses an empty required field in
    // the page's own words.
    setup()

    expect(screen.getByRole('combobox', { name: 'Type' })).not.toBeRequired()
  })
})

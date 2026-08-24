import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { AGE_CHECK } from '@/lib/age-gate-content'
import { AgeCheckForm } from './AgeCheckForm'
import type { AgeCheckRefusal } from '@/lib/age-gate'

/* design/features/age-gate-before-sign-up.md criteria 21, 26, 27, 29 and 42. */

const noop = () => {}

describe('AgeCheckForm', () => {
  test('says why the date of birth is being asked for', () => {
    // Criterion 29.
    render(<AgeCheckForm action={noop} />)

    expect(screen.getByText(AGE_CHECK.hint)).toBeInTheDocument()
  })

  test('describes the field group with the hint', () => {
    render(<AgeCheckForm action={noop} />)

    const group = screen.getByRole('group', { name: AGE_CHECK.legend })
    const describedBy = group.getAttribute('aria-describedby')?.split(' ') ?? []

    expect(describedBy).toHaveLength(1)
    expect(document.getElementById(describedBy[0])).toHaveTextContent(AGE_CHECK.hint)
  })

  test('offers one submit control', () => {
    render(<AgeCheckForm action={noop} />)

    expect(screen.getByRole('button', { name: AGE_CHECK.submit })).toHaveAttribute(
      'type',
      'submit',
    )
  })

  test('shows no refusal until there is one', () => {
    render(<AgeCheckForm action={noop} />)

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test.each([
    'under-age',
    'incomplete',
    'not-a-number',
    'not-a-real-date',
    'in-the-future',
    'implausible',
  ] as const satisfies readonly AgeCheckRefusal[])('announces the %s refusal', (refusal) => {
    // Criterion 26 and 27: in a live region, so it is announced rather than only seen.
    render(<AgeCheckForm action={noop} refusal={refusal} />)

    expect(screen.getByRole('alert')).toHaveTextContent(AGE_CHECK.refusals[refusal])
  })

  test('links the refusal to the field group, after the hint', () => {
    // Criterion 27.
    render(<AgeCheckForm action={noop} refusal="under-age" />)

    const group = screen.getByRole('group', { name: AGE_CHECK.legend })
    const described = (group.getAttribute('aria-describedby') ?? '')
      .split(' ')
      .map((id) => document.getElementById(id)?.textContent)

    expect(described).toEqual([AGE_CHECK.hint, AGE_CHECK.refusals['under-age']])
  })

  test('marks the fields invalid on a refusal', () => {
    render(<AgeCheckForm action={noop} refusal="under-age" />)

    for (const field of screen.getAllByRole('textbox')) {
      expect(field).toHaveAttribute('aria-invalid', 'true')
    }
  })

  test('sets the refusal in the error colour, and states it in words', () => {
    // Criterion 42. Colour alone is never the signal.
    render(<AgeCheckForm action={noop} refusal="under-age" />)

    const alert = screen.getByRole('alert')

    expect(alert).toHaveClass('text-error')
    expect(alert).toHaveTextContent(/18 or older/i)
  })

  test('hands the typed date to its action', async () => {
    const user = userEvent.setup()
    const action = vi.fn()
    render(<AgeCheckForm action={action} />)

    await user.type(screen.getByLabelText(AGE_CHECK.fields.day), '21')
    await user.type(screen.getByLabelText(AGE_CHECK.fields.month), '4')
    await user.type(screen.getByLabelText(AGE_CHECK.fields.year), '1994')
    await user.click(screen.getByRole('button', { name: AGE_CHECK.submit }))

    expect(action).toHaveBeenCalledTimes(1)

    const submitted = action.mock.calls[0][0] as FormData

    expect([submitted.get('day'), submitted.get('month'), submitted.get('year')]).toEqual([
      '21',
      '4',
      '1994',
    ])
  })

  test('posts rather than putting the date of birth in a query string', () => {
    // Criterion 28. A GET form would write a birthday into the URL, and into every access log.
    render(<AgeCheckForm action={noop} />)

    const form = screen.getByRole('button', { name: AGE_CHECK.submit }).closest('form')

    expect(form).not.toHaveAttribute('method', 'get')
  })
})

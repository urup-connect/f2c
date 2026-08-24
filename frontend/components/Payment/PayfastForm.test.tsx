import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { PayfastForm } from './PayfastForm'
import type { Checkout } from '@/lib/checkout'

/* design/features/payments.md section 5. */

const FIELDS = {
  merchant_id: '10000100',
  merchant_key: '46f0cd694581a',
  return_url: 'http://localhost:3000/signup/paid',
  m_payment_id: '01a03412-0000-7000-8000-000000000000',
  amount: '150.00',
  item_name: 'Club membership',
  subscription_type: '1',
  recurring_amount: '150.00',
  frequency: '3',
  cycles: '0',
  signature: 'd6dc0b1e2d3a4b5c6d7e8f90a1b2c3d4',
}

const checkout = (overrides: Partial<Checkout> = {}): Checkout => ({
  url: 'https://sandbox.payfast.co.za/eng/process',
  fields: FIELDS,
  ...overrides,
})

const form = () => document.querySelector('form') as HTMLFormElement

const hidden = () =>
  Array.from(document.querySelectorAll<HTMLInputElement>('input[type="hidden"]'))

describe('the Payfast form', () => {
  test('posts to the payment engine the API named', () => {
    render(<PayfastForm checkout={checkout()} />)

    expect(form()).toHaveAttribute('method', 'post')
    expect(form()).toHaveAttribute('action', 'https://sandbox.payfast.co.za/eng/process')
  })

  test('posts to the live engine when that is what the API named', () => {
    // The environment is Django's decision, never this component's.
    render(<PayfastForm checkout={checkout({ url: 'https://www.payfast.co.za/eng/process' })} />)

    expect(form()).toHaveAttribute('action', 'https://www.payfast.co.za/eng/process')
  })

  test('renders every field it was given', () => {
    render(<PayfastForm checkout={checkout()} />)

    expect(hidden()).toHaveLength(Object.keys(FIELDS).length)
  })

  test('renders each field with the exact name and value the API sent', () => {
    /*
     * The property this whole component is written around. Payfast signs the checkout over exactly
     * the set Django built, so a field renamed, re-cased or trimmed here makes the signature fail
     * — and Payfast answers a failed signature with a generic decline that names nothing.
     */
    render(<PayfastForm checkout={checkout()} />)

    expect(
      Object.fromEntries(hidden().map((input) => [input.name, input.value])),
    ).toEqual(FIELDS)
  })

  test('renders the signature, without which Payfast refuses the checkout', () => {
    render(<PayfastForm checkout={checkout()} />)

    const signature = hidden().find((input) => input.name === 'signature')

    expect(signature?.value).toBe(FIELDS.signature)
  })

  test('preserves the order the fields arrived in', () => {
    render(<PayfastForm checkout={checkout()} />)

    expect(hidden().map((input) => input.name)).toEqual(Object.keys(FIELDS))
  })

  test('adds no field of its own', () => {
    render(<PayfastForm checkout={checkout()} />)

    expect(hidden().map((input) => input.name).sort()).toEqual(Object.keys(FIELDS).sort())
  })

  test('has a real submit button, so the screen works without JavaScript', () => {
    /*
     * Every other signed-out screen in this product works with JavaScript off, and the one that
     * takes money is not the place to stop. There is no JavaScript path here at all -- the
     * component is a Server Component with no state -- so the two behave identically rather than
     * one being a fallback nobody exercises.
     */
    render(<PayfastForm checkout={checkout()} />)

    const button = screen.getByRole('button')

    expect(button).toHaveAttribute('type', 'submit')
    expect(button.closest('form')).toBe(form())
  })

  test('names the amount on the button, read from the field being posted', () => {
    render(<PayfastForm checkout={checkout()} />)

    // Rendered from `fields.amount`, so the figure shown and the figure charged cannot disagree.
    expect(screen.getByRole('button').textContent).toMatch(/150/)
  })

  test('the button is live, because nothing submits the form but the member', () => {
    /*
     * The consent. This screen sets up a recurring debit mandate, so the member presses the button
     * that agrees to it -- an earlier version auto-submitted and put the amount and the recurring
     * terms on screen for a few milliseconds.
     */
    render(<PayfastForm checkout={checkout()} />)

    expect(screen.getByRole('button')).toBeEnabled()
  })

  test('does not submit itself', () => {
    const submit = vi.fn()
    HTMLFormElement.prototype.submit = submit

    render(<PayfastForm checkout={checkout()} />)

    expect(submit).not.toHaveBeenCalled()
  })

  test('states the recurring terms above the button, not below it', () => {
    /*
     * What a member is agreeing to has to be readable before the thing that agrees to it. Same
     * reasoning as the collection notice sitting above the sign-up fields.
     */
    render(<PayfastForm checkout={checkout()} />)

    const terms = screen.getByText(/recurring/i)
    const button = screen.getByRole('button')

    expect(terms.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  test('still labels the button when the amount cannot be read', () => {
    render(
      <PayfastForm checkout={checkout({ fields: { ...FIELDS, amount: 'not-a-number' } })} />,
    )

    expect(screen.getByRole('button').textContent).toBeTruthy()
    expect(screen.getByRole('button').textContent).not.toMatch(/NaN/)
  })

  test('states that the mandate is recurring', () => {
    // On the screen where the member agrees to it, not only in the club documents.
    render(<PayfastForm checkout={checkout()} />)

    expect(screen.getByText(/recurring/i)).toBeInTheDocument()
  })

  test('carries nothing about the member', () => {
    /*
     * The fields are safe in a browser bundle precisely because they hold no personal data — see
     * `gateway.checkout`. This asserts the component adds none either: no name, no address, and in
     * particular not the checkout token that fetched them.
     */
    render(<PayfastForm checkout={checkout()} />)

    const markup = document.body.innerHTML

    for (const value of ['name_first', 'email_address', 'cell_number', 'checkout_token']) {
      expect(markup, value).not.toContain(value)
    }
  })
})

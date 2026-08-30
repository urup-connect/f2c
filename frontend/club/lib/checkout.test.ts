import { describe, expect, test } from 'vitest'
import { readCheckout, readCheckoutToken } from './checkout'

/* design/features/payments.md section 5. */

const FIELDS = {
  merchant_id: '10000100',
  merchant_key: '46f0cd694581a',
  m_payment_id: '01a03412-0000-7000-8000-000000000000',
  amount: '150.00',
  item_name: 'Club membership',
  subscription_type: '1',
  signature: 'd6dc0b1e2d3a4b5c6d7e8f90a1b2c3d4',
}

const body = (overrides: Record<string, unknown> = {}) => ({
  url: 'https://sandbox.payfast.co.za/eng/process',
  fields: FIELDS,
  ...overrides,
})

const TOKEN = 'LxEhFiiwLb8tlAvQ1ACKLQ9dAD117RWhxK3EUpzQABC'

describe('reading a checkout token', () => {
  test('accepts a token of the shape Django mints', () => {
    expect(readCheckoutToken(TOKEN)).toBe(TOKEN)
  })

  test('trims surrounding whitespace, which a copied link brings with it', () => {
    expect(readCheckoutToken(`  ${TOKEN}  `)).toBe(TOKEN)
  })

  test('refuses a token that is too short to be one', () => {
    expect(readCheckoutToken('abc')).toBeNull()
  })

  test('refuses a multi-kilobyte path segment before it reaches the API', () => {
    expect(readCheckoutToken('a'.repeat(5000))).toBeNull()
  })

  test('refuses characters that are not URL-safe base64', () => {
    // A '/' would break the link rather than fail a lookup, which is harder to diagnose.
    expect(readCheckoutToken(`${TOKEN.slice(0, 40)}a/b`)).toBeNull()
  })

  test('refuses a path traversal attempt', () => {
    expect(readCheckoutToken('../../api/auth/me')).toBeNull()
  })

  test('refuses nothing at all', () => {
    expect(readCheckoutToken(undefined)).toBeNull()
    expect(readCheckoutToken(null)).toBeNull()
    expect(readCheckoutToken('')).toBeNull()
  })

  test('refuses a value that is not a string', () => {
    expect(readCheckoutToken(42 as unknown as string)).toBeNull()
  })
})

describe('reading a checkout body', () => {
  test('accepts a complete one', () => {
    const outcome = readCheckout(body())

    expect(outcome).toEqual({
      status: 'ready',
      checkout: { url: 'https://sandbox.payfast.co.za/eng/process', fields: FIELDS },
    })
  })

  test('passes every field through untouched', () => {
    /*
     * The property the whole module exists for. Payfast signs the checkout over exactly the set
     * Django built, so a field this dropped, trimmed or re-cased would make the signature fail —
     * and Payfast answers a failed signature with a generic decline that names nothing.
     */
    const outcome = readCheckout(
      body({ fields: { ...FIELDS, item_name: '  Club membership  ' } }),
    )

    expect(outcome.status).toBe('ready')
    if (outcome.status !== 'ready') return
    expect(outcome.checkout.fields.item_name).toBe('  Club membership  ')
  })

  test('preserves field order, which is what the signature was computed over', () => {
    const outcome = readCheckout(body())

    expect(outcome.status).toBe('ready')
    if (outcome.status !== 'ready') return
    expect(Object.keys(outcome.checkout.fields)).toEqual(Object.keys(FIELDS))
  })

  test('refuses a body that is not an object', () => {
    expect(readCheckout('nope').status).toBe('unusable')
    expect(readCheckout(null).status).toBe('unusable')
    expect(readCheckout([]).status).toBe('unusable')
  })

  test('refuses a body with no payment URL', () => {
    expect(readCheckout(body({ url: '' })).status).toBe('unusable')
    expect(readCheckout(body({ url: undefined })).status).toBe('unusable')
  })

  test('refuses a body with no fields', () => {
    expect(readCheckout(body({ fields: undefined })).status).toBe('unusable')
    expect(readCheckout(body({ fields: 'nope' })).status).toBe('unusable')
  })

  test('refuses an empty field set rather than posting nothing', () => {
    expect(readCheckout(body({ fields: {} })).status).toBe('unusable')
  })

  test('refuses a field that is not a string', () => {
    /*
     * A number here would render as its own text and break the signature. Refusing the body is the
     * difference between an honest failure and Payfast declining for reasons nobody can see.
     */
    expect(readCheckout(body({ fields: { ...FIELDS, amount: 150 } })).status).toBe('unusable')
  })

  test('refuses a field that is null', () => {
    expect(readCheckout(body({ fields: { ...FIELDS, item_name: null } })).status).toBe(
      'unusable',
    )
  })

  test('refuses a field set with no signature', () => {
    // The one missing field whose absence would otherwise be silent.
    const unsigned = Object.fromEntries(
      Object.entries(FIELDS).filter(([name]) => name !== 'signature'),
    )

    expect(readCheckout(body({ fields: unsigned })).status).toBe('unusable')
  })

  test('refuses an empty signature', () => {
    expect(readCheckout(body({ fields: { ...FIELDS, signature: '' } })).status).toBe(
      'unusable',
    )
  })

  test('says why it could not be read, for the log', () => {
    const outcome = readCheckout(body({ url: '' }))

    expect(outcome.status).toBe('unusable')
    if (outcome.status !== 'unusable') return
    expect(outcome.reason).toMatch(/URL/i)
  })
})

import { describe, expect, test } from 'vitest'
import { EMAIL_LOCAL_MAX_LENGTH, EMAIL_MAX_LENGTH, checkEmailAddress } from './email-address'
import type { EmailCheck } from './email-address'

/*
 * A copy of the club's suite, because it is a copy of the club's rule. If the two files ever
 * diverge, one of these tests is what says so.
 *
 * Every address here uses example.com or example.org, which exist for exactly this purpose and
 * belong to nobody.
 *
 * The rule is deliberately conservative rather than a full RFC 5322 grammar. Nothing here proves
 * an address can receive mail; sending to it is the only thing that does, and that check belongs
 * to the emailed sign-in code. This module exists to catch a typo and to fix one stored form.
 */

const accepted = (result: EmailCheck) => (result.status === 'valid' ? result.email : null)
const refusal = (result: EmailCheck) => (result.status === 'invalid' ? result.reason : null)

describe('an address the rule accepts', () => {
  // Criterion 19.
  test.each([
    ['a plain address', 'thandiwe@example.com'],
    ['a subdomain', 'thandiwe@mail.example.com'],
    ['a dot in the local part', 'thandiwe.nkosi@example.com'],
    ['a hyphen in the domain', 'thandiwe@example-club.com'],
    ['a digit in the local part', 'thandiwe7@example.com'],
    ['a longer top-level domain', 'thandiwe@example.africa'],
    ['an underscore in the local part', 'thandiwe_n@example.com'],
  ])('accepts %s', (_label, email) => {
    expect(accepted(checkEmailAddress(email))).toBe(email)
  })

  // Criterion 22.
  test('accepts a plus-address and keeps the suffix', () => {
    expect(accepted(checkEmailAddress('thandiwe+club@example.com'))).toBe(
      'thandiwe+club@example.com',
    )
  })
})

describe('normalisation', () => {
  // Criterion 19.
  test('lower-cases the whole address, so one member has one stored form', () => {
    expect(accepted(checkEmailAddress('Thandiwe.Nkosi@Example.COM'))).toBe(
      'thandiwe.nkosi@example.com',
    )
  })

  test('trims surrounding whitespace rather than refusing it', () => {
    expect(accepted(checkEmailAddress('  thandiwe@example.com  '))).toBe('thandiwe@example.com')
  })
})

describe('an address that is not there', () => {
  test.each([
    ['empty', ''],
    ['whitespace only', '   '],
  ])('refuses %s as missing', (_label, email) => {
    expect(refusal(checkEmailAddress(email))).toBe('missing')
  })
})

describe('an address the rule refuses', () => {
  // Criterion 20.
  test.each([
    ['no at sign', 'thandiwe.example.com'],
    ['two at signs', 'thandiwe@club@example.com'],
    ['no domain', 'thandiwe@'],
    ['no local part', '@example.com'],
    ['no dot in the domain', 'thandiwe@example'],
    ['a leading dot in the local part', '.thandiwe@example.com'],
    ['a trailing dot in the local part', 'thandiwe.@example.com'],
    ['a leading dot in the domain', 'thandiwe@.example.com'],
    ['a trailing dot in the domain', 'thandiwe@example.com.'],
    ['two consecutive dots', 'thandiwe..nkosi@example.com'],
    ['two consecutive dots in the domain', 'thandiwe@example..com'],
    ['a space inside', 'thandiwe nkosi@example.com'],
    ['a comma', 'thandiwe,nkosi@example.com'],
    ['a single-character top-level domain', 'thandiwe@example.c'],
    ['a hyphen starting the domain', 'thandiwe@-example.com'],
  ])('refuses %s', (_label, email) => {
    expect(refusal(checkEmailAddress(email))).toBe('malformed')
  })
})

describe('an address that is too long', () => {
  // Criterion 21.
  test('refuses a local part over the limit', () => {
    const local = 'a'.repeat(EMAIL_LOCAL_MAX_LENGTH + 1)

    expect(refusal(checkEmailAddress(`${local}@example.com`))).toBe('too-long')
  })

  test('accepts a local part at the limit', () => {
    const local = 'a'.repeat(EMAIL_LOCAL_MAX_LENGTH)

    expect(accepted(checkEmailAddress(`${local}@example.com`))).toBe(`${local}@example.com`)
  })

  test('refuses a whole address over the limit', () => {
    // Built from repeated labels so the domain stays syntactically valid while growing past 254.
    const label = 'a'.repeat(60)
    const domain = `${label}.${label}.${label}.${label}.com`
    const email = `thandiwe@${domain}`

    expect(email.length).toBeGreaterThan(EMAIL_MAX_LENGTH)
    expect(refusal(checkEmailAddress(email))).toBe('too-long')
  })

  test('holds the RFC limits', () => {
    expect(EMAIL_LOCAL_MAX_LENGTH).toBe(64)
    expect(EMAIL_MAX_LENGTH).toBe(254)
  })
})

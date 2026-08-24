import { describe, expect, test } from 'vitest'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'
import { PAYMENT_COPY, formatAmount } from './payment-content'

/* design/features/payments.md section 5. */

/**
 * Every string in the copy object, so a sentence added later cannot escape the rules below by
 * being nested one level deeper than the walk went.
 *
 * `submitWithAmount` is a function rather than a string. It is called with a sample amount so its
 * output is held to the same rules as everything else — the amount it interpolates is exactly what
 * the `CURRENCY` exemption is for.
 */
const corpus = (): readonly string[] => {
  const lines: string[] = []

  const walk = (value: unknown) => {
    if (typeof value === 'string') lines.push(value)
    else if (typeof value === 'function') walk((value as (amount: string) => string)('R150.00'))
    else if (Array.isArray(value)) value.forEach(walk)
    else if (value && typeof value === 'object') Object.values(value).forEach(walk)
  }

  walk(PAYMENT_COPY)
  return lines
}

const SCREENS = ['checkout', 'unavailable', 'unusable', 'paid', 'cancelled'] as const

describe('the payment copy', () => {
  test('has a sentence in it', () => {
    // Guards the walk itself: a corpus that silently collected nothing would pass every rule below.
    expect(corpus().length).toBeGreaterThan(10)
  })

  test('makes no clinical claim, payment screen or not', () => {
    /*
     * The one rule with no exemptions anywhere in the product. Being the screen that takes money
     * buys no relief from it.
     */
    for (const line of corpus()) {
      expect(line, line).not.toMatch(CLINICAL_CLAIM)
    }
  })

  test('says nothing about who may join', () => {
    /*
     * It matters more here than elsewhere, not less: this is the screen a member reaches after
     * giving an identity number, and the likeliest place for a reassuring sentence about
     * eligibility to be added. The age check is still the only surface that states any part of it.
     */
    for (const line of corpus()) {
      expect(line, line).not.toMatch(ELIGIBILITY_CLAIM)
    }
  })

  test('takes the currency exemption copy-compliance reserved for it', () => {
    /*
     * Asserted rather than merely not tested. The exemption was written into `copy-compliance.ts`
     * before this screen existed, and this is the screen it was written for — so the test records
     * that the exemption is being used, and where.
     */
    const amounts = corpus().filter((line) => CURRENCY.some((pattern) => pattern.test(line)))

    expect(amounts.length).toBeGreaterThan(0)
  })

  test('does not need the retail-voice exemption, and is held to the rule instead', () => {
    /*
     * `copy-compliance.ts` reserved two exemptions for this screen. Only one turned out to be
     * needed: naming an amount requires the currency exemption, but asking to be paid did not
     * require retail voice — "subscription", "payment" and "Payfast" say it without a shop's
     * vocabulary. So the wider exemption is declined and the rule is enforced here, which is the
     * point of asserting it rather than quietly not testing it.
     */
    for (const line of corpus()) {
      expect(line, line).not.toMatch(RETAIL_VOICE)
    }
  })

  test('never tells a member their membership is active', () => {
    /*
     * The wording decision that runs through all five screens. Until a Payfast notification
     * arrives the account cannot sign in, and the return screen is reached by a redirect the
     * member could replay — so nothing here congratulates anybody on joining.
     */
    for (const line of corpus()) {
      expect(line.toLowerCase(), line).not.toMatch(
        /\b(you are now a member|membership is active|welcome to the club)\b/,
      )
    }
  })

  test('holds no amount of its own', () => {
    /*
     * The figure on screen is formatted from the signed Payfast field set, so it cannot disagree
     * with what is being charged. A price written into the copy is a price that goes stale in a
     * deploy nobody remembers.
     */
    const { checkout, unavailable, unusable, paid, cancelled } = PAYMENT_COPY
    const written = [checkout, unavailable, unusable, paid, cancelled]
      .flatMap((screen) => [screen.heading, ...('body' in screen ? screen.body : [])])
      .join(' ')

    for (const pattern of CURRENCY) {
      expect(written, written).not.toMatch(pattern)
    }
  })

  test('gives every screen a heading and a body', () => {
    // A screen shipped with no wording is a blank card, and it fails here rather than in review.
    for (const screen of SCREENS) {
      expect(PAYMENT_COPY[screen].heading, screen).toBeTruthy()
      expect(PAYMENT_COPY[screen].body.length, screen).toBeGreaterThan(0)
    }
  })

  test('tells a member who cancelled that nothing was charged', () => {
    // The one thing somebody who backed out after typing an identity number needs to read.
    expect(PAYMENT_COPY.cancelled.body.join(' ')).toMatch(/nothing has been charged/i)
  })

  test('tells a member who paid that confirmation is still pending', () => {
    expect(PAYMENT_COPY.paid.body.join(' ')).toMatch(/confirm/i)
  })

  test('names Payfast on the screen that hands over to it', () => {
    // A member about to be redirected to a domain they did not type should read it first.
    expect(PAYMENT_COPY.checkout.body.join(' ')).toContain('Payfast')
  })

  test('says the mandate is recurring, on the screen that sets it up', () => {
    expect(PAYMENT_COPY.checkout.recurring).toMatch(/recurring/i)
    expect(PAYMENT_COPY.checkout.recurring).toMatch(/cancel/i)
  })
})

describe('formatting the amount', () => {
  test('renders rands and cents from the string Payfast is sent', () => {
    // Non-breaking space in the ZAR format, hence the loose match.
    expect(formatAmount('150.00')).toMatch(/^R\s?150,00$|^R\s?150\.00$/)
  })

  test('reads the signed field rather than a number, so the two cannot disagree', () => {
    expect(formatAmount('1250.50')).toMatch(/1\s?250/)
  })

  test('returns null for a missing amount rather than rendering nothing useful', () => {
    expect(formatAmount(undefined)).toBeNull()
    expect(formatAmount('')).toBeNull()
  })

  test('returns null for something that is not a number', () => {
    // "NaN" beside a payment button is worse than no figure; the amount is on Payfast's own page
    // a moment later either way.
    expect(formatAmount('free')).toBeNull()
    expect(formatAmount('Infinity')).toBeNull()
  })
})

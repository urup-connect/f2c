import { describe, expect, test } from 'vitest'
import {
  CHECKOUT_COOKIE,
  CHECKOUT_COOKIE_MAX_AGE_SECONDS,
  checkoutCookieOptions,
  readCheckoutCookie,
} from './checkout-cookie'
import type { SiteConfig } from './site'

/* design/features/payments.md section 5. */

const TOKEN = 'LxEhFiiwLb8tlAvQ1ACKLQ9dAD117RWhxK3EUpzQABC'

const config = (overrides: Partial<SiteConfig> = {}): SiteConfig => ({
  appEnv: 'local',
  siteUrl: 'http://localhost:3000',
  cdnBaseUrl: 'http://localhost:3000/static',
  supportEmail: 'hello@example.invalid',
  isProduction: false,
  ...overrides,
})

describe('the cookie name', () => {
  test('names the hand-off and not what it holds', () => {
    // Cookie names show up in developer tools and logs.
    expect(CHECKOUT_COOKIE).toBe('cc_checkout')
  })
})

describe('the cookie options', () => {
  test('are httpOnly, so page scripts cannot read the token', () => {
    /*
     * The property the whole design rests on: the token is a bearer credential that pays for a
     * membership, and holding it in a cookie is pointless if client JavaScript can read it.
     */
    expect(checkoutCookieOptions(config()).httpOnly).toBe(true)
  })

  test('are lax rather than strict, so the token survives the return from Payfast', () => {
    /*
     * `strict` would withhold the cookie on the cross-site redirect back, so a member who
     * cancelled at Payfast could not be offered the payment again without starting over.
     */
    expect(checkoutCookieOptions(config()).sameSite).toBe('lax')
  })

  test('are scoped to the whole site, because /pay is not under /signup', () => {
    expect(checkoutCookieOptions(config()).path).toBe('/')
  })

  test('follow the scheme the site is served on, not the environment name', () => {
    // `Secure` on a plain-http local server means the browser never sends it back, which looks
    // exactly like a broken payment.
    expect(checkoutCookieOptions(config()).secure).toBe(false)
    expect(checkoutCookieOptions(config({ siteUrl: 'https://app.example.co.za' })).secure).toBe(
      true,
    )
  })

  test('expire, and well before the token does at Django', () => {
    // Half an hour here against a day there: a member who takes longer comes back through the
    // emailed link rather than through a cookie that outlived the screen it was for.
    expect(checkoutCookieOptions(config()).maxAge).toBe(CHECKOUT_COOKIE_MAX_AGE_SECONDS)
    expect(CHECKOUT_COOKIE_MAX_AGE_SECONDS).toBe(30 * 60)
    expect(CHECKOUT_COOKIE_MAX_AGE_SECONDS).toBeLessThan(86_400)
  })
})

describe('reading the cookie', () => {
  test('returns the token it holds', () => {
    expect(readCheckoutCookie(TOKEN)).toBe(TOKEN)
  })

  test('returns null for a missing cookie', () => {
    expect(readCheckoutCookie(undefined)).toBeNull()
  })

  test('returns null for a doctored cookie', () => {
    /*
     * Validated on the way out as well as in, because a cookie is a value the browser sends and
     * therefore one somebody can edit. What decides whether the token is real is Django.
     */
    expect(readCheckoutCookie('../../admin')).toBeNull()
    expect(readCheckoutCookie('short')).toBeNull()
  })
})

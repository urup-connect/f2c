/**
 * The carrier that gets a checkout token from the registration action to the payment screen.
 *
 * The same shape of problem the age gate has, and the same answer. A server action cannot render a
 * page, only redirect, and a redirect carries nothing but a URL — so the token has to travel some
 * other way. A cookie: `httpOnly`, so page scripts cannot read it, short-lived, because it exists
 * to cross one redirect, and re-validated on every read.
 *
 * **The token is deliberately not put in the query string**, even though it would work and is what
 * the emailed fallback link has to do. A URL is written to every access log between the member and
 * this application, kept in browser history, and sent in `Referer` to anything the next page loads.
 * A bearer credential that pays for a membership does not belong in one when there is a cookie
 * available. The emailed link has no such option, which is why that path is the one with the
 * shorter life and the tighter wording — see design/features/payments.md section 5.
 *
 * Unsigned, like the age pass, and for a stronger reason: the token is 32 bytes of entropy that
 * Django looks up. A forged one resolves to nothing. There is no rule here for a signature to
 * protect, only a value for Django to fail to find.
 */

import { readCheckoutToken } from './checkout'
import type { SiteConfig } from './site'

/** Names the hand-off, never what it holds: cookie names show up in developer tools and logs. */
export const CHECKOUT_COOKIE = 'cc_checkout'

/**
 * Thirty minutes. It has one redirect to survive, so this is already generous — and it is
 * deliberately much shorter than the token's own life at Django, which is a day. A member who
 * takes longer than this comes back through the emailed link rather than through a cookie that
 * outlived the screen it was for.
 */
export const CHECKOUT_COOKIE_MAX_AGE_SECONDS = 30 * 60

export type CheckoutCookieOptions = {
  readonly httpOnly: true
  readonly sameSite: 'lax'
  readonly path: '/'
  readonly secure: boolean
  readonly maxAge: number
}

/**
 * `sameSite: 'lax'` rather than `'strict'`, and it matters here.
 *
 * The member leaves for Payfast and comes back on a cross-site redirect. `strict` would withhold
 * the cookie on that return, so a member who cancelled at Payfast and was sent back could not be
 * offered the payment again without starting over.
 *
 * `secure` follows the scheme the site is actually served on rather than the environment name.
 * Marking a cookie `Secure` on a plain-http local server means the browser never sends it back,
 * which looks exactly like a broken payment.
 */
export const checkoutCookieOptions = ({ siteUrl }: SiteConfig): CheckoutCookieOptions => ({
  httpOnly: true,
  sameSite: 'lax',
  path: '/',
  secure: siteUrl.startsWith('https:'),
  maxAge: CHECKOUT_COOKIE_MAX_AGE_SECONDS,
})

/**
 * The token the cookie holds, or `null` for anything that is not one.
 *
 * Validated on the way out as well as on the way in, because a cookie is a value the browser sends
 * and therefore a value somebody can edit. What this refuses is a doctored cookie becoming a
 * request path; what decides whether the token is real is Django.
 */
export const readCheckoutCookie = (value: string | undefined): string | null =>
  readCheckoutToken(value)

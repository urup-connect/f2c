import { cookies } from 'next/headers'
import { CheckoutScreen } from './CheckoutScreen'
import { CHECKOUT_COOKIE, readCheckoutCookie } from '@/lib/checkout-cookie'

/*
 * Payment, reached two ways: straight from a completed sign-up, and from the club's pay-now
 * redirect.
 *
 * **From sign-up**, the token comes from the `httpOnly` cookie the registration action set, not
 * from the URL. That is the whole reason this route exists separately from `/pay/[token]`: a server
 * action can only redirect, a redirect carries only a URL, and a bearer credential that pays for a
 * membership does not belong in one when a cookie is available. See `lib/checkout-cookie.ts`.
 *
 * **From the club**, there is no cookie — the member signed in days later, and the club layout sent
 * them here because their membership is unpaid. Before the split that could not happen, because an
 * unpaid member could not sign in at all; now it is the ordinary path, and the screen falls back to
 * the session-authenticated endpoint. C27, and `lib/club-membership.ts`.
 *
 * The cookie is tried first. A member arriving straight from sign-up has one and it is already
 * minted, so the fallback costs them nothing.
 *
 * No age-gate check here, and that is deliberate rather than an omission. The gate guards the
 * screens that collect information; this one is reached with a token Django issued against a
 * registration that already passed it, and the age rule was applied to the identity document
 * itself at the write. Re-gating here would send a member who has just paid back to a date-of-birth
 * form, and the cookie behind that gate expires in thirty minutes.
 *
 * Reading a cookie already makes this route dynamic, so there is no cache directive here.
 * `cookies()` is what rules out a statically rendered payment page — which would be one member's
 * checkout served to the next.
 */
export default async function Pay() {
  const store = await cookies()
  const token = readCheckoutCookie(store.get(CHECKOUT_COOKIE)?.value)

  return <CheckoutScreen token={token} allowSession={token === null} />
}

import 'server-only'

import { headers } from 'next/headers'

import { apiBaseUrl } from './api'
import { readCheckout, readCheckoutToken } from './checkout'
import type { CheckoutOutcome } from './checkout'

/**
 * Fetches a Payfast checkout from Django, and never throws.
 *
 * Server-side only, and deliberately so, for a different reason than `registration-api.ts`. That
 * module is server-only because it carries an identity number. This one is server-only because the
 * *token* must not reach a browser bundle: it is the bearer credential that pays for a membership,
 * and the whole point of holding it in an `httpOnly` cookie is undone the moment client JavaScript
 * can read it. The fields it returns are safe in the page — they carry nothing about the member,
 * by design (see `gateway.checkout`) — but the token that fetched them is not.
 *
 * No cookies are forwarded. There is no session: a member at Pending payment cannot sign in, which
 * is the reason the endpoint is unauthenticated in the first place.
 *
 * **Fails closed, and distinguishes the two kinds of failure**, because they are different screens.
 * A token that names nothing payable is the member's problem to solve by getting a fresh link. An
 * unreachable API is ours, and saying "your link has expired" for our own outage would send them
 * chasing a link that was never the problem.
 *
 * A 200 whose body does not parse is unusable rather than believed. Rendering a half-read field set
 * would POST an incomplete checkout to Payfast, which declines it generically — so the member is
 * told the club could not start the payment, which is true, instead of being handed a form that
 * cannot work.
 *
 * See design/features/payments.md section 5.
 */
export const fetchCheckout = async (token: string): Promise<CheckoutOutcome> => {
  /*
   * Validated again here rather than trusted from the caller. Both callers check — the cookie
   * reader and the emailed-link route — and this is the one place every path goes through, so it is
   * the place that keeps a doctored value out of a request path.
   */
  const safe = readCheckoutToken(token)
  if (!safe) return { status: 'unavailable' }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}/api/payments/checkout/${safe}`, {
      /*
       * Never cached. A checkout is a bearer-credential lookup whose answer stops being valid the
       * moment the subscription is paid, and a cached one would keep offering a payment that has
       * already been made. Stated rather than left to a default, because the default for a GET is
       * the wrong one here.
       */
      cache: 'no-store',
    })
  } catch {
    return { status: 'unusable', reason: 'Checkout failed: the API is unreachable.' }
  }

  if (response.status === 404) return { status: 'unavailable' }

  if (response.status === 429) {
    return {
      status: 'unusable',
      reason: 'Checkout was rate limited. Too many attempts from this address.',
    }
  }

  if (!response.ok) {
    return {
      status: 'unusable',
      reason: `Checkout answered with status ${response.status}.`,
    }
  }

  let body: unknown

  try {
    body = await response.json()
  } catch {
    return { status: 'unusable', reason: 'Checkout answered with a body that is not JSON.' }
  }

  return readCheckout(body)
}

/**
 * The signed-in member's outstanding checkout, fetched with their session.
 *
 * **The other half of the pay-now redirect.** `fetchCheckout` above needs a token, and the token
 * arrives in an `httpOnly` cookie that the registration action sets — which a member who signs in a
 * week later does not have. Sending them to `/pay` without this would show them "your payment link
 * is unavailable", which is a dead end wearing a helpful message. See `lib/club-membership.ts`.
 *
 * Cookies **are** forwarded here, unlike above, and that is the whole difference between the two:
 * this endpoint authenticates the caller instead of taking a bearer token, so there is no
 * credential in a URL and nothing to keep out of the bundle. Still server-only, because forwarding
 * a session cookie from a browser bundle is not a thing that can be done.
 *
 * **409 is not a fault.** It is Django saying this membership is not one a payment settles — one
 * awaiting the club's verification, or already paid up. `clubGateFor` should have caught both
 * before anybody got here, so a 409 means the two disagreed; it is reported as unavailable rather
 * than as an outage, because the member cannot act on it either way and an error reference would
 * send them to support over a race.
 */
export const fetchMyCheckout = async (): Promise<CheckoutOutcome> => {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}/api/payments/me/checkout`, {
      headers: { cookie: (await headers()).get('cookie') ?? '' },
      // Never cached, for the reason `fetchCheckout` gives, and one more: this
      // answer is per member, and a cached one would be somebody else's.
      cache: 'no-store',
    })
  } catch {
    return { status: 'unusable', reason: 'Checkout failed: the API is unreachable.' }
  }

  // 401 cannot happen behind the club gate, and is handled rather than assumed away: a session that
  // expired between the redirect and this fetch is a member with nothing to pay for right now.
  if (response.status === 401 || response.status === 409) return { status: 'unavailable' }

  if (!response.ok) {
    return {
      status: 'unusable',
      reason: `Checkout answered with status ${response.status}.`,
    }
  }

  let body: unknown

  try {
    body = await response.json()
  } catch {
    return { status: 'unusable', reason: 'Checkout answered with a body that is not JSON.' }
  }

  return readCheckout(body)
}

import 'server-only'

import { cache } from 'react'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

import { PATHNAME_HEADER } from '@/proxy'
import type { Passkey, User } from './api'
import { getCurrentUser, getPasskeys } from './server-api'
import { signInPath } from './sign-in'

/**
 * The guard in front of every signed-in screen.
 *
 * **Where the guard is, and where it is not.** It is here, in a Server Component, because this is
 * the only place that can ask Django whether the session cookie is real. It is deliberately *not*
 * in `proxy.ts`: a proxy sees a cookie, not a session, so the only thing it could check is whether
 * a string is present — and a guard that admits anyone holding an expired, forged or signed-out
 * cookie is not a guard, it is a redirect that looks like one. The account layout asks the API,
 * every time, uncached.
 *
 * It is also not the last line of defence. Every endpoint authorises its own caller; nothing on a
 * screen decides anything. This exists so a customer is sent somewhere useful rather than shown an
 * area full of refusals.
 *
 * **There is one gate here, where the club has two, and that is the whole point of the identity
 * split.** The club asks whether this is anybody *and* whether the club is open to them — a member
 * who has not paid is sent to a payment screen. A store customer has nothing to pay for and no
 * membership to be behind on: an account that can hold a session can shop. `design/verticals.md`
 * section 6, and C27.
 */

/**
 * The session, read once per request no matter how many callers ask.
 *
 * `cache` is React's request-scoped memo: the account layout needs the account to draw the header
 * and each page needs it too, and without this that is two round trips to `/api/auth/me` for one
 * page. The memo lives for one render pass, so nothing is shared between requests or between
 * customers.
 */
export const currentUser = cache(getCurrentUser)

/**
 * The path being rendered, as `proxy.ts` recorded it on the way in.
 *
 * A layout is not told which route it wraps, which is normally right — a layout is meant to be
 * reusable — but this one has to send a visitor back to where they were headed. `null` when the
 * header is absent, which is what a unit test or a route outside the proxy's matcher looks like;
 * the caller then simply has no `next` to offer.
 */
export const requestedPath = async (): Promise<string | null> =>
  (await headers()).get(PATHNAME_HEADER)

/**
 * The signed-in account, or a redirect to sign-in carrying where they were going.
 *
 * Returns `User` rather than `User | null`, so a caller cannot forget the null branch: everything
 * after this line has an account.
 */
export const requireSession = async (): Promise<User> => {
  const user = await currentUser()
  if (user === null) redirect(signInPath(await requestedPath()))
  return user
}

/** The account's passkeys, and whether the list could be read at all. */
export type PasskeysResult = {
  readonly passkeys: readonly Passkey[]
  /** True when Django could not be asked. The card then says so rather than saying zero. */
  readonly unavailable: boolean
}

/**
 * The passkeys on this account, read on the server so the list is in the first paint.
 *
 * **Never throws.** `getPasskeys` swallows a 401 and returns an empty list, which cannot happen past
 * the guard, but it rethrows everything else — and an unreachable API taking down a whole screen
 * would be a poor trade for one card. A failure resolves to "unavailable" instead, so the card says
 * the list could not be read rather than claiming there are none. The difference matters: somebody
 * told they have no passkeys will go and enrol another one.
 */
export const readPasskeys = async (): Promise<PasskeysResult> => {
  try {
    return { passkeys: await getPasskeys(), unavailable: false }
  } catch {
    return { passkeys: [], unavailable: true }
  }
}

/**
 * The name to greet somebody by, or `null` when there is nothing to use.
 *
 * `first_name` rather than the club's nickname, and that is not a shortcut: a store customer has a
 * name and needs no pseudonym, so the nickname is a club membership field and arrives blank here.
 * `null` rather than an empty string, so the greeting is omitted rather than rendered with a gap —
 * "Welcome back," with nothing after the comma reads as a page that failed to draw.
 */
export const greetingName = (user: Pick<User, 'first_name' | 'display_name'>): string | null => {
  const first = user.first_name.trim()
  if (first.length > 0) return first

  const display = user.display_name.trim()
  return display.length > 0 ? display : null
}

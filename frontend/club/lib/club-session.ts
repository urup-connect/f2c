import 'server-only'

import { cache } from 'react'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

import { PATHNAME_HEADER } from '@/proxy'
import type { Passkey, User } from './api'
import { clubGateFor } from './club-membership'
import type { ClubRole } from './club-roles'
import { clubHomeFor } from './club-roles'
import { getCurrentUser, getPasskeys } from './server-api'
import { signInPath } from './sign-in'

/**
 * The guard in front of every signed-in screen.
 *
 * **Where the guard is, and where it is not.** It is here, in a Server Component, because this is
 * the only place that can ask Django whether the session cookie is real. It is deliberately *not*
 * in `proxy.ts`: a proxy sees a cookie, not a session, so the only thing it could check is whether
 * a string is present — and a guard that admits anyone holding an expired, forged or signed-out
 * cookie is not a guard, it is a redirect that looks like one. The club layout asks the API, every
 * time, uncached.
 *
 * It is also not the last line of defence. Every endpoint authorises its own caller; nothing on a
 * screen decides anything. This exists so a member is sent somewhere useful rather than shown an
 * area full of refusals.
 */

/**
 * The session, read once per request no matter how many callers ask.
 *
 * `cache` is React's request-scoped memo: the club layout needs the account to draw the header and
 * each home page needs it to check the role, and without this that is two round trips to
 * `/api/auth/me` for one page. The memo lives for one render pass, so nothing is shared between
 * requests or between members.
 */
export const currentUser = cache(getCurrentUser)

/**
 * The path being rendered, as `proxy.ts` recorded it on the way in.
 *
 * A layout is not told which route it wraps, which is normally right — a layout is meant to be
 * reusable — but the club layout has to send a visitor back to where they were headed. `null` when
 * the header is absent, which is what a unit test or a route outside the proxy's matcher looks
 * like; the caller then simply has no `next` to offer.
 */
export const requestedPath = async (): Promise<string | null> =>
  (await headers()).get(PATHNAME_HEADER)

/**
 * The signed-in account, or a redirect to sign-in carrying where they were going.
 *
 * Returns `User` rather than `User | null`, so a caller cannot forget the null branch: everything
 * after this line has an account.
 *
 * **Says nothing about membership.** Signing in and belonging to the club are separate questions
 * now — see `requireClubMembership` below — and the screens outside the club group that a signed-in
 * non-member legitimately reaches, the payment screen first among them, go through this one.
 */
export const requireSession = async (): Promise<User> => {
  const user = await currentUser()
  if (user === null) redirect(signInPath(await requestedPath()))
  return user
}

/**
 * The signed-in account, having established the club is open to it.
 *
 * **The pay-now gate.** A member who has not paid signs in perfectly well and is sent here to the
 * payment screen; before the split Django refused the sign-in itself, and the only way back was an
 * emailed link. That could not survive a second storefront — a produce customer has no club
 * membership to pay for — so the account became an identity and the club gate came here. C27, and
 * `design/verticals.md` section 5.
 *
 * The rule itself is in `clubGateFor`, deliberately: it is pure, it is unit-tested, and the case
 * worth getting right is not "unpaid goes to /pay" but the one next to it — a membership blocked
 * for a reason money does not settle must **not** be sent to a checkout.
 *
 * Called by the club layout, so every screen in the group is behind it. A page that needs the
 * account but not the membership should call `requireSession`.
 */
export const requireClubMembership = async (): Promise<User> => {
  const user = await requireSession()
  const gate = clubGateFor(user)
  if (!gate.allow) redirect(gate.redirectTo)
  return user
}

/**
 * The signed-in account, having established it belongs on this page.
 *
 * A member who arrives at `/admin` is sent to `/member` rather than refused. Nothing was
 * exposed — the page had not rendered — and a redirect to somewhere they can use beats an error
 * page saying they took a wrong turn.
 *
 * An account with no home at all is signed out of the club entirely: that is a sharing member,
 * which cannot hold a session, and the front door is the only honest destination.
 */
export const requireRole = async (role: ClubRole): Promise<User> => {
  const user = await requireClubMembership()
  if (user.role !== role) redirect(clubHomeFor(user.role) ?? '/')
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
 * **Never throws.** `getPasskeys` swallows a 401 and returns an empty list, which cannot happen
 * past the guard, but it rethrows everything else — and an unreachable API taking down a member's
 * whole home page would be a poor trade for one card. A failure resolves to "unavailable" instead,
 * so the card says the list could not be read rather than claiming there are none. The difference
 * matters: a member told they have no passkeys will go and enrol another one.
 */
export const readPasskeys = async (): Promise<PasskeysResult> => {
  try {
    return { passkeys: await getPasskeys(), unavailable: false }
  } catch {
    return { passkeys: [], unavailable: true }
  }
}

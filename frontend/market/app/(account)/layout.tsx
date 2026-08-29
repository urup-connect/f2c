import type { ReactNode } from 'react'

import { StoreHeader } from '@/components/Account/StoreHeader'
import { navigable } from '@/lib/navigation'
import { greetingName, requireSession } from '@/lib/session'
import { STORE_SHELL } from '@/lib/store-content'

/**
 * The frame every signed-in screen sits in, and the gate in front of all of them.
 *
 * A route group, so it shapes the layout without appearing in the URL: the screens stay at /account and
 * below.
 *
 * **The session check is here and nowhere earlier.** `proxy.ts` runs before this and could see the
 * cookie, but seeing a cookie is not the same as having a session — an expired, forged or signed-out
 * cookie is still a string, and a gate that admits anyone holding one is a redirect dressed as a guard.
 * This asks Django, on every request, uncached.
 *
 * **One gate, where the club has two.** The club also asks whether the club is open to this member —
 * an unpaid membership is sent to a payment screen. A store customer has nothing to pay for: an
 * account that can hold a session can shop. That is the identity split earning its keep rather than a
 * check left out; `lib/session.ts` and `design/verticals.md` section 6.
 *
 * It is not the last line of defence either: every endpoint authorises its own caller. This exists so a
 * customer is sent somewhere useful instead of being shown an area full of refusals.
 *
 * No `robots` field. These screens inherit `noindex, nofollow` from the root layout, which is the
 * default-deny every signed-in screen relies on.
 */
export default async function AccountLayout({ children }: { children: ReactNode }) {
  const user = await requireSession()

  return (
    <>
      <a
        href="#account-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-control focus:bg-surface focus:px-4 focus:py-2 focus:font-sans focus:text-leaf"
      >
        {STORE_SHELL.skipToContent}
      </a>

      <StoreHeader displayName={greetingName(user)} navigable={navigable()} />

      <main id="account-content" className="flex flex-1 flex-col">
        {children}
      </main>
    </>
  )
}

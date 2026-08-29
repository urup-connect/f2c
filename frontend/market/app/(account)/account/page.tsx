import type { Metadata } from 'next'

import { DestinationTile } from '@/components/Account/DestinationTile'
import { ACCOUNT_MENU } from '@/lib/navigation'
import { greetingName, requireSession } from '@/lib/session'
import { ACCOUNT_HOME } from '@/lib/store-content'

export const metadata: Metadata = {
  title: ACCOUNT_HOME.title,
}

/**
 * The signed-in home.
 *
 * **One home, where the club has three.** The club routes a member, a cultivator and an administrator
 * to different pages because they are different people doing different things. Every store customer is
 * the same kind of customer, and a farm selling into the store is a `Producer` with an area of its own
 * that is not built — so there is nothing here for a role to choose between.
 *
 * The tiles render `ACCOUNT_MENU` whole, planned entries included. Somebody who created an account
 * expecting to buy something is better served by a tile saying orders are coming than by a page with
 * two links and no mention of them.
 *
 * `requireSession` again, even though the layout has already run it: the memo in `lib/session.ts` makes
 * that one round trip rather than two, and a page that reads the account without asking for it would be
 * a page whose guard is somebody else's business.
 */
export default async function AccountHome() {
  const user = await requireSession()
  const name = greetingName(user)

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-6 py-12">
      <div className="flex flex-col gap-3">
        <h1 className="font-display text-3xl tracking-display text-leaf">
          {name === null
            ? ACCOUNT_HOME.greetingFallback
            : `${ACCOUNT_HOME.greetingPrefix} ${name}`}
        </h1>
        <p className="max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
          {ACCOUNT_HOME.standfirst}
        </p>
      </div>

      <ul className="grid list-none gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ACCOUNT_MENU.map((destination) => (
          <li key={destination.key}>
            <DestinationTile destination={destination} />
          </li>
        ))}
      </ul>
    </div>
  )
}

import Link from 'next/link'

import { Wordmark } from '@/components/Brand/Wordmark'
import { ACCOUNT_PATH, type AccountDestination } from '@/lib/navigation'
import { STORE_SHELL } from '@/lib/store-content'
import { SignOutButton } from './SignOutButton'

type StoreHeaderProps = {
  /** Whatever should appear on screen for this account. `null` when there is nothing to use. */
  displayName: string | null
  /** Only destinations that can actually be navigated to. */
  navigable: readonly AccountDestination[]
}

/**
 * The bar across the top of every signed-in screen.
 *
 * Leaf green, which is what separates the signed-in store from the paper-white public one at a
 * glance — somebody should be able to tell whether they are signed in without reading anything. The
 * club does the same with forest green, and the two greens are far enough apart to tell the
 * storefronts apart too.
 *
 * **The nav renders nothing rather than an empty landmark** when there is nowhere to go. A landmark
 * containing nothing is a landmark a screen-reader user is invited into for no reason. It cannot
 * happen today — details and security are both built — and the branch stays because the condition is
 * what makes `navigable()` the single source of what works.
 */
export const StoreHeader = ({ displayName, navigable }: StoreHeaderProps) => (
  <header className="bg-leaf">
    <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-6 py-4">
      <Link
        href={ACCOUNT_PATH}
        aria-label={STORE_SHELL.homeLabel}
        className="flex items-center gap-3 rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-paper"
      >
        <Wordmark ground="leaf" />
      </Link>

      {navigable.length > 0 ? (
        <nav aria-label={STORE_SHELL.navLabel} className="flex-1">
          <ul className="flex list-none flex-wrap items-center gap-4">
            {navigable.map((destination) => (
              <li key={destination.key}>
                <Link
                  href={destination.href as string}
                  className="font-sans text-sm text-leaf-pale underline-offset-4 hover:text-paper hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-paper"
                >
                  {destination.title}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : (
        <div className="flex-1" />
      )}

      <div className="flex items-center gap-4">
        {displayName ? (
          <p className="font-sans text-sm text-leaf-pale">{displayName}</p>
        ) : null}

        <SignOutButton />
      </div>
    </div>
  </header>
)

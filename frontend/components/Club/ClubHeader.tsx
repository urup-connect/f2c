import Link from 'next/link'
import { Logo } from '@/components/Brand/Logo'
import { CLUB_SHELL } from '@/lib/club-content'
import type { ClubDestination } from '@/lib/club-navigation'
import { SignOutButton } from './SignOutButton'

type ClubHeaderProps = {
  /** Whatever should appear on screen for this account. Blank for an erased one. */
  displayName: string | null
  /** Where this account's own home is, so the badge goes somewhere useful. */
  homeHref: string
  /** Only destinations that can actually be navigated to. Empty is expected today. */
  navigable: readonly ClubDestination[]
}

/**
 * The bar across the top of every signed-in screen.
 *
 * Forest green, which is what separates the club from the cream public product at a glance — a
 * member should be able to tell whether they are signed in without reading anything.
 *
 * **The nav renders nothing while there is nowhere to go.** Not an empty `nav` element, and not a
 * row of disabled links: `navigableFor` returns only destinations with a real `href`, and today
 * that is none of them. A landmark containing nothing is a landmark a screen-reader user is invited
 * into for no reason. What the account may eventually do is on the page itself, in tiles that say
 * so. The bar starts carrying links on its own the day the first destination gains one.
 */
export const ClubHeader = ({ displayName, homeHref, navigable }: ClubHeaderProps) => (
  <header className="bg-forest-green">
    <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
      <Link
        href={homeHref}
        aria-label={CLUB_SHELL.homeLabel}
        className="flex items-center gap-3 rounded-control focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cream-warm"
      >
        <Logo variant="onForestGreen" width={44} loading="eager" className="rounded-control" />
      </Link>

      {navigable.length > 0 ? (
        <nav aria-label={CLUB_SHELL.navLabel} className="flex-1">
          <ul className="flex list-none flex-wrap items-center gap-4">
            {navigable.map((destination) => (
              <li key={destination.key}>
                <Link
                  href={destination.href as string}
                  className="font-sans text-sm text-sage-green underline-offset-4 hover:text-cream-warm hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cream-warm"
                >
                  {destination.label}
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
          <p className="font-sans text-sm text-sage-green">{displayName}</p>
        ) : null}

        <SignOutButton />
      </div>
    </div>
  </header>
)

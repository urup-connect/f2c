import type { ReactNode } from 'react'

import { ClubBreadcrumbs } from '@/components/Club/ClubBreadcrumbs'
import { ClubHeader } from '@/components/Club/ClubHeader'
import { greetingName } from '@/lib/club-account'
import { CLUB_HOMES_COPY, CLUB_SHELL } from '@/lib/club-content'
import { navigableFor } from '@/lib/club-navigation'
import { clubHomeFor, isClubRole } from '@/lib/club-roles'
import { requireSession } from '@/lib/club-session'

/**
 * The frame every signed-in screen sits in, and the gate in front of all of them.
 *
 * A route group, so it shapes the layout without appearing in the URL: the screens stay at
 * /member, /cultivator and /admin.
 *
 * **The session check is here and nowhere earlier.** `proxy.ts` runs before this and could see the
 * cookie, but seeing a cookie is not the same as having a session — an expired, forged or
 * signed-out cookie is still a string, and a gate that admits anyone holding one is a redirect
 * dressed as a guard. This asks Django, on every request, uncached. The pages beneath then check
 * only the role, reading the same answer through a request-scoped memo rather than asking twice.
 *
 * It is not the last line of defence either: every endpoint authorises its own caller. This exists
 * so a member is sent somewhere useful instead of being shown an area full of refusals.
 *
 * No `robots` field. These screens inherit `noindex, nofollow` from the root layout, which is the
 * default-deny the design relies on.
 */
export default async function ClubLayout({ children }: { children: ReactNode }) {
  const user = await requireSession()

  /*
   * Where the trail starts, and what it calls that place.
   *
   * The home each role lands on already has a name it uses for itself — "Club administration",
   * "Your cultivation" — so the first crumb borrows it rather than inventing a generic word for
   * three different places. An account with no club role has no home to name either, and falls back
   * to the club's own name pointing at the front door, which is exactly where `clubHomeFor` sends
   * it.
   */
  const home = {
    href: clubHomeFor(user.role) ?? '/',
    label: isClubRole(user.role) ? CLUB_HOMES_COPY[user.role].title : CLUB_SHELL.homeLabel,
  }

  return (
    <>
      <a
        href="#club-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-control focus:bg-surface focus:px-4 focus:py-2 focus:font-sans focus:text-forest-green"
      >
        {CLUB_SHELL.skipToContent}
      </a>

      <ClubHeader
        displayName={greetingName(user)}
        homeHref={home.href}
        navigable={navigableFor(user.permissions)}
      />

      <ClubBreadcrumbs home={home} />

      <main id="club-content" className="flex flex-1 flex-col">
        {children}
      </main>
    </>
  )
}

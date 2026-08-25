import type { Metadata } from 'next'

import { ClubHome } from '@/components/Club/ClubHome'
import { CLUB_HOMES_COPY } from '@/lib/club-content'
import { readPasskeys, requireRole } from '@/lib/club-session'

export const metadata: Metadata = {
  title: CLUB_HOMES_COPY.cultivator.title,
}

/**
 * A cultivator's home.
 *
 * A route of its own rather than a branch inside one shared page. The three areas answer to
 * different people and will diverge — a cultivator's screens are about stock, listings and the
 * register, and none of that is a variation on a member's plants. Giving each its own route means
 * the divergence arrives as new files rather than as a switch statement growing in the middle of
 * an existing one.
 *
 * `role` is appointed by hand in the Django admin, never claimed on a form. See
 * design/features/roles-and-permissions.md section 2.
 */
export default async function CultivatorHome() {
  const user = await requireRole('cultivator')
  const { passkeys, unavailable } = await readPasskeys()

  return (
    <ClubHome
      role="cultivator"
      user={user}
      passkeys={passkeys}
      passkeysUnavailable={unavailable}
    />
  )
}

import type { Metadata } from 'next'

import { ClubHome } from '@/components/Club/ClubHome'
import { CLUB_HOMES_COPY } from '@/lib/club-content'
import { readPasskeys, requireRole } from '@/lib/club-session'

export const metadata: Metadata = {
  title: CLUB_HOMES_COPY.member.title,
}

/**
 * A member's home.
 *
 * `requireRole` does two things and both are redirects rather than errors: no session goes to
 * /login carrying where it was headed, and the wrong role goes to its own home. Nothing had
 * rendered in either case, so nothing was exposed — and a member who typed /admin is better served
 * by arriving somewhere they can use than by an error page telling them off.
 *
 * The session is read twice on this request, here and in the layout, and fetched once: both go
 * through the request-scoped memo in `club-session`.
 */
export default async function MemberHome() {
  const user = await requireRole('member')
  const { passkeys, unavailable } = await readPasskeys()

  return (
    <ClubHome
      role="member"
      user={user}
      passkeys={passkeys}
      passkeysUnavailable={unavailable}
    />
  )
}

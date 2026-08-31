import { redirect } from 'next/navigation'

import { BlockedNotice } from '@/components/Blocked/BlockedNotice'
import { AuthCard } from '@/components/Ui/AuthCard'
import { BLOCKED_COPY, isBlockedReason } from '@/lib/blocked-content'
import { clubGateFor, FRONT_DOOR } from '@/lib/club-membership'
import { requireSession } from '@/lib/club-session'
import { clubHomeFor } from '@/lib/club-roles'
import { SITE_CONFIG } from '@/lib/site'

/*
 * Where a member goes when the club is closed to them and money is not the reason.
 *
 * **It derives its own reason rather than being told one.** The club layout redirects here, and a
 * redirect carries only a URL — so the obvious design is `?reason=blocked`. This asks
 * `clubGateFor` again instead, for two reasons. A query parameter is typed by anybody, so the
 * screen would render whichever situation a visitor asked for; and it would put the rule in two
 * places, which is the thing `lib/club-membership.ts` exists to prevent.
 *
 * `requireSession`, not `requireClubMembership`. The membership guard redirects here, so calling it
 * from this page would be a redirect loop.
 *
 * **An account the gate now admits is sent on rather than shown a stale refusal.** A member
 * reinstated while this tab sat open, or one who followed a link somebody sent them, gets their own
 * home. The gate is asked live on every request, so it is the same answer the layout would give.
 */
export default async function Blocked() {
  const user = await requireSession()
  const gate = clubGateFor(user)

  if (gate.allow) redirect(clubHomeFor(user.role) ?? FRONT_DOOR)

  /*
   * `owes-payment` and `not-a-member` have destinations of their own, and a member who reaches this
   * URL directly in either state is sent to the one that can actually help them. Only the reasons
   * the copy module has wording for are rendered here — `isBlockedReason` is what makes that a
   * type-level fact rather than a lookup that might return undefined.
   */
  if (!isBlockedReason(gate.reason)) redirect(gate.redirectTo)

  return (
    <AuthCard>
      <BlockedNotice
        notice={BLOCKED_COPY[gate.reason]}
        supportEmail={SITE_CONFIG.supportEmail}
      />
    </AuthCard>
  )
}

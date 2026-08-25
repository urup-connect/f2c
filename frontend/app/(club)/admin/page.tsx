import type { Metadata } from 'next'

import { ClubHome } from '@/components/Club/ClubHome'
import { CLUB_HOMES_COPY } from '@/lib/club-content'
import { readPasskeys, requireRole } from '@/lib/club-session'

export const metadata: Metadata = {
  title: CLUB_HOMES_COPY.admin.title,
}

/**
 * An administrator's home.
 *
 * **Self-contained: nothing here links to the Django admin.** That is a decision rather than an
 * omission, and it has a cost worth stating. Django admin opens on `is_staff`, which is a
 * *different fact* from `role` — the two are independent by design (roles doc section 9), so an
 * administrator without `is_staff` would follow such a link into a refusal, and a member of staff
 * without the role would find one that worked. A branded club screen that answers to the role and
 * to nothing else has no such disagreement to make.
 *
 * The cost is that the administration screens themselves do not exist yet: `manage_cultivators`,
 * `manage_strain_catalogue`, `manage_product_types`, `manage_club_rules`, `disable_user`,
 * `revoke_access`, `cancel_membership`, `hide_cultivator` and `refund_transaction` are nine
 * destinations with no API endpoint behind any of them. They are shown as planned, which is honest,
 * and until they are built the Django admin at /admin/ on the API host remains where records are
 * actually managed — by hand, by somebody holding `is_staff`.
 */
export default async function AdminHome() {
  const user = await requireRole('admin')
  const { passkeys, unavailable } = await readPasskeys()

  return (
    <ClubHome
      role="admin"
      user={user}
      passkeys={passkeys}
      passkeysUnavailable={unavailable}
    />
  )
}

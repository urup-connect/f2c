import type { Metadata } from 'next'

import { MemberRegisterScreen } from '@/components/Admin/MemberRegisterScreen'
import { requireRole } from '@/lib/club-session'
import { memberPath } from '@/lib/member-register-routes'
import { MEMBER_REGISTER } from '@/lib/member-register-content'
import { getMembers } from '@/lib/server-api'

export const metadata: Metadata = {
  title: MEMBER_REGISTER.heading,
}

/**
 * The membership register: every account the club holds.
 *
 * Read on the server so the whole table is in the first paint. It matters here
 * more than on the catalogue: a register is a screen an administrator scans and
 * searches, and one that arrives empty and fills in a moment later is a screen
 * they will have typed a search into before the rows land underneath them.
 *
 * ## A failed read renders the screen, and says so
 *
 * Unlike `/admin/strains`, which folds a null to `notFound()`. The two are
 * different situations: a null there is one strain that is not there, and a null
 * here is the whole register being unreadable — which is not "there is nothing
 * at this address", it is "the club could not be asked". The screen draws with
 * no rows and an alert saying the read failed, because an administrator who is
 * shown a 404 will go looking for a routing problem.
 *
 * The exception is a caller who may not manage the membership at all. That also
 * arrives as null — `getMembers` folds 401 and 403 together — and is
 * indistinguishable here from an outage. It cannot happen in practice: the guard
 * above has already established the administrator role, and
 * `platform.disable_user` is held by exactly that role. If the two ever diverge,
 * an administrator without the permission sees an empty register that says it
 * could not be read, which is true.
 */
export default async function MembersPage() {
  await requireRole('admin')

  const members = await getMembers()

  return (
    <MemberRegisterScreen
      initial={members ?? []}
      unavailable={members === null}
      memberHref={memberPath}
    />
  )
}

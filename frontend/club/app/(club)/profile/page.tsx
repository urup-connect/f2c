import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { ProfileScreen } from '@/components/Profile/ProfileScreen'
import { PROFILE_COPY } from '@/lib/club-content'
import { requireSession } from '@/lib/club-session'
import { getProfile } from '@/lib/server-api'

export const metadata: Metadata = {
  title: PROFILE_COPY.title,
}

/**
 * A member's own profile.
 *
 * **One route for all three roles, and guarded by `requireSession` rather than `requireRole`.** That
 * is the opposite of the three home pages, and the difference is real: `/member`, `/cultivator` and
 * `/admin` answer to different people and are expected to diverge, whereas everybody has exactly one
 * profile and it is the same screen. Splitting it three ways would be three near-identical files
 * with no divergence in prospect — and the moment an administrator's profile did need something
 * extra, the honest change is a card that renders on a permission, not a fourth copy of the page.
 *
 * A cultivator's *public* profile is a different thing entirely and is not this: it is
 * `manage_own_cultivator_profile` in the permission catalogue, it is what members see of them, and
 * it has a destination tile of its own that is not built. This screen is the record the club holds
 * about a person, which no other member ever sees.
 *
 * `notFound()` for a session that has no profile. It cannot happen — `requireSession` has already
 * established the account exists, and the same cookie fetched both — so this is the branch that
 * stops a `null` reaching the component rather than a state anybody meets. A 404 rather than an
 * error page: if the API genuinely has no record for this session, there is nothing at this address.
 *
 * No `robots` field. This inherits `noindex, nofollow` from the root layout, which is the
 * default-deny every signed-in screen relies on.
 */
export default async function ProfilePage() {
  await requireSession()

  const profile = await getProfile()
  if (profile === null) notFound()

  return <ProfileScreen initial={profile} />
}

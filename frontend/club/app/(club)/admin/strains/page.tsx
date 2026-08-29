import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { CatalogueScreen } from '@/components/Admin/CatalogueScreen'
import { NEW_STRAIN_PATH, TERMS_PATH } from '@/lib/catalogue-routes'
import { requireRole } from '@/lib/club-session'
import { getStrains } from '@/lib/server-api'
import { CATALOGUE_LIST } from '@/lib/strain-catalogue-content'

export const metadata: Metadata = {
  title: CATALOGUE_LIST.title,
}

/**
 * The strain catalogue, as an administrator manages it.
 *
 * The first destination in the `administration` band to gain an `href`, and the
 * second in the whole of `club-navigation.ts` — the first was `own-profile`.
 * Nothing else in that file moved, which is the shape working as designed.
 *
 * ## Two guards, doing two different jobs
 *
 * `requireRole('admin')` sends anybody else to their own home. That is a
 * courtesy, not a security boundary: a member who lands here is redirected
 * somewhere useful instead of being shown an area full of refusals, and the
 * endpoints authorise their own callers regardless.
 *
 * `notFound()` on a null read is the second, and it catches the case the role
 * check cannot: `role` and `platform.manage_strain_catalogue` are not the same
 * fact. The permission comes from `roles.permissions_for`, which empties the set
 * for an account that cannot sign in — so a suspended administrator holds the
 * role and not the permission. The API answers 403, `getStrains` folds that to
 * null, and this is where it becomes a 404. A 404 rather than an error page: if
 * this account may not manage the catalogue, there is nothing at this address for
 * them.
 *
 * The `unavailable` flag is deliberately not set from that branch. A null here is
 * a refusal, not an unreachable API, and the two must not be conflated — an
 * administrator told "the catalogue could not be read" would reload the page
 * forever.
 *
 * No `robots` field. This inherits `noindex, nofollow` from the root layout,
 * which is the default-deny every signed-in screen relies on.
 */
export default async function StrainCataloguePage() {
  await requireRole('admin')

  const strains = await getStrains()
  if (strains === null) notFound()

  return (
    <CatalogueScreen
      initial={strains}
      addHref={NEW_STRAIN_PATH}
      termsHref={TERMS_PATH}
    />
  )
}

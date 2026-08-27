import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { StrainScreen } from '@/components/Admin/StrainScreen'
import { CATALOGUE_PATH, TERMS_PATH } from '@/lib/catalogue-routes'
import { requireRole } from '@/lib/club-session'
import { getCultivators, getStrain, getVocabularies } from '@/lib/server-api'
import { STRAIN_FORM } from '@/lib/strain-catalogue-content'

export const metadata: Metadata = {
  title: STRAIN_FORM.editHeading,
}

/**
 * One strain: its record, who offers it, and how to retire it.
 *
 * Addressed by id rather than by slug. The slug is derived from the name on every
 * write, so a rename would move this URL and break a bookmark against a strain
 * that is still there — see `catalogue-routes.ts`.
 *
 * `params` is a promise and is awaited. That is the Next.js 16 contract, not a
 * flourish: it was synchronous through version 14 and accessing it that way is
 * on its way out.
 *
 * The three reads run concurrently, being independent of each other. Two of them
 * can refuse and both fold to a 404 — a strain that does not exist and a strain
 * this account may not manage are the same answer, and separating them would be
 * a distinction with no rendering behind it.
 *
 * ## The metadata does not name the strain
 *
 * It could — this page has the record — but `generateMetadata` would mean a
 * second read of the same strain on every render, since the function and the
 * component do not share one. A browser tab reading "Edit this strain" is a small
 * loss against a round trip on every page load, and these screens are
 * `noindex, nofollow` from the root layout so nothing else consumes the title.
 */
export default async function StrainPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  await requireRole('admin')

  const { id } = await params

  const [strain, vocabularies, cultivators] = await Promise.all([
    getStrain(id),
    getVocabularies(),
    getCultivators(),
  ])

  if (strain === null || vocabularies === null) notFound()

  return (
    <StrainScreen
      initial={strain}
      vocabularies={vocabularies}
      cultivators={cultivators}
      catalogueHref={CATALOGUE_PATH}
      termsHref={TERMS_PATH}
    />
  )
}

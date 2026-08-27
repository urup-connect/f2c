import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { TermsScreen } from '@/components/Admin/TermsScreen'
import { CATALOGUE_PATH } from '@/lib/catalogue-routes'
import { requireRole } from '@/lib/club-session'
import { getVocabularies } from '@/lib/server-api'
import { TERMS_SCREEN } from '@/lib/strain-catalogue-content'

export const metadata: Metadata = {
  title: TERMS_SCREEN.title,
}

/**
 * The aroma and effect vocabularies.
 *
 * A static segment beside `[id]`, and Next.js resolves it first — so `terms` is
 * never mistaken for a strain. Neither could it be: a strain is addressed by
 * UUID.
 *
 * Nested under the catalogue rather than sitting beside it, because that is what
 * these are: `Strain.aromas` and `Strain.effects` are many-to-many fields on a
 * strain, and the only screen that reads them is the strain form. A cultivator
 * asking for "gassy" to be added is asking about the catalogue.
 */
export default async function TermsPage() {
  await requireRole('admin')

  const vocabularies = await getVocabularies()
  if (vocabularies === null) notFound()

  return <TermsScreen initial={vocabularies} catalogueHref={CATALOGUE_PATH} />
}

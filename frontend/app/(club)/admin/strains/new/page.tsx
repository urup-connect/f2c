import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { StrainScreen } from '@/components/Admin/StrainScreen'
import { CATALOGUE_PATH, TERMS_PATH } from '@/lib/catalogue-routes'
import { requireRole } from '@/lib/club-session'
import { getCultivators, getVocabularies } from '@/lib/server-api'
import { STRAIN_FORM } from '@/lib/strain-catalogue-content'

export const metadata: Metadata = {
  title: STRAIN_FORM.addHeading,
}

/**
 * Adding a strain to the catalogue.
 *
 * The same screen as the edit route with `initial` of null — see `StrainScreen`,
 * which grows the offers and retire cards once the record exists rather than
 * navigating away. So this file's whole job is the two lists the form's pickers
 * need, and the guard.
 *
 * The two reads run concurrently. They are independent, and awaiting them in
 * sequence would make the page's time-to-first-paint the sum of two round trips
 * for no reason. `getVocabularies` is the one that can refuse — see the list
 * page on why a refusal here is a 404 — and `getCultivators` answers an empty
 * list instead, because a form with nothing to reserve a strain to is still a
 * usable form.
 */
export default async function NewStrainPage() {
  await requireRole('admin')

  const [vocabularies, cultivators] = await Promise.all([
    getVocabularies(),
    getCultivators(),
  ])

  if (vocabularies === null) notFound()

  return (
    <StrainScreen
      initial={null}
      vocabularies={vocabularies}
      cultivators={cultivators}
      catalogueHref={CATALOGUE_PATH}
      termsHref={TERMS_PATH}
    />
  )
}

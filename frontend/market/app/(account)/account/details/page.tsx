import type { Metadata } from 'next'
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { DetailsForm } from '@/components/Account/DetailsForm'
import { ACCOUNT_PATH } from '@/lib/navigation'
import { getProfile } from '@/lib/server-api'
import { requireSession } from '@/lib/session'
import { ACCOUNT_HOME, PROFILE_COPY } from '@/lib/store-content'

export const metadata: Metadata = {
  title: PROFILE_COPY.title,
}

/**
 * A customer's own details.
 *
 * The record is read on the server so the whole form is in the first paint. That matters here more than
 * elsewhere: a form that arrives empty and fills in a moment later is a form somebody can start typing
 * into before their own details land on top of what they typed.
 *
 * `notFound()` for a session with no profile. It cannot happen — `requireSession` has already
 * established the account exists, and the same cookie fetched both — so this is the branch that stops a
 * `null` reaching the component rather than a state anybody meets. A 404 rather than an error page: if
 * the API genuinely has no record for this session, there is nothing at this address.
 */
export default async function DetailsPage() {
  await requireSession()

  const profile = await getProfile()
  if (profile === null) notFound()

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-12">
      <Link
        href={ACCOUNT_PATH}
        className="font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
      >
        {`← ${ACCOUNT_HOME.title}`}
      </Link>

      <DetailsForm initial={profile} />
    </div>
  )
}

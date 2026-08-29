import type { Metadata } from 'next'
import Link from 'next/link'

import { PasskeyCard } from '@/components/Account/PasskeyCard'
import { ACCOUNT_PATH } from '@/lib/navigation'
import { readPasskeys, requireSession } from '@/lib/session'
import { ACCOUNT_DESTINATIONS, ACCOUNT_HOME } from '@/lib/store-content'

export const metadata: Metadata = {
  title: ACCOUNT_DESTINATIONS.security.title,
}

/**
 * How a customer signs in: the passkeys on this account.
 *
 * The list is read on the server so it is in the first paint — somebody with three passkeys should never
 * see "no passkey yet" for a frame, which reads as though the store lost them.
 *
 * `readPasskeys` never throws, and answers "unavailable" when Django could not be asked. The card then
 * says the list could not be read rather than claiming there are none, which is the difference between
 * a customer waiting and a customer enrolling a fourth passkey they did not need.
 *
 * There is nothing else on this screen, and that is worth stating: there is no password to change,
 * because the platform has none. An emailed code is the other way in and needs no setting up.
 */
export default async function SecurityPage() {
  await requireSession()

  const { passkeys, unavailable } = await readPasskeys()

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-12">
      <Link
        href={ACCOUNT_PATH}
        className="font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
      >
        {`← ${ACCOUNT_HOME.title}`}
      </Link>

      <PasskeyCard initial={passkeys} unavailable={unavailable} />
    </div>
  )
}

import Link from 'next/link'
import { submitAgeCheck } from './actions'
import { AgeCheckForm } from '@/components/AgeGate/AgeCheckForm'
import { AuthCard } from '@/components/Ui/AuthCard'
import { isAgeCheckRefusal } from '@/lib/age-gate'
import { AGE_CHECK } from '@/lib/age-gate-content'

/*
 * The gate in front of joining.
 *
 * No `robots` field: like every other route but the landing page, this inherits
 * `noindex, nofollow` from the root layout and the proxy.
 *
 * The refusal arrives in the query string as a reason code and is narrowed before it is trusted,
 * so a hand-typed or stale code shows the plain form rather than a blank error.
 * See design/features/age-gate-before-sign-up.md sections 6.1 and 6.2.
 */
export default async function AgeCheck({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const { refused } = await searchParams

  return (
    <AuthCard>
      <h1 className="font-display text-3xl tracking-display text-forest-green">
        {AGE_CHECK.heading}
      </h1>

      <div className="mt-6">
        <AgeCheckForm
          action={submitAgeCheck}
          refusal={isAgeCheckRefusal(refused) ? refused : undefined}
        />
      </div>

      <Link
        href="/"
        className="mt-8 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        {AGE_CHECK.back}
      </Link>
    </AuthCard>
  )
}

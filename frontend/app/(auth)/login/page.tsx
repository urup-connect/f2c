import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { Suspense } from 'react'

import { SignInForm } from '@/components/Auth/SignInForm'
import { AuthCard } from '@/components/Ui/AuthCard'
import { clubHomeFor } from '@/lib/club-roles'
import { currentUser } from '@/lib/club-session'
import { SIGN_IN } from '@/lib/sign-in-content'

export const metadata: Metadata = {
  title: SIGN_IN.title,
}

/**
 * Where a member gets in.
 *
 * **A signed-in visitor is sent to their own area rather than shown the form again.** Somebody who
 * follows an old bookmark or presses back after signing in has not asked to sign out, and a form
 * that appears to have forgotten them reads as though something went wrong.
 *
 * The form itself is a Client Component: WebAuthn is a browser ceremony and nothing about it can
 * happen on the server. It is wrapped in `Suspense` because it reads the query string through
 * `useSearchParams`, which opts a route into client-side rendering unless a boundary is there to
 * catch it.
 *
 * This screen inherits `noindex, nofollow` from the root layout, which is the default-deny the
 * design relies on. Nothing here overrides it.
 */
export default async function LogIn() {
  const user = await currentUser()

  if (user !== null) redirect(clubHomeFor(user.role) ?? '/')

  return (
    <AuthCard width="wide">
      <h1 className="font-display text-3xl tracking-display text-forest-green">
        {SIGN_IN.title}
      </h1>
      <p className="mt-3 font-sans text-base leading-relaxed text-muted-foreground">
        {SIGN_IN.standfirst}
      </p>

      <div className="mt-8 max-w-md">
        <Suspense>
          <SignInForm />
        </Suspense>
      </div>

      <Link
        href="/"
        className="mt-8 inline-block font-sans text-sm text-primary underline underline-offset-4 hover:text-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        {SIGN_IN.back}
      </Link>
    </AuthCard>
  )
}

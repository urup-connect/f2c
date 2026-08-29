import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { Suspense } from 'react'

import { SignInForm } from '@/components/Auth/SignInForm'
import { AuthCard } from '@/components/Ui/AuthCard'
import { ACCOUNT_HOME_PATH } from '@/lib/sign-in'
import { SIGN_IN } from '@/lib/sign-in-content'
import { currentUser } from '@/lib/session'

export const metadata: Metadata = {
  title: SIGN_IN.title,
}

/**
 * Where a customer gets in.
 *
 * **A signed-in visitor is sent to their account rather than shown the form again.** Somebody who
 * follows an old bookmark or presses back after signing in has not asked to sign out, and a form that
 * appears to have forgotten them reads as though something went wrong.
 *
 * The form itself is a Client Component: WebAuthn is a browser ceremony and nothing about it can
 * happen on the server. It is wrapped in `Suspense` because it reads the query string through
 * `useSearchParams`, which opts a route into client-side rendering unless a boundary is there to catch
 * it.
 */
export default async function SignIn() {
  const user = await currentUser()

  if (user !== null) redirect(ACCOUNT_HOME_PATH)

  return (
    <AuthCard width="wide">
      <h1 className="font-display text-3xl tracking-display text-leaf">{SIGN_IN.title}</h1>
      <p className="mt-3 font-sans text-base leading-relaxed text-muted-foreground">
        {SIGN_IN.standfirst}
      </p>

      <div className="mt-8 max-w-md">
        <Suspense>
          <SignInForm />
        </Suspense>
      </div>

      <p className="mt-8 font-sans text-sm text-muted-foreground">
        {SIGN_IN.noAccount}{' '}
        <Link
          href="/sign-up"
          className="text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
        >
          {SIGN_IN.noAccountLink}
        </Link>
      </p>

      <Link
        href="/"
        className="mt-4 inline-block font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
      >
        {SIGN_IN.back}
      </Link>
    </AuthCard>
  )
}

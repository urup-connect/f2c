import type { Metadata } from 'next'
import Link from 'next/link'
import { redirect } from 'next/navigation'

import { SignUpForm } from '@/components/Auth/SignUpForm'
import { AuthCard } from '@/components/Ui/AuthCard'
import { ACCOUNT_HOME_PATH } from '@/lib/sign-in'
import { SIGN_UP } from '@/lib/sign-up-content'
import { currentUser } from '@/lib/session'
import { signUp } from './actions'

export const metadata: Metadata = {
  title: SIGN_UP.title,
}

/**
 * Where a customer creates an account.
 *
 * **A signed-in visitor is sent to their account rather than shown the form**, the same as sign-in and
 * for the same reason: somebody who already has an account has not asked for a second one, and the two
 * would share an email address, which the API refuses.
 *
 * The action is passed to the form rather than imported by it, so the form is a plain component that
 * can be rendered in a test with a stub — the alternative is a component that reaches for a server
 * action and cannot be exercised without one.
 *
 * Note what this screen does *not* collect: no identity number, no consents, no password. See
 * `lib/sign-up.ts` for each of the three and why. Consents arrive here when the store's own documents
 * are published — `design/todo.md` Block B.
 */
export default async function SignUp() {
  const user = await currentUser()

  if (user !== null) redirect(ACCOUNT_HOME_PATH)

  return (
    <AuthCard width="wide">
      <h1 className="font-display text-3xl tracking-display text-leaf">{SIGN_UP.title}</h1>
      <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
        {SIGN_UP.standfirst}
      </p>

      <div className="mt-8">
        <SignUpForm action={signUp} />
      </div>

      <Link
        href="/"
        className="mt-8 inline-block font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
      >
        {SIGN_UP.back}
      </Link>
    </AuthCard>
  )
}

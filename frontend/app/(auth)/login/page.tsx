import Link from 'next/link'
import { AuthCard } from '@/components/Ui/AuthCard'

/*
 * No form yet. How a member gains access — a link sent by email or a code — is an open
 * product decision, so the shape of this form is not yet known. See
 * design/features/public-landing-and-auth-routing.md risk 5.
 */
export default function LogIn() {
  return (
    <AuthCard>
      <h1 className="font-display text-3xl tracking-display text-forest-green">Log In</h1>
      <p className="mt-4 text-muted-foreground">
        Members will sign in here once the club opens.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        Back to Cultivators Collective
      </Link>
    </AuthCard>
  )
}

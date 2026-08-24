import Link from 'next/link'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/**
 * Shown instead of the form when joining cannot proceed for a reason that is ours.
 *
 * Two causes, one screen. The club documents in force cannot be read, so the form is withheld
 * rather than rendered without its agreements — a member cannot agree to a document nobody can
 * serve them, and a form that quietly drops one agreement collects a consent that is incomplete in
 * a way nobody can see, including the club later in a dispute. Or a registration that passed every
 * rule could not be written, because the API was unreachable or a required document has no
 * published revision.
 *
 * They are not distinguished, deliberately. In both cases nothing was stored and there is nothing
 * the visitor can do; a message per cause would only ask them to act on a fault they cannot reach.
 * The wording says the details are fine, because they are.
 *
 * A Server Component with no state and no retry button: there is nothing the member can do about
 * it, and a button that only reloads the page pretends otherwise.
 *
 * See design/features/sign-up.md sections 5 and 6.
 */
export const DocumentsUnavailable = () => (
  <>
    <h1 className="font-display text-3xl tracking-display text-forest-green">
      {MEMBER_DETAILS_COPY.unavailable.heading}
    </h1>

    {MEMBER_DETAILS_COPY.unavailable.body.map((line) => (
      <p key={line} className="mt-4 font-sans text-base leading-relaxed text-foreground">
        {line}
      </p>
    ))}

    <Link
      href="/"
      className="mt-6 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
    >
      {MEMBER_DETAILS_COPY.back}
    </Link>
  </>
)

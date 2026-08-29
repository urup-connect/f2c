import Link from 'next/link'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

type DocumentsUnavailableProps = {
  /**
   * The handle on the log line that says what actually failed, when there is one.
   *
   * Present when a submission could not be written — the fault was ours and somebody may want to
   * report it. Absent when the club documents simply could not be read on the way in: that screen
   * is rendered before anything was attempted on the member's behalf, and a reference with nothing
   * behind it is worse than none.
   */
  reference?: string
}

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
 * What it will now carry is a reference, when a submission was attempted and could not be written.
 * That is the whole of what a member is given about a fault on our side: eight characters that
 * point at a log line they cannot read, and no description of the fault. It is what makes the
 * failure reportable without them having to describe anything about themselves to report it — the
 * wording says so, because being asked for a code after typing an identity number into a form
 * deserves an answer to the obvious question. See design/features/sign-up.md section 7.
 *
 * See also sections 5 and 6.
 */
export const DocumentsUnavailable = ({ reference }: DocumentsUnavailableProps) => (
  <>
    <h1 className="font-display text-3xl tracking-display text-forest-green">
      {MEMBER_DETAILS_COPY.unavailable.heading}
    </h1>

    {MEMBER_DETAILS_COPY.unavailable.body.map((line) => (
      <p key={line} className="mt-4 font-sans text-base leading-relaxed text-foreground">
        {line}
      </p>
    ))}

    {reference === undefined ? null : (
      <p className="mt-4 font-sans text-base leading-relaxed text-muted-foreground">
        {MEMBER_DETAILS_COPY.unavailable.reference(reference)}
      </p>
    )}

    <Link
      href="/"
      className="mt-6 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
    >
      {MEMBER_DETAILS_COPY.back}
    </Link>
  </>
)

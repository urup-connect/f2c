import Link from 'next/link'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/**
 * What a visitor sees once every detail passed: the club is not open, and nothing was kept.
 *
 * It replaces the form on a fresh page render rather than appearing beneath it, so the heading is
 * the first thing in the document and is reached without any focus script — which is also why this
 * stays a Server Component and works identically with JavaScript switched off.
 *
 * The second sentence is the one that matters. Somebody has just typed their identity number and
 * is entitled to know that no application is pending anywhere.
 *
 * See design/features/member-details-at-sign-up.md criterion 37 and section 10, risk 1.
 */
export const SubmissionOutcome = () => (
  <>
    <h1 className="font-display text-3xl tracking-display text-forest-green">
      {MEMBER_DETAILS_COPY.outcome.heading}
    </h1>

    {MEMBER_DETAILS_COPY.outcome.body.map((line) => (
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

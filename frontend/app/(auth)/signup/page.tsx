import { cookies } from 'next/headers'
import Link from 'next/link'
import { redirect } from 'next/navigation'
import { submitMemberDetails } from './actions'
import { CollectionNotice } from '@/components/SignUp/CollectionNotice'
import { DocumentsUnavailable } from '@/components/SignUp/DocumentsUnavailable'
import { MemberDetailsForm } from '@/components/SignUp/MemberDetailsForm'
import { SubmissionOutcome } from '@/components/SignUp/SubmissionOutcome'
import { AuthCard } from '@/components/Ui/AuthCard'
import { AGE_PASS_COOKIE, readAgePass } from '@/lib/age-gate-cookie'
import { fetchClubDocumentRevisions } from '@/lib/club-documents-api'
import { readErrorReference } from '@/lib/error-reference'
import { parseMemberDetailsRefusals } from '@/lib/member-details'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/*
 * Joining: the details the club asks a new member for.
 *
 * No `robots` field: like every other route but the landing page, this inherits
 * `noindex, nofollow` from the root layout and the proxy.
 *
 * This route is where the age gate is enforced, rather than on the landing page's buttons: one
 * guard, so a bookmark, a shared link or any entry point added later is gated without anyone
 * having to remember to point it at the check. The pass is re-read on every request, and reading
 * it re-applies the eighteen-year rule, so a stale, forged or expired cookie sends the visitor
 * back to the gate. Criterion 1.
 *
 * The date of birth is not displayed here at all — the product owner's decision — and nothing
 * offers to change it. It still reaches the form as a prop, because the browser-side check needs
 * something to check against, but never as text on the page and never as an input. The server
 * re-reads the cookie rather than trusting anything sent back. Criteria 3 and 4.
 *
 * The card is the wide one, and the form inside it is two columns from the medium breakpoint up.
 * The outcome screen goes back to the narrow card: it is two sentences, not a form.
 *
 * The three club documents are read from Django rather than named here: the address, the version
 * and the sentence a member ticks all come from whichever revision is in force at the moment this
 * page renders. That is what lets a revised document be published in the admin instead of
 * deployed. See design/features/sign-up.md section 5.
 *
 * If they cannot be read, the form is withheld rather than rendered without its agreements — a
 * member cannot agree to a document nobody can serve them. That check is here rather than inside
 * the form, so there is one place a missing document stops sign-up.
 *
 * Nothing entered here is stored, the agreements included. See
 * design/features/member-details-at-sign-up.md sections 2 and 9.
 */
export default async function SignUp({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const store = await cookies()
  const pass = readAgePass(store.get(AGE_PASS_COOKIE)?.value, new Date())

  if (!pass) redirect('/age-check')

  const { refused, submitted, unavailable, ref } = await searchParams

  if (submitted === '1') {
    return (
      <AuthCard>
        <SubmissionOutcome />
      </AuthCard>
    )
  }

  /*
   * A registration that could not be completed: Django unreachable, or a club document with no
   * revision in force. Nothing was written and there is nothing the visitor can do, which is the
   * same position as documents that cannot be read — so it is the same screen, before the fetch
   * below, because that fetch may be the thing that is failing.
   *
   * `ref` is the reference the server action minted and logged the cause against. Read strictly:
   * anything that is not eight hex characters is dropped rather than rendered, so a hand-typed or
   * doctored parameter cannot put text of somebody else's choosing on this screen.
   */
  if (unavailable === '1') {
    return (
      <AuthCard>
        <DocumentsUnavailable reference={readErrorReference(ref) ?? undefined} />
      </AuthCard>
    )
  }

  const documents = await fetchClubDocumentRevisions()

  if (documents.status === 'unusable') {
    return (
      <AuthCard>
        <DocumentsUnavailable />
      </AuthCard>
    )
  }

  return (
    <AuthCard width="wide">
      <h1 className="font-display text-3xl tracking-display text-forest-green">
        {MEMBER_DETAILS_COPY.heading}
      </h1>

      {/* Above the fields, never below them: the position has to be known before typing. */}
      <div className="mt-6">
        <CollectionNotice />
      </div>

      <div className="mt-8">
        <MemberDetailsForm
          action={submitMemberDetails}
          dateOfBirth={pass.dateOfBirth}
          revisions={documents.revisions}
          refusals={parseMemberDetailsRefusals(refused)}
        />
      </div>

      {/* To the landing page, never to the age check: see the note above about the date. */}
      <Link
        href="/"
        className="mt-8 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        {MEMBER_DETAILS_COPY.back}
      </Link>
    </AuthCard>
  )
}

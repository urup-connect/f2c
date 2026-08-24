'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { AGE_PASS_COOKIE, readAgePass } from '@/lib/age-gate-cookie'
import { fetchClubDocumentRevisions } from '@/lib/club-documents-api'
import {
  readMemberDetailsInput,
  serialiseMemberDetailsRefusals,
  validateMemberDetails,
} from '@/lib/member-details'
import { registerMember } from '@/lib/registration-api'

/**
 * Decides the member details, and registers the member.
 *
 * The age pass is read again here rather than trusted from the page. A submission arrives as an
 * HTTP request like any other, so the date of birth the ID number is checked against has to come
 * from the cookie the server can verify, never from the form. A pass that has expired between the
 * page rendering and the visitor submitting sends them back to the gate. Criterion 43.
 *
 * The same pure functions the browser used run again here, and this outcome is the one that counts.
 * Criterion 41.
 *
 * A refusal redirects with reason codes and nothing else — no name, no address, no identity
 * number. A redirect can only carry a URL, and a URL is written to every access log on the way.
 * Criterion 40. That holds for the refusals Django sends back as well: a taken nickname and a
 * superseded document both travel as the same reason codes the browser-side rules produce, mapped
 * in `lib/registration.ts`, so the form has one way of showing a refusal rather than two.
 *
 * **The accepted path now writes.** It calls `POST /api/members/register`, which stores the member
 * and their three agreements in one transaction and leaves the account at `pending_payment`. Until
 * a payment lands the account cannot sign in — Django derives `is_active` from `status` and its
 * check constraint holds the two together, so there is no way for a registration to produce an
 * account that can log in.
 *
 * Two things this deliberately does not decide.
 *
 * It does not tell a visitor that their address or identity number is already on file. Django
 * answers a duplicate exactly as it answers a new registration, writing nothing, because the
 * alternative turns this form into a way to ask whether a named person is a member here. A taken
 * *nickname* is refused out loud, because a nickname is a claim against other members and there is
 * nothing to disclose in saying one is spoken for.
 *
 * It does not distinguish an unreachable API from a club document with no published revision.
 * Either way nothing was written, there is nothing the visitor can do, and `/signup?unavailable=1`
 * says so. Inventing a message per cause would only ask them to act on a fault that is ours.
 *
 * The revisions in force are re-read here rather than trusted from the form. A document can be
 * published between the page rendering and the member submitting, and a tick beside the old wording
 * is not an agreement to the new text. `validateMemberDetails` compares the version the form
 * carried against the one now in force and refuses the difference; Django's `resolve_submitted`
 * refuses it a second time, because a server action is an HTTP request like any other.
 */
export const submitMemberDetails = async (formData: FormData) => {
  const store = await cookies()
  const pass = readAgePass(store.get(AGE_PASS_COOKIE)?.value, new Date())

  if (!pass) redirect('/age-check')

  const documents = await fetchClubDocumentRevisions()

  /*
   * No documents, no submission. Back to the form, which renders the same refusal for the same
   * reason: nobody may be recorded as agreeing to a document that could not be served.
   */
  if (documents.status === 'unusable') redirect('/signup')

  const outcome = validateMemberDetails(
    readMemberDetailsInput(formData),
    pass.dateOfBirth,
    documents.revisions,
  )

  if (outcome.status === 'refused') {
    redirect(refusedUrl(serialiseMemberDetailsRefusals(outcome.refusals)))
  }

  const registration = await registerMember(outcome.details)

  /*
   * `registration` is the only thing that crosses back out of Django, and it carries nothing the
   * visitor typed — see `RegistrationOut` in membership/schemas.py. Nothing from `outcome.details`
   * is logged or put in a URL, here or anywhere after this line.
   */
  if (registration.status === 'refused') {
    redirect(refusedUrl(serialiseMemberDetailsRefusals(registration.refusals)))
  }

  if (registration.status === 'unusable') redirect('/signup?unavailable=1')

  redirect('/signup?submitted=1')
}

const refusedUrl = (refusals: string) => `/signup?refused=${encodeURIComponent(refusals)}`

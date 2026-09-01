'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { AGE_PASS_COOKIE, readAgePass } from '@/lib/age-gate-cookie'
import { CAMPAIGN_COOKIE, readCampaign } from '@/lib/campaign-cookie'
import { CHECKOUT_COOKIE, checkoutCookieOptions } from '@/lib/checkout-cookie'
import { fetchClubDocumentRevisions } from '@/lib/club-documents-api'
import { newErrorReference } from '@/lib/error-reference'
import {
  readMemberDetailsInput,
  serialiseMemberDetailsRefusals,
  validateMemberDetails,
} from '@/lib/member-details'
import { registerMember } from '@/lib/registration-api'
import { SITE_CONFIG } from '@/lib/site'

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
 * **The accepted path now also hands the member to Payfast.** A registration that wrote a row comes
 * back with a checkout token, and this sets it in an `httpOnly` cookie and redirects to `/pay`.
 * See the note above that redirect for what travels where, and why the token is not in the URL.
 *
 * Two things this deliberately does not decide.
 *
 * It does not say *whether* an address or identity number is already on file. Django still answers
 * a duplicate with the same status code, the same status and the same sentence, writing nothing —
 * only without a checkout token, because there is nothing to pay for. So a duplicate lands on the
 * confirmation screen rather than at Payfast, and whoever submitted learns that the address may be
 * on file and nothing further. That is a narrowing of a rule this file used to state absolutely,
 * taken knowingly when the redirect was chosen over emailing every member their link; the cost is
 * recorded in design/features/payments.md section 4 and risk 1. A taken *nickname* is still refused
 * out loud, because a nickname is a claim against other members and there is nothing to disclose in
 * saying one is spoken for.
 *
 * It does not distinguish an unreachable API from a club document with no published revision.
 * Either way nothing was written, there is nothing the visitor can do, and `/signup?unavailable=1`
 * says so. Inventing a message per cause would only ask them to act on a fault that is ours.
 *
 * What it does now do is make that fault reportable. A failure mints a reference, logs the cause
 * against it server-side, and carries the reference — and only the reference — back in the query
 * string. So the screen says something failed and gives the member eight characters to quote,
 * while which fault it was stays in a log line they cannot read and nobody has to describe
 * themselves to report it. See design/features/sign-up.md section 7.
 *
 * **The campaign comes from a cookie, not the form.** No screen asks a member how they found the
 * club, and none should: the answer is already in the URL they arrived on, and asking would collect
 * an opinion where a fact was available. It travels with the registration and can change nothing
 * about the outcome — see `lib/campaign-cookie.ts` and `app/core/attribution`.
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

  /*
   * The campaign, read here and sent with the registration. This is the only moment it can be
   * recorded: there is finally a record to attach it to, and the cookie that has been carrying it
   * since the visitor arrived is about to stop being the only copy.
   *
   * `null` for the visitor who typed the address, followed a bookmark, or arrived before this
   * existed, and that is stored as an absence rather than as a campaign called "direct" — see
   * `lib/campaign-cookie.ts`. The cookie is deliberately **not** cleared afterwards: it outlives
   * this submission on purpose, so that a duplicate or a refusal does not silently lose the
   * campaign before the member gets their details right.
   */
  const campaign = readCampaign(store.get(CAMPAIGN_COOKIE)?.value)

  const registration = await registerMember(outcome.details, campaign)

  /*
   * `registration` is the only thing that crosses back out of Django, and it carries nothing the
   * visitor typed — see `RegistrationOut` in membership/schemas.py. Nothing from `outcome.details`
   * is logged or put in a URL, here or anywhere after this line.
   */
  if (registration.status === 'refused') {
    redirect(refusedUrl(serialiseMemberDetailsRefusals(registration.refusals)))
  }

  /*
   * The fault was ours, and it is now reportable. A reference is minted, the reason is logged
   * against it here — where the member cannot read it and where nothing they typed is in scope —
   * and only the reference travels back. `registration.reason` is written by `registration-api.ts`
   * and says which kind of failure it was; it carries no submitted value, which is why it may be
   * logged at all. Criterion 40 still holds: the query string carries eight random characters.
   */
  if (registration.status === 'unusable') {
    const reference = newErrorReference()

    console.error(`[register] ${reference}: ${registration.reason}`)

    redirect(`/signup?unavailable=1&ref=${reference}`)
  }

  /*
   * Accepted, and now one of two hand-offs.
   *
   * **A token means a member was written**, and they go to Payfast. The token travels in an
   * `httpOnly` cookie rather than in the redirect, because a redirect carries only a URL and a URL
   * is written to every access log between here and the member — Criterion 40 again, applied to a
   * value this application minted rather than to one the member typed. See `lib/checkout-cookie.ts`.
   *
   * **No token means the submission named somebody already on file.** Nothing was written, and this
   * is the path that keeps that from being disclosed outright: the member lands on the same
   * confirmation screen sign-up has always used, and Django emails the outstanding payment link to
   * the address instead — which reaches the mailbox rather than whoever filled in the form.
   *
   * The two screens are not identical, and that is the known cost of redirecting straight to
   * payment: somebody submitting another person's address learns that it may already be on file.
   * They learn nothing else — no name, no status, no amount, no confirmation. The alternative was
   * emailing every member their link and sending nobody to Payfast directly, which was weighed and
   * not taken. See design/features/payments.md section 4 and risk 1.
   */
  if (registration.checkoutToken) {
    store.set(CHECKOUT_COOKIE, registration.checkoutToken, checkoutCookieOptions(SITE_CONFIG))

    redirect('/pay')
  }

  redirect('/signup?submitted=1')
}

const refusedUrl = (refusals: string) => `/signup?refused=${encodeURIComponent(refusals)}`

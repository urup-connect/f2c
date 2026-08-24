/**
 * Turning Django's answer to a registration back into something the form can show.
 *
 * Pure, and separate from the fetch that produces the input, for one reason: the mapping is the
 * part that can be wrong in a way nobody notices. A refusal that fails to map lands on no field,
 * the error summary shows nothing, and the member sees a form that silently did not submit. So it
 * is a function with a test rather than a few lines inside a server action.
 *
 * Two decisions are recorded here.
 *
 * **The refusal is read from named fields, never from the message.** Django returns
 * `nickname_unavailable` and `superseded_documents`; the prose in `detail` is for a human and for a
 * log. Matching on prose is how this would quietly stop working the first time somebody improved
 * the wording.
 *
 * **An answer this module does not understand is a refusal, not a success.** A body missing its
 * fields, an unrecognised document id, a status code nobody planned for: all of them mean the
 * member cannot be told what happened, and the honest response is to send them back to the form
 * rather than to a confirmation screen for a membership that may not exist.
 *
 * See design/features/sign-up.md section 6.
 */

import { isClubDocumentId } from './club-documents'
import type { ClubDocumentId } from './club-documents'
import { MEMBER_CONSENT_FIELDS } from './member-details'
import type { MemberDetailsFieldRefusal } from './member-details'

/** What Django answers a successful registration with. Mirrors `RegistrationOut`. */
export type RegistrationAccepted = {
  /** Where the account now sits. `pending_payment` until a payment lands. */
  readonly status: string
  readonly detail: string
}

/** What Django answers a refusal with. Mirrors `RegistrationRefusedOut`. */
export type RegistrationRefusedBody = {
  readonly detail?: unknown
  readonly nickname_unavailable?: unknown
  readonly superseded_documents?: unknown
}

export type RegistrationOutcome =
  | { readonly status: 'accepted'; readonly memberStatus: string }
  /** Refusals to render against specific fields, exactly as the validator's are. */
  | { readonly status: 'refused'; readonly refusals: readonly MemberDetailsFieldRefusal[] }
  /**
   * Nothing the member can act on: the API is unreachable, a document has no published revision,
   * or the answer made no sense. The form says the fault is ours, because it is.
   */
  | { readonly status: 'unusable'; readonly reason: string }

/** The status the backend puts a new member at, and what the confirmation screen expects. */
export const PENDING_PAYMENT = 'pending_payment'

/** Which checkbox stands for which document, inverted from the form's own mapping. */
const CONSENT_FIELD_FOR_DOCUMENT = new Map<ClubDocumentId, MemberDetailsFieldRefusal['field']>(
  MEMBER_CONSENT_FIELDS.map(({ field, document }) => [document, field]),
)

const asStringArray = (value: unknown): readonly string[] =>
  Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : []

/**
 * The refusals a 409 stands for, as field-and-reason pairs the form already knows how to render.
 *
 * A document id this application does not know is dropped rather than guessed at — the same trade
 * `readClubDocumentRevisions` makes, and for the same reason: staff publishing a fourth document
 * must not take sign-up down until a deploy catches up.
 *
 * Returns an empty list when the body carries no refusal this module understands, which the caller
 * must treat as unusable rather than as nothing being wrong.
 */
export const readRegistrationRefusals = (
  body: RegistrationRefusedBody,
): readonly MemberDetailsFieldRefusal[] => {
  const refusals: MemberDetailsFieldRefusal[] = []

  if (body.nickname_unavailable === true) {
    refusals.push({ field: 'nickname', reason: 'nickname-unavailable' })
  }

  for (const document of asStringArray(body.superseded_documents)) {
    if (!isClubDocumentId(document)) continue

    const field = CONSENT_FIELD_FOR_DOCUMENT.get(document)

    if (field !== undefined) refusals.push({ field, reason: 'consent-superseded' })
  }

  return refusals
}

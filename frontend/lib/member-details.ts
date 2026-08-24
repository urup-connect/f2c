/**
 * The whole sign-up submission, composed from the six rules that own the fields.
 *
 * This module holds no validation of its own. It reads the form, asks each rule about its field,
 * and collects every refusal rather than stopping at the first — a member with three things wrong
 * should be told three things once, not one thing three times.
 *
 * The accepted result is the normalised form: what would be stored, if anything were being stored.
 * Nothing is. See design/features/member-details-at-sign-up.md sections 2 and 6.1.
 *
 * The three club document agreements are composed here alongside the six details rather than
 * through a mechanism of their own, so that refusal ordering, the one-message-per-field rule, the
 * error summary and the no-script path all cover them without a second implementation. See
 * design/features/club-document-agreements-at-sign-up.md section 6.2.
 */

import {
  CLUB_DOCUMENT_IDS,
  checkClubConsent,
  checkClubDocumentVersion,
  clubVersionField,
} from './club-documents'
import type {
  ClubDocumentConsent,
  ClubDocumentId,
  ClubDocumentRevisions,
} from './club-documents'
import { checkEmailAddress } from './email-address'
import { checkNickname, nicknameKey } from './nickname'
import { checkPersonName } from './person-name'
import { checkSaIdNumber } from './sa-id-number'
import { checkSaMobileNumber } from './sa-mobile-number'
import type { CalendarDate } from './age-gate'

/** In the order the form shows them, which is the order refusals are reported in. */
export const MEMBER_DETAILS_FIELDS = [
  'firstName',
  'lastName',
  'nickname',
  'email',
  'mobile',
  'idNumber',
  'agreeClubRules',
  'agreeAnnexures',
  'agreeConstitution',
] as const

export type MemberDetailsField = (typeof MEMBER_DETAILS_FIELDS)[number]

/**
 * Which checkbox stands for which document.
 *
 * Written out rather than derived from the document ids: a field name spelled by an algorithm is a
 * field name nobody can search for. Exported so a test can assert it covers every document, which
 * is what stops a fourth document being added with no box to tick.
 */
export const MEMBER_CONSENT_FIELDS = [
  { field: 'agreeClubRules', document: 'club-rules' },
  { field: 'agreeAnnexures', document: 'annexures' },
  { field: 'agreeConstitution', document: 'constitution' },
] as const satisfies readonly { field: MemberDetailsField; document: ClubDocumentId }[]

/** One of the three agreement checkboxes. */
export type MemberConsentField = (typeof MEMBER_CONSENT_FIELDS)[number]['field']

/** One of the six details a member types. */
export type MemberDetailField = Exclude<MemberDetailsField, MemberConsentField>

export const isMemberConsentField = (field: MemberDetailsField): field is MemberConsentField =>
  MEMBER_CONSENT_FIELDS.some((entry): boolean => entry.field === field)

/**
 * Exactly what the form hands over. Every value a string, because that is what a form yields.
 *
 * `versions` carries the revision each agreement was rendered against, from a hidden field per
 * document. It is not one of `MEMBER_DETAILS_FIELDS`: it is not something a member fills in, has
 * no label and no message of its own, and a refusal about it belongs to the checkbox beside it.
 */
export type MemberDetailsInput = { readonly [Field in MemberDetailsField]: string } & {
  readonly versions: Readonly<Partial<Record<ClubDocumentId, string>>>
}

/**
 * Every way a field can be refused, prefixed by the rule that refused it.
 *
 * One code per refusal, so a new one cannot ship without wording: the copy module holds a message
 * per code and a test fails if any is missing.
 */
export const MEMBER_DETAILS_REFUSALS = [
  'name-missing',
  'name-too-long',
  'name-unexpected-characters',
  'nickname-missing',
  'nickname-length',
  'nickname-unexpected-characters',
  'nickname-shape',
  'nickname-unavailable',
  'email-missing',
  'email-malformed',
  'email-too-long',
  'mobile-missing',
  'mobile-unexpected-characters',
  'mobile-length',
  'mobile-not-a-mobile',
  'id-missing',
  'id-length',
  'id-not-digits',
  'id-checksum',
  'id-date-mismatch',
  'id-not-recognised',
  'consent-required',
  'consent-superseded',
] as const

export type MemberDetailsRefusal = (typeof MEMBER_DETAILS_REFUSALS)[number]

export const isMemberDetailsRefusal = (value: unknown): value is MemberDetailsRefusal =>
  typeof value === 'string' &&
  MEMBER_DETAILS_REFUSALS.some((refusal): boolean => refusal === value)

export type MemberDetailsFieldRefusal = {
  readonly field: MemberDetailsField
  readonly reason: MemberDetailsRefusal
}

/** The normalised, storable form. Produced only when every field passed. */
export type MemberDetails = {
  readonly firstName: string
  readonly lastName: string
  /** As typed, for display. */
  readonly nickname: string
  /** Lower-cased, for uniqueness. */
  readonly nicknameKey: string
  /** Lower-cased. */
  readonly email: string
  /** `+27` followed by nine digits. */
  readonly mobile: string
  /** Thirteen digits, separators removed. Never logged, never returned to the browser. */
  readonly idNumber: string
  readonly dateOfBirth: CalendarDate
  /**
   * One entry per club document, in document order, each naming the revision agreed to.
   *
   * No timestamp: this function is pure, and the moment of agreement is the moment of the write,
   * which the database stamps. Two clocks for one fact eventually disagree.
   */
  readonly consents: readonly ClubDocumentConsent[]
}

export type MemberDetailsOutcome =
  | { readonly status: 'accepted'; readonly details: MemberDetails }
  | { readonly status: 'refused'; readonly refusals: readonly MemberDetailsFieldRefusal[] }

/**
 * A `FormData` entry is a string or a `File`. A file in one of these fields is not something a
 * visitor can do through the form, so it is read as no answer at all rather than special-cased —
 * and an absent field reads the same way, which is what makes it refused as missing rather than
 * quietly acceptable.
 */
const field = (formData: FormData, name: string) => {
  const value = formData.get(name)

  return typeof value === 'string' ? value : ''
}

export const readMemberDetailsInput = (formData: FormData): MemberDetailsInput => ({
  firstName: field(formData, 'firstName'),
  lastName: field(formData, 'lastName'),
  nickname: field(formData, 'nickname'),
  email: field(formData, 'email'),
  mobile: field(formData, 'mobile'),
  idNumber: field(formData, 'idNumber'),
  agreeClubRules: field(formData, 'agreeClubRules'),
  agreeAnnexures: field(formData, 'agreeAnnexures'),
  agreeConstitution: field(formData, 'agreeConstitution'),
  versions: Object.fromEntries(
    CLUB_DOCUMENT_IDS.map((document) => [document, field(formData, clubVersionField(document))]),
  ),
})

/**
 * The whole submission, from what the visitor typed to an outcome. Never throws for any input.
 *
 * `revisions` is what Django says is in force, and it decides two things: which version each
 * agreement is recorded against, and whether the version the form was rendered against is still
 * the current one. A caller must read it rather than assume it — that is the whole reason a
 * document's version is no longer a constant in this codebase.
 *
 * `takenNicknameKeys` is how the caller supplies the display names already spoken for. It is empty
 * for now, because nothing is stored; when the data layer exists it becomes a query. Only the
 * nickname is checked this way. A colliding email address or ID number must not change what the
 * visitor sees, or the form becomes a way to ask whether a named person is a member here — see
 * section 6.7.
 */
export const validateMemberDetails = (
  input: MemberDetailsInput,
  dateOfBirth: CalendarDate,
  revisions: ClubDocumentRevisions,
  takenNicknameKeys: readonly string[] = [],
): MemberDetailsOutcome => {
  const refusals: MemberDetailsFieldRefusal[] = []

  const refuse = (field: MemberDetailsField, reason: MemberDetailsRefusal) => {
    refusals.push({ field, reason })
  }

  const firstName = checkPersonName(input.firstName)
  if (firstName.status === 'invalid') refuse('firstName', `name-${firstName.reason}`)

  const lastName = checkPersonName(input.lastName)
  if (lastName.status === 'invalid') refuse('lastName', `name-${lastName.reason}`)

  const nickname = checkNickname(input.nickname)
  if (nickname.status === 'invalid') {
    refuse('nickname', `nickname-${nickname.reason}`)
  } else if (takenNicknameKeys.some((key): boolean => key === nicknameKey(nickname.nickname))) {
    refuse('nickname', 'nickname-unavailable')
  }

  const email = checkEmailAddress(input.email)
  if (email.status === 'invalid') refuse('email', `email-${email.reason}`)

  const mobile = checkSaMobileNumber(input.mobile)
  if (mobile.status === 'invalid') refuse('mobile', `mobile-${mobile.reason}`)

  const idNumber = checkSaIdNumber(input.idNumber, dateOfBirth)
  if (idNumber.status === 'invalid') refuse('idNumber', `id-${idNumber.reason}`)

  /*
   * One refusal per unticked box rather than one for the group: three documents are three separate
   * things to do about it, and a member who ticked two of three should not be told to start again.
   */
  const consents: ClubDocumentConsent[] = []

  for (const { field, document } of MEMBER_CONSENT_FIELDS) {
    const consent = checkClubConsent(input[field])

    if (consent.status === 'invalid') {
      refuse(field, `consent-${consent.reason}`)
      continue
    }

    /*
     * Ticked, but possibly against text that has since been replaced. The version the form was
     * rendered with is compared to the one in force, and a mismatch is refused rather than
     * recorded — a tick beside v1's wording is not an agreement to v2. The refusal lands on the
     * checkbox, because that is where the member has to do something about it.
     */
    const inForce = revisions[document]
    const version = checkClubDocumentVersion(input.versions[document] ?? '', inForce.version)

    if (version.status === 'invalid') {
      refuse(field, `consent-${version.reason}`)
      continue
    }

    consents.push({ document, version: inForce.version })
  }

  if (refusals.length > 0) return { status: 'refused', refusals }

  /*
   * Every branch above has narrowed, but TypeScript cannot see that an empty refusal list implies
   * it. Asserting the six statuses here is cheaper than threading the narrowed values through.
   */
  if (
    firstName.status !== 'valid' ||
    lastName.status !== 'valid' ||
    nickname.status !== 'valid' ||
    email.status !== 'valid' ||
    mobile.status !== 'valid' ||
    idNumber.status !== 'valid'
  ) {
    throw new Error('A member detail refused without recording a refusal')
  }

  return {
    status: 'accepted',
    details: {
      firstName: firstName.name,
      lastName: lastName.name,
      nickname: nickname.nickname,
      nicknameKey: nicknameKey(nickname.nickname),
      email: email.email,
      mobile: mobile.mobile,
      idNumber: idNumber.idNumber,
      dateOfBirth,
      consents,
    },
  }
}

export const isMemberDetailsField = (value: unknown): value is MemberDetailsField =>
  typeof value === 'string' && MEMBER_DETAILS_FIELDS.some((field): boolean => field === value)

const PAIR = ','
const FIELD_AND_REASON = ':'

/**
 * Refusals as a query-string value: field and reason, nothing else.
 *
 * This is the no-script path. The server cannot hand state back to a page it has not scripted, so
 * it redirects, and a redirect carries only a URL — which is exactly why no value the visitor
 * typed may travel in it. An identity number in a query string is an identity number in every
 * access log, proxy log and browser history between here and the member.
 *
 * See design/features/member-details-at-sign-up.md criterion 40 and section 9.
 */
export const serialiseMemberDetailsRefusals = (refusals: readonly MemberDetailsFieldRefusal[]) =>
  refusals.map(({ field, reason }) => `${field}${FIELD_AND_REASON}${reason}`).join(PAIR)

/**
 * The inverse, strictly. Anything unrecognised is dropped rather than guessed at, so a stale,
 * hand-typed or tampered parameter shows a plain form instead of an invented error.
 *
 * A repeated query parameter arrives as a list rather than a string, and is read as no refusals at
 * all: there is one form and one submission, so a list is not something the product produced.
 */
export const parseMemberDetailsRefusals = (
  value: unknown,
): readonly MemberDetailsFieldRefusal[] => {
  if (typeof value !== 'string' || value.length === 0) return []

  const seen = new Set<MemberDetailsField>()
  const refusals: MemberDetailsFieldRefusal[] = []

  for (const pair of value.split(PAIR)) {
    const [field, reason] = pair.split(FIELD_AND_REASON)

    if (!isMemberDetailsField(field) || !isMemberDetailsRefusal(reason)) continue
    // One message per field, so a doctored parameter cannot stack three errors on one input.
    if (seen.has(field)) continue

    seen.add(field)
    refusals.push({ field, reason })
  }

  return refusals
}

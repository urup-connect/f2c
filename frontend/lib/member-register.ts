/**
 * The membership register's own types, and the rules a browser can apply to one.
 *
 * No React, no `fetch`, no DOM. The screens are thin because everything decidable
 * without the server is decided here and tested without a renderer — the same
 * split `lib/profile.ts` and `lib/strain-catalogue.ts` make.
 *
 * ## What this refuses, and what it deliberately does not
 *
 * Every rule here is one the API enforces too, and the wording is shared with
 * sign-up: `person-name.ts`, `nickname.ts`, `email-address.ts` and
 * `sa-mobile-number.ts` are the four modules, they are already tested, and this
 * file asks each of them about its field rather than writing a fifth opinion.
 *
 * What a browser cannot answer is whether an address, a nickname or a mobile
 * number is already held by *another* account. Those three come back from the
 * API as per-field refusals and are rendered through the same list this
 * function produces — which is what lets one renderer handle both sources.
 *
 * ## The register is read-only about authority
 *
 * There is no role field and no status field in `MemberSubmission`, and their
 * absence is the design rather than an omission. Role is appointed in the Django
 * admin, because handing out authority over other members' records is not a form
 * field; standing moves through the suspend and reinstate endpoints, which have
 * rules a field assignment does not. See `app/membership/administration.py`.
 */

import { checkEmailAddress } from './email-address'
import { checkNickname } from './nickname'
import { MEMBER_REFUSALS } from './member-register-content'
import { checkPersonName, normalisePersonName } from './person-name'
import { checkSaMobileNumber } from './sa-mobile-number'

/* -------------------------------------------------------------------------- */
/* The payloads                                                                */
/* -------------------------------------------------------------------------- */

/** Where a member's subscription stands, mirroring `MembershipStandingOut`. */
export type MembershipStanding = {
  /** Null throughout when no arrangement is in force. Never a missing key. */
  status: string | null
  status_label: string | null
  /** An ISO date. The column that decides whether an account keeps its access. */
  paid_until: string | null
}

/**
 * One row on the register, mirroring `MemberRowOut`.
 *
 * No identity number in any form, not even the masked one: `id_number_masked`
 * decrypts, and a masked column on a list of six hundred members is six hundred
 * decryptions per page load. `has_id_number` is the fact a list needs and it
 * never decrypts.
 */
export type MemberRow = {
  id: string
  display_name: string
  first_name: string
  last_name: string
  nickname: string
  /** Null on an erased account — `soft_delete` clears the address and keeps the row. */
  email: string | null
  mobile: string
  status: string
  /** The label from `accounts.UserStatus`, so this build never has to own the vocabulary. */
  status_label: string
  role: string
  role_label: string
  membership: MembershipStanding
  has_id_number: boolean
  erased: boolean
  created_at: string
}

/** One recorded read of a member's identity number, mirroring `DisclosureOut`. */
export type Disclosure = {
  id: string
  /** A `display_name`, or null once that account has been deleted outright. */
  read_by: string | null
  reason: string
  created_at: string
}

/** A member in full, mirroring `MemberOut`. */
export type Member = MemberRow & {
  /**
   * All but the last four digits, `''` when none is on file, or `UNREADABLE` for
   * a row that will not decrypt. The third is surfaced rather than hidden: it is
   * a key or integrity problem somebody has to look at.
   */
  id_number_masked: string
  /**
   * Whether this screen may write to the record at all.
   *
   * Sent by the API rather than derived here. The two reasons a record is
   * read-only — it was erased, or it is a cultivator's sharing member — are
   * rules in `administration._editable`, and a second copy in this bundle would
   * be a form offering a save the API then refuses.
   */
  editable: boolean
  /** The cultivator who put a sharing member on the register. Null for everybody else. */
  registered_by: string | null
  date_of_birth: string | null
  date_of_birth_verified_at: string | null
  last_login: string | null
  updated_at: string
  disclosures: readonly Disclosure[]
}

/** The body the record screen's `PUT` sends, mirroring `MemberIn`. */
export type MemberSubmission = {
  first_name: string
  last_name: string
  nickname: string
  email: string
  mobile: string
}

/* -------------------------------------------------------------------------- */
/* The choice lists                                                            */
/* -------------------------------------------------------------------------- */

/*
 * Mirroring the `TextChoices` in `app/accounts/models.py` and
 * `app/accounts/roles.py`. Written out rather than fetched, for the reason
 * `strain-catalogue.ts` gives: these are not runtime data, they change when
 * those files change, they are held by check constraints, and an endpoint
 * answering with them would be a round trip for a list fixed at deploy time.
 *
 * They are used for the *filters* only. Every row already carries its own
 * `status_label` and `role_label` from the API, so a column never reads these —
 * which means a value this build has not heard of still renders correctly, and
 * only the dropdown is short of an option.
 */

export const MEMBER_STATUSES = [
  { value: 'pending', label: 'Pending verification' },
  { value: 'pending_payment', label: 'Pending payment' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'inactive', label: 'Inactive' },
  { value: 'sharing', label: 'Sharing member (no sign-in)' },
] as const

export const MEMBER_ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'cultivator', label: 'Cultivator' },
  { value: 'member', label: 'Member' },
  { value: 'sharing_member', label: 'Sharing member' },
] as const

/**
 * The windows the *joined* filter offers.
 *
 * Values are strings because a `select` yields one; the API takes a number and
 * `memberQueryString` does the crossing. `RECENT_WINDOWS` in
 * `app/membership/administration.py` is the same set, and the two are written
 * out separately rather than shared: a filter the screen offers and a window the
 * service documents are allowed to diverge, and neither constrains the other.
 */
export const JOINED_WINDOWS = [
  { value: '7', label: 'The last week' },
  { value: '30', label: 'The last month' },
  { value: '90', label: 'The last three months' },
] as const

/** A choice's label, or the raw value when the API has one this build does not know. */
export const labelFor = (
  choices: readonly { value: string; label: string }[],
  value: string,
): string => choices.find((choice) => choice.value === value)?.label ?? value

/**
 * Whether an account in this status may sign in.
 *
 * Only `active` may, and `User.is_active` is derived from exactly that with a
 * check constraint holding the two together. Used to mark the register rather
 * than to decide anything: a standing column that says "Pending payment" without
 * saying that it means locked out leaves an administrator guessing which of the
 * five non-active states blocks a sign-in. All of them do.
 */
export const canSignIn = (status: string): boolean => status === 'active'

/**
 * Whether this account can be suspended from this screen, and by this viewer.
 *
 * Three conditions, and the third is the one worth having: an administrator who
 * suspends their own account is signed out on the way and cannot sign back in to
 * undo it. The API refuses it too — this is what stops the button being offered
 * at all, so nobody has to discover the rule by pressing it.
 */
export const canSuspend = (member: Member, viewerId: string): boolean =>
  member.editable && member.status !== 'suspended' && member.id !== viewerId

/**
 * Whether a suspension can be lifted.
 *
 * Only from `suspended`. Nothing records where an account sat beforehand, so
 * reinstatement cannot restore it — and an account at Pending payment is not
 * blocked by the club, it is unpaid, which the subscription owns.
 */
export const canReinstate = (member: Member): boolean =>
  member.editable && member.status === 'suspended'

/** What `administration.MINIMUM_DISCLOSURE_REASON` requires, restated so the form can refuse first. */
export const MINIMUM_DISCLOSURE_REASON = 10

/** Whether a stated reason is long enough to be worth recording. */
export const disclosureReasonIsEnough = (reason: string): boolean =>
  reason.trim().length >= MINIMUM_DISCLOSURE_REASON

/** What the record screen shows when the column will not decrypt. */
export const UNREADABLE_ID_NUMBER = 'UNREADABLE'

/* -------------------------------------------------------------------------- */
/* The form                                                                    */
/* -------------------------------------------------------------------------- */

/** The record form as the browser holds it. Every value a string, as a form yields. */
export type MemberInput = {
  firstName: string
  lastName: string
  nickname: string
  email: string
  mobile: string
}

/** A field the form can mark a refusal against, keyed as the API keys it. */
export type MemberFieldRefusal = {
  field: keyof MemberSubmission
  message: string
}

const NAME_MESSAGES = {
  firstName: {
    missing: MEMBER_REFUSALS.firstNameMissing,
    'unexpected-characters': MEMBER_REFUSALS.firstNameCharacters,
    'too-long': MEMBER_REFUSALS.firstNameLong,
  },
  lastName: {
    missing: MEMBER_REFUSALS.lastNameMissing,
    'unexpected-characters': MEMBER_REFUSALS.lastNameCharacters,
    'too-long': MEMBER_REFUSALS.lastNameLong,
  },
} as const

/*
 * `missing` is unreachable: the blank case is branched on before the rule is
 * asked, because a blank nickname is an answer here rather than an omission.
 * Mapped anyway so the union stays exhaustive — a caller reaching it has found a
 * bug in `nickname.ts`, and the length message is at least true.
 */
const NICKNAME_MESSAGES = {
  missing: MEMBER_REFUSALS.nicknameLength,
  length: MEMBER_REFUSALS.nicknameLength,
  'unexpected-characters': MEMBER_REFUSALS.nicknameCharacters,
  shape: MEMBER_REFUSALS.nicknameShape,
  unavailable: MEMBER_REFUSALS.nicknameReserved,
} as const

const EMAIL_MESSAGES = {
  missing: MEMBER_REFUSALS.emailMissing,
  malformed: MEMBER_REFUSALS.emailMalformed,
  'too-long': MEMBER_REFUSALS.emailLong,
} as const

const MOBILE_MESSAGES = {
  missing: MEMBER_REFUSALS.mobileMissing,
  'unexpected-characters': MEMBER_REFUSALS.mobileCharacters,
  length: MEMBER_REFUSALS.mobileLength,
  'not-a-mobile': MEMBER_REFUSALS.mobileNotAMobile,
} as const

export type MemberCheck =
  | { readonly status: 'valid'; readonly submission: MemberSubmission }
  | { readonly status: 'invalid'; readonly refusals: readonly MemberFieldRefusal[] }

/**
 * Everything about a submission a browser can decide, and the body if it passes.
 *
 * Every refusal is collected rather than returned at the first one. A form that
 * reports one problem at a time is a form somebody submits four times, and each
 * of those is a round trip.
 *
 * **A blank nickname is accepted.** Clearing one leaves the member without a
 * nickname, which `User.display_name` already falls back from, and it is not the
 * same as the nickname being taken. Sign-up requires one because a joining
 * member is choosing how the club will see them; an administrator correcting a
 * record is not.
 *
 * **A blank mobile number is not accepted**, and that is the asymmetry with
 * `checkProfile`. A member clearing their own number is saying "I no longer have
 * that handset", which is an answer. An administrator blanking somebody else's
 * is throwing away a contact detail on their behalf, which is not.
 */
export const checkMember = (input: MemberInput): MemberCheck => {
  const refusals: MemberFieldRefusal[] = []

  const first = checkPersonName(input.firstName)
  if (first.status === 'invalid') {
    refusals.push({
      field: 'first_name',
      message: NAME_MESSAGES.firstName[first.reason],
    })
  }

  const last = checkPersonName(input.lastName)
  if (last.status === 'invalid') {
    refusals.push({
      field: 'last_name',
      message: NAME_MESSAGES.lastName[last.reason],
    })
  }

  // Blank is an answer, so the rule is asked only of a non-blank value. The same
  // shape `checkProfile` uses for the mobile number, and for the same reason:
  // `checkNickname` has no way to express "absent on purpose".
  const typedNickname = input.nickname.trim()
  let nickname = ''
  if (typedNickname !== '') {
    const checked = checkNickname(typedNickname)
    if (checked.status === 'valid') {
      nickname = checked.nickname
    } else {
      refusals.push({
        field: 'nickname',
        message: NICKNAME_MESSAGES[checked.reason],
      })
    }
  }

  const email = checkEmailAddress(input.email)
  if (email.status === 'invalid') {
    refusals.push({ field: 'email', message: EMAIL_MESSAGES[email.reason] })
  }

  const mobile = checkSaMobileNumber(input.mobile)
  if (mobile.status === 'invalid') {
    refusals.push({ field: 'mobile', message: MOBILE_MESSAGES[mobile.reason] })
  }

  if (refusals.length > 0) return { status: 'invalid', refusals }

  return {
    status: 'valid',
    submission: {
      // Read off each check rather than re-normalised here, so there is one
      // normalisation per field and the browser sends what it validated.
      first_name: first.status === 'valid' ? first.name : '',
      last_name: last.status === 'valid' ? last.name : '',
      nickname,
      email: email.status === 'valid' ? email.email : '',
      mobile: mobile.status === 'valid' ? mobile.mobile : '',
    },
  }
}

/** The message against one field, from either source, or undefined. */
export const refusalFor = (
  refusals: readonly MemberFieldRefusal[],
  field: keyof MemberSubmission,
): string | undefined => refusals.find((refusal) => refusal.field === field)?.message

/**
 * The API's per-field refusal body as this screen's own refusal list.
 *
 * `MemberRefusedOut.fields` is keyed by the API's field names, which is why
 * `MemberFieldRefusal.field` is too: one renderer, two sources, no translation
 * table to keep in step. A key this build does not know is dropped rather than
 * rendered against nothing — and `detail` is always shown as well, so the
 * sentence is never lost even when its field is.
 */
export const refusalsFromApi = (
  fields: Readonly<Record<string, readonly string[]>>,
): MemberFieldRefusal[] => {
  const known = new Set<string>([
    'first_name',
    'last_name',
    'nickname',
    'email',
    'mobile',
    // Not on the record form, and admitted anyway: the identity-number endpoint
    // keys its refusal to `reason`, and dropping it would leave that card with a
    // `detail` and no field to mark.
    'reason',
  ])

  return Object.entries(fields)
    .filter(([field, messages]) => known.has(field) && messages.length > 0)
    .map(([field, messages]) => ({
      field: field as keyof MemberSubmission,
      message: messages.join(' '),
    }))
}

/**
 * A stored member as the form holds it.
 *
 * `?? ''` on the address: null means the account was erased, and an empty field
 * is what that looks like. The form is read-only in that case anyway — `editable`
 * is false — so nothing can be typed into it.
 */
export const memberInputFrom = (member: Member): MemberInput => ({
  firstName: member.first_name,
  lastName: member.last_name,
  nickname: member.nickname,
  email: member.email ?? '',
  mobile: member.mobile,
})

/**
 * Whether anything in the form differs from what is on file.
 *
 * Compared on the *normalised* values, not the typed ones, because the form is
 * uncontrolled and this is what decides whether the save button does anything.
 * An administrator who added a trailing space to a surname, or retyped
 * `+27821234567` as `082 123 4567`, has changed nothing the club would store —
 * and a save button that lights up for that is a button promising a change it
 * will not make. The same rule `profileHasChanges` applies, for the same reason.
 *
 * A form that does not yet validate counts as changed. It cannot be normalised,
 * so the honest answer is "something is different", and pressing save is how the
 * administrator learns what.
 */
export const memberHasChanges = (input: MemberInput, member: Member): boolean => {
  const checked = checkMember(input)

  if (checked.status === 'invalid') return true

  const { submission } = checked

  return (
    submission.first_name !== normalisePersonName(member.first_name) ||
    submission.last_name !== normalisePersonName(member.last_name) ||
    submission.nickname !== member.nickname.trim() ||
    submission.email !== (member.email ?? '') ||
    submission.mobile !== member.mobile
  )
}

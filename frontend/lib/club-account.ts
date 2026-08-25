/**
 * What the club holds about the signed-in account, as rows a screen can render.
 *
 * Pure, and the session is always an argument. The rules that matter here are small but they are
 * rules, and each of them has been got wrong somewhere before:
 *
 * * a blank field is *said to be* blank rather than rendered as an empty line, so a member can
 *   tell "we hold nothing" from "the page failed to draw it";
 * * an erased account keeps its row with every name cleared and no email address at all, so every
 *   field here has to survive being empty — it cannot sign in, so this is a contract rather than a
 *   screen anyone will see, and the contract is what stops a future caller assuming otherwise;
 * * the identity number is not here and must never be. It is encrypted at rest, it is not in
 *   `UserOut`, and there is nothing on a home page that needs it.
 */

import type { User } from './api'
import { DETAILS_CARD, MEMBERSHIP_CARD } from './club-content'

/** One labelled line in the details card. */
export type DetailRow = {
  readonly key: string
  readonly label: string
  /** The value, or `null` when the club holds nothing. Never an empty string. */
  readonly value: string | null
}

/**
 * A date as a South African reader writes it: 15 March 1990.
 *
 * Takes the stored ISO value and nothing else — no ambient clock, in keeping with the rest of
 * `lib/`. An unparseable value reads as nothing held rather than as `Invalid Date`, because a
 * member should never be shown the string a date library produces when it gives up.
 */
export const formatIsoDate = (iso: string | null): string | null => {
  if (!iso) return null

  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return null

  return parsed.toLocaleDateString('en-ZA', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

/** Trimmed, or `null`. The one place a blank becomes "nothing held". */
const held = (value: string | null | undefined): string | null => {
  const trimmed = (value ?? '').trim()
  return trimmed.length > 0 ? trimmed : null
}

/**
 * The full name, or `null` when neither part is on file.
 *
 * Joined here rather than in the component so a member with only one of the two still gets a
 * sensible line instead of a stray space.
 */
export const fullName = (user: User): string | null =>
  held([held(user.first_name), held(user.last_name)].filter(Boolean).join(' '))

/**
 * The details card, in reading order.
 *
 * Name first, because it is what the member checks. Date of birth last, because it is the one
 * thing on here nobody can change by asking.
 */
export const detailRows = (user: User): readonly DetailRow[] => [
  { key: 'name', label: DETAILS_CARD.labels.name, value: fullName(user) },
  { key: 'nickname', label: DETAILS_CARD.labels.nickname, value: held(user.nickname) },
  { key: 'email', label: DETAILS_CARD.labels.email, value: held(user.email) },
  { key: 'mobile', label: DETAILS_CARD.labels.mobile, value: held(user.mobile) },
  {
    key: 'dateOfBirth',
    label: DETAILS_CARD.labels.dateOfBirth,
    value: formatIsoDate(user.date_of_birth),
  },
]

/** The standing of the membership, as a label and the sentence that explains it. */
export type MembershipStanding = {
  readonly label: string
  readonly note: string
}

/**
 * How the account stands, from its status.
 *
 * Only `active` can hold a session, so every other branch describes a state the browser should
 * not be able to reach. They are all written out anyway: `status` is reportable rather than
 * enforceable here, and a screen that renders nothing for an unexpected value is a screen that
 * looks broken at the exact moment something has gone wrong.
 */
export const membershipStanding = (status: User['status']): MembershipStanding => ({
  label: MEMBERSHIP_CARD.statusLabels[status],
  note: MEMBERSHIP_CARD.statusNotes[status],
})

/**
 * What to greet this account by.
 *
 * `display_name` is Django's own answer — nickname, then full name, then email address — so this
 * only guards the case where every one of those was blank. That is an erased account, which cannot
 * sign in; the fallback exists so the greeting degrades to a sentence rather than to "Welcome
 * back, ".
 */
export const greetingName = (user: User): string | null => held(user.display_name)

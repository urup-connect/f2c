/**
 * How a profile reads on screen when there is no photograph, and how its two read-only fields do.
 *
 * Pure, and separate from `lib/profile.ts` because that module is the form's rules and this is
 * presentation. The split matters for one reason: everything here takes a record and returns a
 * string, so it can be called from a Server Component, and the profile screen renders in the first
 * paint rather than filling in after it.
 *
 * No ambient clock and no locale detection. Dates are formatted for a South African reader
 * explicitly, the same way `club-account.ts` does it, because the club is South African and a
 * browser set to another locale would otherwise render the club's own record in a foreign format.
 */

import { PROFILE_COPY } from './club-content'

/** The literal the API sends for a record whose identity number will not decrypt. */
export const UNREADABLE_ID_NUMBER = 'UNREADABLE'

/**
 * One or two letters standing in for a photograph.
 *
 * From the names when there are any, and from the nickname or address when there are not. It never
 * answers an empty string: a blank circle where a face should be reads as an image that failed to
 * load, and the whole point of initials is to be recognisably deliberate.
 *
 * Uses the first *code point* rather than the first UTF-16 unit, so a name outside the Basic
 * Multilingual Plane yields a character rather than half of one.
 */
export const initials = (profile: {
  first_name: string
  last_name: string
  nickname: string
  email: string | null
}): string => {
  const first = firstLetter(profile.first_name)
  const last = firstLetter(profile.last_name)

  if (first && last) return `${first}${last}`
  if (first || last) return first || last

  // An erased account has none of these, which is why the last resort is a letter rather than a
  // name: it cannot sign in, so nobody sees it, and the contract still has to return something.
  return firstLetter(profile.nickname) || firstLetter(profile.email ?? '') || '·'
}

const firstLetter = (value: string): string => {
  const trimmed = value.trim()
  if (trimmed.length === 0) return ''

  return [...trimmed][0].toUpperCase()
}

const DATE = new Intl.DateTimeFormat('en-ZA', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  timeZone: 'UTC',
  calendar: 'gregory',
})

/**
 * A date as a South African reader writes it: 15 March 1990.
 *
 * `timeZone: 'UTC'` is the part that matters. An ISO date has no time in it, so `new Date` reads it
 * as midnight UTC — and formatted in a timezone behind UTC that is the previous day. A member in
 * Johannesburg would never see it, and one travelling would see their own birthday move.
 *
 * An unparseable value reads as nothing held rather than as `Invalid Date`. A member should never be
 * shown the string a date library produces when it gives up.
 */
export const formatProfileDate = (iso: string | null): string | null => {
  if (!iso) return null

  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return null

  return DATE.format(parsed)
}

/** One labelled, read-only line on the identity card. */
export type IdentityLine = {
  readonly key: string
  readonly label: string
  /** The value, or `null` when the club holds nothing. Never an empty string. */
  readonly value: string | null
  /** A sentence under the value, when there is something true to say about it. */
  readonly note: string | null
}

/**
 * The two fields taken from an identity document, as lines a screen can render.
 *
 * Both are reported as *absent* rather than blank when the club holds nothing, for the reason
 * `club-account.ts` gives at length: an empty line reads as a page that failed to draw.
 *
 * The identity number has three states, not two, and conflating any of them would mislead. Held and
 * readable shows the mask. Not held shows "not on file". Held and *unreadable* — a key or integrity
 * problem — says so, because a member told the club holds no document when it holds one it cannot
 * read will go and send it again for no reason.
 */
export const identityLines = (profile: {
  date_of_birth: string | null
  date_of_birth_verified_at: string | null
  has_id_number: boolean
  id_number_masked: string
}): readonly IdentityLine[] => {
  const copy = PROFILE_COPY.identity

  return [
    {
      key: 'dateOfBirth',
      label: copy.dateOfBirthLabel,
      value: formatProfileDate(profile.date_of_birth),
      /*
       * Whether anybody has checked the date against a document, said on the line it qualifies.
       * Registration does not check one -- a number that passes its check digit is a number that is
       * not a typo -- so unverified is the normal state and the wording must not read as a fault.
       */
      note:
        profile.date_of_birth === null
          ? null
          : profile.date_of_birth_verified_at === null
            ? copy.unverified
            : `${copy.verifiedLabel}: ${formatProfileDate(profile.date_of_birth_verified_at)}`,
    },
    {
      key: 'idNumber',
      label: copy.idNumberLabel,
      value: identityNumberValue(profile),
      note: identityNumberNote(profile),
    },
  ]
}

const identityNumberValue = (profile: {
  has_id_number: boolean
  id_number_masked: string
}): string | null => {
  if (!profile.has_id_number) return null
  if (profile.id_number_masked === UNREADABLE_ID_NUMBER) return null

  // Trusted as the API sent it. Masking here as well would be a second implementation of a rule
  // that has already run, and the two would eventually disagree about how much to show.
  return profile.id_number_masked || null
}

const identityNumberNote = (profile: {
  has_id_number: boolean
  id_number_masked: string
}): string | null => {
  const copy = PROFILE_COPY.identity

  if (!profile.has_id_number) return null
  if (profile.id_number_masked === UNREADABLE_ID_NUMBER) return copy.unreadable

  return copy.idNumberNote
}

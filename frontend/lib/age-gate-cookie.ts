/**
 * The carrier that gets an asserted date of birth from the age gate to sign-up.
 *
 * There is no session and no database yet, so the value travels in a cookie: `httpOnly`, so page
 * scripts cannot read it, short-lived, because it exists to cross two screens and nothing more,
 * and re-validated on every read.
 *
 * Deliberately unsigned. A signature would stop a visitor forging a date they could equally have
 * typed into the gate, which is no protection at all; what matters is that the rule is applied
 * again on the way out. Signing arrives free when Better Auth introduces `AUTH_SECRET` — see
 * design/features/age-gate-before-sign-up.md sections 6.5 and 11.
 */

import { fromIsoDate, hasReachedMinimumAge, sastToday, toIsoDate } from './age-gate'
import type { CalendarDate } from './age-gate'
import type { SiteConfig } from './site'

/** Names the gate, never what it holds: cookie names show up in developer tools and logs. */
export const AGE_PASS_COOKIE = 'cc_age_pass'

export const AGE_PASS_MAX_AGE_SECONDS = 30 * 60

/** Bumped if the value's shape ever changes, so an old cookie is refused rather than misread. */
const VERSION = 'v1'

const SEPARATOR = '|'

export type AgePass = {
  readonly dateOfBirth: CalendarDate
  /** When the visitor asserted it. UTC, ISO 8601. */
  readonly assertedAt: string
}

export const serialiseAgePass = ({ dateOfBirth, assertedAt }: AgePass) =>
  [VERSION, toIsoDate(dateOfBirth), assertedAt].join(SEPARATOR)

/** Exactly what `Date.prototype.toISOString` produces, and nothing looser. */
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/

/**
 * Reads a pass, or returns `null` for anything that cannot be trusted: a malformed or
 * wrong-version value, an assertion made in the future or outside its window, or a date of birth
 * that fails the eighteen-year rule when the rule is applied again now.
 */
export const readAgePass = (value: string | undefined, now: Date): AgePass | null => {
  if (!value) return null

  const parts = value.split(SEPARATOR)
  if (parts.length !== 3) return null

  const [version, isoDate, assertedAt] = parts
  if (version !== VERSION) return null

  const dateOfBirth = fromIsoDate(isoDate)
  if (!dateOfBirth) return null

  if (!UTC_INSTANT.test(assertedAt)) return null

  const asserted = Date.parse(assertedAt)
  if (Number.isNaN(asserted)) return null

  const elapsed = now.getTime() - asserted
  if (elapsed < 0 || elapsed > AGE_PASS_MAX_AGE_SECONDS * 1000) return null

  if (!hasReachedMinimumAge(dateOfBirth, sastToday(now))) return null

  return { dateOfBirth, assertedAt }
}

export type AgePassCookieOptions = {
  readonly httpOnly: true
  readonly sameSite: 'lax'
  readonly path: '/'
  readonly secure: boolean
  readonly maxAge: number
}

/**
 * `secure` follows the scheme the site is actually served on rather than the environment name.
 * Marking a cookie `Secure` on a plain-http local server means the browser never sends it back,
 * which looks exactly like a broken gate.
 */
export const agePassCookieOptions = ({ siteUrl }: SiteConfig): AgePassCookieOptions => ({
  httpOnly: true,
  sameSite: 'lax',
  path: '/',
  secure: siteUrl.startsWith('https:'),
  maxAge: AGE_PASS_MAX_AGE_SECONDS,
})

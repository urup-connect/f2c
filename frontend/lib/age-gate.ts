/**
 * The eighteen-year rule, as pure logic.
 *
 * The current instant is always an argument, never read from inside: a date boundary is then a
 * test rather than something that only misbehaves at midnight in production.
 *
 * The rule is calendar arithmetic, not milliseconds. Adding eighteen years to a `Date` invites
 * a time zone, an hour that does not exist across a clock change, and a 29 February that
 * silently becomes 1 March in a different place from where we meant it to. Comparing
 * `(year + 18, month, day)` part by part has none of that.
 *
 * See design/features/age-gate-before-sign-up.md sections 5 and 6.5.
 */

export const MINIMUM_AGE_YEARS = 18

/** South African Standard Time. UTC+2 all year: the country observes no daylight saving. */
export const SAST_TIME_ZONE = 'Africa/Johannesburg'

/** Beyond this, the visitor has mistyped the year rather than lived that long. */
const MAX_PLAUSIBLE_AGE_YEARS = 120

/** A date on a calendar. No time, no zone — a birthday is not an instant. */
export type CalendarDate = {
  readonly year: number
  readonly month: number
  readonly day: number
}

/** What the visitor typed, exactly as the form hands it over. */
export type DateOfBirthInput = {
  readonly day: string
  readonly month: string
  readonly year: string
}

export type AgeCheckRefusal =
  | 'incomplete'
  | 'not-a-number'
  | 'not-a-real-date'
  | 'in-the-future'
  | 'implausible'
  | 'under-age'

/**
 * Every reason the check can refuse, as values.
 *
 * A refusal travels back to the gate in the query string — a reason code, never the date the
 * visitor typed — so it has to be narrowed from an arbitrary string on the way in.
 */
export const AGE_CHECK_REFUSALS = [
  'incomplete',
  'not-a-number',
  'not-a-real-date',
  'in-the-future',
  'implausible',
  'under-age',
] as const satisfies readonly AgeCheckRefusal[]

export const isAgeCheckRefusal = (value: unknown): value is AgeCheckRefusal =>
  typeof value === 'string' &&
  AGE_CHECK_REFUSALS.some((refusal): boolean => refusal === value)

export type AgeCheckOutcome =
  | { readonly status: 'pass'; readonly dateOfBirth: CalendarDate }
  | { readonly status: 'refused'; readonly reason: AgeCheckRefusal }

/*
 * Constructed once. `en-CA` is not a display choice: its numeric format is ISO-ordered, and the
 * parts are read by type anyway, so the locale only has to be one that yields Gregorian
 * numerals. The zone is what matters, and it is explicit.
 */
const SAST_DATE = new Intl.DateTimeFormat('en-CA', {
  timeZone: SAST_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  numberingSystem: 'latn',
  calendar: 'gregory',
})

const part = (parts: readonly Intl.DateTimeFormatPart[], type: Intl.DateTimeFormatPartTypes) => {
  const found = parts.find((candidate) => candidate.type === type)
  if (!found) throw new Error(`The SAST date formatter produced no ${type} part`)

  return Number(found.value)
}

/**
 * Today's date on a South African calendar, derived from an instant.
 *
 * Throws if handed an invalid `Date`, which is a programming error rather than visitor input:
 * every caller passes `new Date()` or a fixed test instant.
 */
export const sastToday = (now: Date): CalendarDate => {
  const parts = SAST_DATE.formatToParts(now)

  return {
    year: part(parts, 'year'),
    month: part(parts, 'month'),
    day: part(parts, 'day'),
  }
}

const isLeapYear = (year: number) => (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31] as const

const daysInMonth = (year: number, month: number) =>
  month === 2 && isLeapYear(year) ? 29 : DAYS_IN_MONTH[month - 1]

const isRealDate = ({ year, month, day }: CalendarDate) => {
  // A four-digit year is required, so a visitor typing "94" is corrected rather than aged out.
  if (year < 1000 || year > 9999) return false
  if (month < 1 || month > 12) return false

  const limit = daysInMonth(year, month)

  return limit !== undefined && day >= 1 && day <= limit
}

/** Negative when `a` is earlier, zero when they are the same day, positive when later. */
const compare = (a: CalendarDate, b: CalendarDate) =>
  a.year - b.year || a.month - b.month || a.day - b.day

/**
 * True when `dateOfBirth` plus eighteen years falls on or before `today`.
 *
 * A 29 February birthday has no eighteenth birthday in a common year, and comparing parts
 * places it on 1 March — the visitor waits one more day, which is the conservative side of a
 * legal convention this code should not be inventing. See section 10, risk 1.
 */
export const hasReachedMinimumAge = (dateOfBirth: CalendarDate, today: CalendarDate) =>
  compare({ ...dateOfBirth, year: dateOfBirth.year + MINIMUM_AGE_YEARS }, today) <= 0

/** Digits only, so no sign, no decimal point, no exponent and no non-Latin numeral. */
const DIGITS = /^\d{1,4}$/

/**
 * The whole gate decision, from raw form strings to an outcome. Never throws for any input.
 *
 * The refusals are ordered so the visitor is told the most useful thing first: what is missing,
 * then what is not a number, then what is not a date, then what is wrong with the date itself.
 */
export const checkAge = (input: DateOfBirthInput, now: Date): AgeCheckOutcome => {
  const parts = [input.year, input.month, input.day].map((value) => value.trim())

  if (parts.some((value) => value.length === 0)) {
    return { status: 'refused', reason: 'incomplete' }
  }

  if (parts.some((value) => !DIGITS.test(value))) {
    return { status: 'refused', reason: 'not-a-number' }
  }

  const [year, month, day] = parts.map(Number)
  const dateOfBirth = { year, month, day }

  if (!isRealDate(dateOfBirth)) {
    return { status: 'refused', reason: 'not-a-real-date' }
  }

  const today = sastToday(now)

  if (compare(dateOfBirth, today) > 0) {
    return { status: 'refused', reason: 'in-the-future' }
  }

  if (today.year - year > MAX_PLAUSIBLE_AGE_YEARS) {
    return { status: 'refused', reason: 'implausible' }
  }

  if (!hasReachedMinimumAge(dateOfBirth, today)) {
    return { status: 'refused', reason: 'under-age' }
  }

  return { status: 'pass', dateOfBirth }
}

const pad = (value: number, width: number) => String(value).padStart(width, '0')

/** `YYYY-MM-DD`, for storage and for the pass cookie. */
export const toIsoDate = ({ year, month, day }: CalendarDate) =>
  `${pad(year, 4)}-${pad(month, 2)}-${pad(day, 2)}`

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/

/** The inverse, strictly. `null` for anything that is not exactly an ISO calendar date. */
export const fromIsoDate = (value: string): CalendarDate | null => {
  const match = ISO_DATE.exec(value.trim())
  if (!match) return null

  const [year, month, day] = match.slice(1).map(Number)
  const date = { year, month, day }

  return isRealDate(date) ? date : null
}

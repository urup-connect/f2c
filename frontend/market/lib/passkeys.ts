/**
 * The rules around an account's passkeys, separately from the card that renders them.
 *
 * A copy of the club's module, and one of the strongest candidates for `packages/`: nothing in here
 * knows what is being sold. The only edit is where the wording comes from.
 */

import type { Passkey } from './api'
import { apiProblem, passkeyProblem } from './sign-in'
import { PASSKEYS_CARD } from './store-content'

/**
 * The `DOMException` names a WebAuthn ceremony throws.
 *
 * Listed rather than inferred, because the two sources of failure during enrolment read completely
 * differently: the authenticator refusing is about *this device*, and Django refusing is about the
 * account. Deciding which by the name is the only reliable signal — the messages are
 * browser-specific and change between versions.
 */
export const WEBAUTHN_ERROR_NAMES: ReadonlySet<string> = new Set([
  'NotAllowedError',
  'InvalidStateError',
  'SecurityError',
  'AbortError',
  'ConstraintError',
  'NotSupportedError',
  'UnknownError',
])

/**
 * What to say when enrolling a passkey did not work.
 *
 * The authenticator's failures get the device wording; everything else — an API refusal, a network
 * failure — gets the wording for that. Neither ever shows what the browser or the runtime said.
 */
export const enrolmentProblem = (error: unknown): string =>
  error instanceof Error && WEBAUTHN_ERROR_NAMES.has(error.name)
    ? passkeyProblem(error)
    : apiProblem(error)

/**
 * A default label for a new passkey, from a user-agent string.
 *
 * The string is a **parameter**, never read from `navigator` in here — so the Windows case is a test
 * rather than something that only misbehaves on somebody else's laptop.
 *
 * User-agent sniffing is unreliable by nature and this is the one place it is acceptable: the answer
 * is a suggestion the customer can overwrite, and being wrong costs them a label they did not want
 * rather than a credential that does not work.
 */
export const suggestPasskeyName = (userAgent: string): string => {
  if (/iPhone|iPad/.test(userAgent)) return 'iPhone or iPad'
  if (/Android/.test(userAgent)) return 'Android device'
  if (/Macintosh/.test(userAgent)) return 'Mac'
  if (/Windows/.test(userAgent)) return 'Windows PC'
  return 'This device'
}

/** Django truncates at 64. Doing it here too means the customer sees what will be stored. */
export const PASSKEY_NAME_MAX = 64

export const trimPasskeyName = (value: string): string => value.slice(0, PASSKEY_NAME_MAX)

/**
 * The name to send: what was typed, or the suggestion when nothing was.
 *
 * Django would fall back to the literal string "Passkey" for a blank name, which tells somebody with
 * three of them nothing at all.
 */
export const passkeyNameToSend = (typed: string, userAgent: string): string =>
  trimPasskeyName(typed.trim() || suggestPasskeyName(userAgent))

/**
 * When a passkey was added and last used, as one line.
 *
 * A passkey that has never been used says so rather than showing a blank or an epoch date — somebody
 * reading "Last used 1 January 1970" would reasonably conclude the store had lost track of
 * something.
 */
export const passkeyTimeline = (passkey: Passkey): string => {
  const added = formatDay(passkey.created_at)
  const used = passkey.last_used_at ? formatDay(passkey.last_used_at) : null

  const addedPart = added ? `${PASSKEYS_CARD.addedPrefix} ${added}` : PASSKEYS_CARD.addedPrefix

  const usedPart = used ? `${PASSKEYS_CARD.lastUsedPrefix} ${used}` : PASSKEYS_CARD.neverUsed

  return `${addedPart} · ${usedPart}`
}

/**
 * A short date, or `null` when the value cannot be read as one.
 *
 * Formatted for a South African reader explicitly rather than from the browser's locale: the store is
 * South African, and a browser set to another locale would otherwise render the store's own record in
 * a foreign format.
 */
const formatDay = (iso: string): string | null => {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return null

  return parsed.toLocaleDateString('en-ZA', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/**
 * The handle a member is given when something on our side failed.
 *
 * A fault the visitor cannot act on still has to be reportable, and the report has to be possible
 * without them quoting anything about themselves. So a failure mints eight random hex characters,
 * the cause is logged against them on the server, and the reference is the only part that reaches
 * the screen. A member says "reference 3f9a1c04" and support reads the line; nobody has to say a
 * name, an address or an identity number to describe what went wrong.
 *
 * It carries no information of its own, and that is the point. It is not derived from the request,
 * the time, the field or the value — a reference computed from any of those would be a value in a
 * query string that could be walked backwards. It means nothing except "this log line".
 *
 * Short on purpose: a member reads it off a screen, possibly aloud. Eight hex characters is more
 * than enough to find one line in a day of logs and few enough to be quoted correctly.
 *
 * See design/features/sign-up.md section 7.
 */

/** Lower-case hex only, and exactly eight of it. Anything else did not come from here. */
const REFERENCE = /^[0-9a-f]{8}$/

const HEX_BYTES = 4

/**
 * A fresh reference. Safe on either runtime: `crypto` is global in the browser and in Node.
 *
 * `getRandomValues` rather than anything ordered. A sequence would tell a reader how many failures
 * came before theirs, which is a load metric we have no reason to publish on an error screen.
 */
export const newErrorReference = (): string => {
  const bytes = new Uint8Array(HEX_BYTES)

  crypto.getRandomValues(bytes)

  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/**
 * A reference from somewhere untrusted — a query string, a response body — or null.
 *
 * Strict, because this value is rendered. Anything that is not eight hex characters is dropped
 * rather than shown, so a hand-typed or doctored parameter cannot put arbitrary text on the page
 * beside our own wording.
 *
 * A repeated query parameter arrives as a list rather than a string and is read as no reference at
 * all, the same way `parseMemberDetailsRefusals` treats one.
 */
export const readErrorReference = (value: unknown): string | null =>
  typeof value === 'string' && REFERENCE.test(value) ? value : null

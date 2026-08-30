/**
 * An email address, as pure logic.
 *
 * Deliberately not RFC 5322. That grammar admits quoted local parts, comments and bracketed IP
 * literals, none of which a member is going to type and all of which widen the surface for no
 * benefit. What this catches is a typo, and what it guarantees is one normalised stored form.
 *
 * Nothing here proves an address can receive mail. Only sending to it does, which is what the
 * emailed sign-in code will do — see design/features/passkey-auth-with-email-otp.md.
 *
 * Lower-cased whole, local part included. The RFC allows a case-sensitive local part; no mail
 * provider a member is likely to use treats it that way, and one address must have exactly one
 * stored form or the same person becomes two members.
 *
 * See design/features/member-details-at-sign-up.md section 6.2.
 */

/** RFC 5321: the whole address in a forward path. */
export const EMAIL_MAX_LENGTH = 254

/** RFC 5321: the part before the at sign. */
export const EMAIL_LOCAL_MAX_LENGTH = 64

export type EmailRefusal = 'missing' | 'malformed' | 'too-long'

export const EMAIL_REFUSALS = [
  'missing',
  'malformed',
  'too-long',
] as const satisfies readonly EmailRefusal[]

export type EmailCheck =
  | { readonly status: 'valid'; readonly email: string }
  | { readonly status: 'invalid'; readonly reason: EmailRefusal }

/*
 * Built from named parts, because one long expression is unreviewable.
 *
 * `atom` is the unquoted local-part character set. Dots may separate atoms but may not lead,
 * trail or double up. A domain label starts and ends alphanumeric and may carry hyphens inside,
 * there is at least one label before the last, and the last is two or more letters — which
 * refuses `example` with no dot and `example.c` alike.
 */
const ATOM = "[a-z0-9!#$%&'*+/=?^_`{|}~-]+"
const LOCAL = `${ATOM}(?:\\.${ATOM})*`
const LABEL = '[a-z0-9](?:[a-z0-9-]*[a-z0-9])?'
const DOMAIN = `(?:${LABEL}\\.)+[a-z]{2,}`

const ADDRESS = new RegExp(`^${LOCAL}@${DOMAIN}$`)

const invalid = (reason: EmailRefusal): EmailCheck => ({ status: 'invalid', reason })

/** Trimmed and lower-cased. The one form that is stored and compared. */
export const normaliseEmailAddress = (input: string) => input.trim().toLowerCase()

/**
 * The whole rule. Never throws for any input.
 *
 * Shape is checked before length: an address over the limit is at least an address, and being
 * told it is too long is only useful once it is one.
 */
export const checkEmailAddress = (input: string): EmailCheck => {
  const email = normaliseEmailAddress(input)

  if (email.length === 0) return invalid('missing')
  if (!ADDRESS.test(email)) return invalid('malformed')

  const [local] = email.split('@')

  if (local.length > EMAIL_LOCAL_MAX_LENGTH) return invalid('too-long')
  if (email.length > EMAIL_MAX_LENGTH) return invalid('too-long')

  return { status: 'valid', email }
}

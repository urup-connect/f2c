/**
 * Every word on the sign-in screen.
 *
 * Held here rather than in the form for the same reason as the landing copy: it is fixed club
 * content, the sign-off pass has one file to read, and the compliance tests get a corpus.
 *
 * One rule governs all of it, and it is the design constraint of the whole feature: **nothing here
 * may say whether an address belongs to a member.** Django answers an unknown address exactly as it
 * answers a real one, and copy that said "we have sent you a code" would give away in words what
 * the API is careful not to give away in bytes. Hence the conditional wording throughout — *if that
 * address belongs to a member*. See design/features/authentication.md section 3.
 */

export const SIGN_IN = {
  title: 'Log In',
  standfirst:
    'No password. Your device can prove who you are, or the club can email you a code.',

  emailLabel: 'Email address',
  emailContinue: 'Continue',
  emailChecking: 'Checking…',

  codeLabel: 'Sign-in code',
  /** Completed with the address at the call site, so this file holds no interpolation. */
  codeHintPrefix: 'Six digits, sent to',
  codeHintSuffix: 'Valid for five minutes.',
  codeSubmit: 'Sign in',
  codeChecking: 'Checking…',

  requestCode: 'Email me a code',
  /** Offered instead of the above once a passkey attempt has failed on this device. */
  requestCodeInstead: 'Email me a code instead',
  resend: 'Send a new code',
  /** Completed with the seconds remaining. */
  resendWaitingPrefix: 'Send a new code in',
  startOver: 'Use a different address',

  back: 'Back to Cultivators Collective',
} as const

/**
 * What the club says when something goes wrong.
 *
 * Every one of these is deliberately vague about *who*. A message that distinguished "no such
 * account" from "wrong code" would be the disclosure the API refuses to make.
 */
export const SIGN_IN_PROBLEMS = {
  /**
   * The browser gives the same `NotAllowedError` whether the member dismissed the prompt or no
   * credential matched, so this cannot tell the two apart — hence wording that covers both.
   */
  passkeyNotAllowed:
    'Passkey sign-in was cancelled, or no passkey on this device matched.',
  passkeyInvalidState: "This device's passkey is not registered to that account.",
  passkeySecurity: 'Passkeys need a secure connection. Sign in at localhost or over HTTPS.',
  passkeyOther: 'Passkey sign-in did not complete on this device.',
  unreachable: 'Could not reach the club. Please try again.',
} as const

/**
 * Said when a code has been sent — or would have been, had the address belonged to anybody.
 *
 * Completed with the address at the call site. The conditional is the whole point.
 */
export const CODE_SENT_PREFIX = 'If'
export const CODE_SENT_SUFFIX = 'belongs to a member, a code is on its way.'

/** Every string on this screen, flattened, for the compliance corpus. */
export const ALL_SIGN_IN_COPY: readonly string[] = [
  ...Object.values(SIGN_IN),
  ...Object.values(SIGN_IN_PROBLEMS),
  CODE_SENT_PREFIX,
  CODE_SENT_SUFFIX,
]

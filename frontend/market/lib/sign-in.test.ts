import { describe, expect, test } from 'vitest'
import { ApiError } from './api'
import {
  ACCOUNT_HOME_PATH,
  CODE_LENGTH,
  RESEND_COOLDOWN_SECONDS,
  apiProblem,
  destinationAfterSignIn,
  digitsOnly,
  isSafeNext,
  passkeyProblem,
  signInPath,
} from './sign-in'
import { CODE_SENT_PREFIX, CODE_SENT_SUFFIX, SIGN_IN_PROBLEMS } from './sign-in-content'

/** A DOMException by any other name: what the browser actually throws. */
const domError = (name: string): Error => {
  const error = new Error('the browser said something developer-facing')
  error.name = name
  return error
}

describe('the shape of a code', () => {
  test('is six digits, as Django issues', () => {
    expect(CODE_LENGTH).toBe(6)
  })

  test('cannot be asked for again immediately', () => {
    expect(RESEND_COOLDOWN_SECONDS).toBeGreaterThan(0)
  })
})

describe('digitsOnly', () => {
  test('keeps the digits and drops everything else, so a pasted code still works', () => {
    expect(digitsOnly('12 34-56')).toBe('123456')
    expect(digitsOnly('Your code is 123456')).toBe('123456')
  })

  test('stops at six', () => {
    expect(digitsOnly('1234567890')).toBe('123456')
  })

  test('has nothing to say about nothing', () => {
    expect(digitsOnly('')).toBe('')
    expect(digitsOnly('no digits here')).toBe('')
  })
})

describe('isSafeNext', () => {
  test('follows a path on this origin', () => {
    expect(isSafeNext('/account')).toBe(true)
    expect(isSafeNext('/account/details?saved=1')).toBe(true)
  })

  test('refuses a protocol-relative URL, which leaves the site', () => {
    // The open redirect this closes: it starts with a slash and is still off-site.
    expect(isSafeNext('//evil.example.com')).toBe(false)
  })

  test('refuses anything absolute', () => {
    expect(isSafeNext('https://evil.example.com')).toBe(false)
    expect(isSafeNext('http://localhost:3001/account')).toBe(false)
  })

  test('refuses nothing at all', () => {
    expect(isSafeNext(null)).toBe(false)
    expect(isSafeNext('')).toBe(false)
  })
})

describe('destinationAfterSignIn', () => {
  test('follows a safe next', () => {
    expect(destinationAfterSignIn('/account/security')).toBe('/account/security')
  })

  test('lands on the account area when there is no next', () => {
    // One area, not three. The club chooses between homes by role; the store has one customer.
    expect(destinationAfterSignIn(null)).toBe(ACCOUNT_HOME_PATH)
  })

  test('drops an unsafe next rather than following it', () => {
    expect(destinationAfterSignIn('//evil.example.com')).toBe(ACCOUNT_HOME_PATH)
  })
})

describe('signInPath', () => {
  test('carries where the visitor was going, encoded', () => {
    expect(signInPath('/account/details')).toBe('/sign-in?next=%2Faccount%2Fdetails')
  })

  test('drops an unsafe value rather than escaping it', () => {
    expect(signInPath('//evil.example.com')).toBe('/sign-in')
    expect(signInPath(null)).toBe('/sign-in')
    expect(signInPath()).toBe('/sign-in')
  })
})

describe('passkeyProblem', () => {
  test('covers a cancelled prompt and an unmatched credential in one sentence', () => {
    // The browser cannot tell the two apart, so neither can the wording.
    expect(passkeyProblem(domError('NotAllowedError'))).toBe(SIGN_IN_PROBLEMS.passkeyNotAllowed)
  })

  test('names the device when the credential belongs to another account', () => {
    expect(passkeyProblem(domError('InvalidStateError'))).toBe(SIGN_IN_PROBLEMS.passkeyInvalidState)
  })

  test('says what to do about an insecure origin', () => {
    expect(passkeyProblem(domError('SecurityError'))).toBe(SIGN_IN_PROBLEMS.passkeySecurity)
  })

  test('never shows the browser its own developer-facing message', () => {
    expect(passkeyProblem(domError('WhateverError'))).toBe(SIGN_IN_PROBLEMS.passkeyOther)
    expect(passkeyProblem('a string')).toBe(SIGN_IN_PROBLEMS.passkeyOther)
  })
})

describe('apiProblem', () => {
  test("shows Django's own sentence, which the endpoints write to be read", () => {
    expect(apiProblem(new ApiError(429, 'Too many attempts. Try again in a minute.'))).toBe(
      'Too many attempts. Try again in a minute.',
    )
  })

  test('falls back to our wording for anything that is not an API refusal', () => {
    expect(apiProblem(new TypeError('Failed to fetch'))).toBe(SIGN_IN_PROBLEMS.unreachable)
    expect(apiProblem(new ApiError(500, '   '))).toBe(SIGN_IN_PROBLEMS.unreachable)
  })
})

describe('what the copy may not say', () => {
  /*
   * The disclosure rule: Django answers an unknown address exactly as it answers a real one, so the
   * copy must not give away in words what the API withholds in bytes.
   *
   * `passkeyInvalidState` is exempt, and the exemption is the interesting part. It is reachable only
   * *after* Django has issued a WebAuthn challenge, which it does only for an address that has an
   * account with a credential on it — so by the time that sentence can appear, the existence of the
   * account has already been established to somebody holding the authenticator. Every message below
   * can be reached with an address typed by anybody, and none of them may say whether it is known.
   */
  const reachableBeforeAnythingIsProven = [
    SIGN_IN_PROBLEMS.passkeyNotAllowed,
    SIGN_IN_PROBLEMS.passkeySecurity,
    SIGN_IN_PROBLEMS.passkeyOther,
    SIGN_IN_PROBLEMS.unreachable,
  ]

  test.each(['no such', 'not registered', 'unknown address', 'no account'])(
    'never says "%s"',
    (phrase) => {
      const everything = reachableBeforeAnythingIsProven.join(' ').toLowerCase()

      expect(everything).not.toContain(phrase)
    },
  )

  test('says a code is on its way conditionally, never that one was sent', () => {
    // The wording is completed with the address at the call site: "If <address> belongs to an
    // account, a code is on its way."
    expect(`${CODE_SENT_PREFIX} ${CODE_SENT_SUFFIX}`.toLowerCase()).toContain('if')
    expect(`${CODE_SENT_PREFIX} ${CODE_SENT_SUFFIX}`.toLowerCase()).toContain('belongs to an account')
  })
})

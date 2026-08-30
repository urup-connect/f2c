import { describe, expect, test } from 'vitest'
import { ApiError } from './api'
import {
  CODE_LENGTH,
  RESEND_COOLDOWN_SECONDS,
  apiProblem,
  destinationAfterSignIn,
  digitsOnly,
  isSafeNext,
  passkeyProblem,
  signInPath,
} from './sign-in'
import { SIGN_IN_PROBLEMS } from './sign-in-content'

/* design/features/authentication.md sections 2 and 3. */

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
  test('keeps the digits', () => {
    expect(digitsOnly('123456')).toBe('123456')
  })

  test('drops everything else, so a pasted code still works', () => {
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
    expect(isSafeNext('/member')).toBe(true)
    expect(isSafeNext('/cultivator?welcome=1')).toBe(true)
  })

  test('refuses a protocol-relative URL, which leaves the site', () => {
    // Starts with a slash and is still off-site. This is the open redirect.
    expect(isSafeNext('//evil.example.com')).toBe(false)
  })

  test('refuses anything absolute', () => {
    expect(isSafeNext('https://evil.example.com')).toBe(false)
    expect(isSafeNext('http://localhost:3000/member')).toBe(false)
  })

  test('refuses nothing at all', () => {
    expect(isSafeNext(null)).toBe(false)
    expect(isSafeNext('')).toBe(false)
  })
})

describe('destinationAfterSignIn', () => {
  test('sends each role to its own home when there is no next', () => {
    expect(destinationAfterSignIn(null, 'member')).toBe('/member')
    expect(destinationAfterSignIn(null, 'cultivator')).toBe('/cultivator')
    expect(destinationAfterSignIn(null, 'admin')).toBe('/admin')
  })

  test('follows a safe next in preference to the role home', () => {
    expect(destinationAfterSignIn('/member/plants', 'member')).toBe('/member/plants')
  })

  test('ignores a next that would leave the site', () => {
    expect(destinationAfterSignIn('//evil.example.com', 'member')).toBe('/member')
    expect(destinationAfterSignIn('https://evil.example.com', 'admin')).toBe('/admin')
  })

  test('follows a next into another role area, and lets the server correct it', () => {
    // Deliberate. The club area guards itself and will send them to their own home.
    // A second check here could disagree with the one that actually decides.
    expect(destinationAfterSignIn('/admin', 'member')).toBe('/admin')
  })

  test('sends a sharing member to the front door, having no area of their own', () => {
    expect(destinationAfterSignIn(null, 'sharing_member' as never)).toBe('/')
  })
})

describe('signInPath', () => {
  test('sends a visitor to sign in', () => {
    expect(signInPath()).toBe('/login')
  })

  test('carries where they were going, so they arrive there afterwards', () => {
    expect(signInPath('/cultivator')).toBe('/login?next=%2Fcultivator')
  })

  test('encodes the path rather than pasting it in', () => {
    expect(signInPath('/member/plants?filter=in bloom')).toBe(
      '/login?next=%2Fmember%2Fplants%3Ffilter%3Din%20bloom',
    )
  })

  test('drops a next that would leave the site', () => {
    // The club layout builds this from a request header the client controls. A
    // protocol-relative URL starts with a slash and is still off-site.
    expect(signInPath('//evil.example.com')).toBe('/login')
    expect(signInPath('https://evil.example.com')).toBe('/login')
  })

  test('drops nothing at all rather than producing an empty parameter', () => {
    expect(signInPath(null)).toBe('/login')
    expect(signInPath('')).toBe('/login')
  })
})

describe('passkeyProblem', () => {
  test('covers both cancelling and no match, which the browser will not separate', () => {
    expect(passkeyProblem(domError('NotAllowedError'))).toBe(
      SIGN_IN_PROBLEMS.passkeyNotAllowed,
    )
  })

  test('names the wrong-account case', () => {
    expect(passkeyProblem(domError('InvalidStateError'))).toBe(
      SIGN_IN_PROBLEMS.passkeyInvalidState,
    )
  })

  test('says what a security error actually means for a member', () => {
    expect(passkeyProblem(domError('SecurityError'))).toBe(SIGN_IN_PROBLEMS.passkeySecurity)
  })

  test('never shows the browser own wording for something unrecognised', () => {
    const message = passkeyProblem(domError('SomethingNewInChrome'))

    expect(message).toBe(SIGN_IN_PROBLEMS.passkeyOther)
    expect(message).not.toMatch(/developer-facing/)
  })

  test('survives being handed something that is not an error at all', () => {
    expect(passkeyProblem('a string')).toBe(SIGN_IN_PROBLEMS.passkeyOther)
    expect(passkeyProblem(null)).toBe(SIGN_IN_PROBLEMS.passkeyOther)
  })
})

describe('apiProblem', () => {
  test('shows what Django said, which is already written for a member', () => {
    expect(apiProblem(new ApiError(401, 'That code is not valid. Request a new one.'))).toBe(
      'That code is not valid. Request a new one.',
    )
  })

  test('falls back when Django said nothing', () => {
    expect(apiProblem(new ApiError(500, '   '))).toBe(SIGN_IN_PROBLEMS.unreachable)
  })

  test('never shows what a network failure says', () => {
    expect(apiProblem(new TypeError('Failed to fetch'))).toBe(SIGN_IN_PROBLEMS.unreachable)
  })

  test('survives being handed something that is not an error at all', () => {
    expect(apiProblem(undefined)).toBe(SIGN_IN_PROBLEMS.unreachable)
  })
})

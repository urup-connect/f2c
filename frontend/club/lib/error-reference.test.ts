import { describe, expect, test } from 'vitest'
import { newErrorReference, readErrorReference } from './error-reference'

/*
 * design/features/sign-up.md section 7.
 *
 * The reference is the only thing a member is given about a fault on our side, and the only thing
 * they have to quote to report it. Two properties matter: it says nothing, and nothing but our own
 * shape is ever rendered.
 */

describe('a fresh reference', () => {
  test('is eight lower-case hex characters', () => {
    expect(newErrorReference()).toMatch(/^[0-9a-f]{8}$/)
  })

  test('is different every time', () => {
    /*
     * Not a randomness test — it cannot be. It fails if the implementation is ever replaced by
     * something constant, which is the mistake that would make every log line unfindable.
     */
    const minted = new Set(Array.from({ length: 50 }, () => newErrorReference()))

    expect(minted.size).toBeGreaterThan(45)
  })

  test('is readable by the reader that renders it', () => {
    expect(readErrorReference(newErrorReference())).not.toBeNull()
  })
})

describe('reading a reference from somewhere untrusted', () => {
  test('accepts one of ours', () => {
    expect(readErrorReference('3f9a1c04')).toBe('3f9a1c04')
  })

  test('refuses anything that is not eight hex characters', () => {
    for (const value of ['', '3f9a1c0', '3f9a1c045', '3F9A1C04', 'zzzzzzzz', '3f9a 1c04']) {
      expect(readErrorReference(value)).toBeNull()
    }
  })

  test('refuses wording, so nothing of a visitor’s choosing reaches the screen', () => {
    // The parameter is in a URL anybody can edit, and what it names is rendered.
    expect(readErrorReference('Call 0800 000 000 to claim')).toBeNull()
    expect(readErrorReference('<script>')).toBeNull()
  })

  test('refuses a repeated query parameter, which arrives as a list', () => {
    expect(readErrorReference(['3f9a1c04', '3f9a1c05'])).toBeNull()
  })

  test('refuses anything that is not a string at all', () => {
    for (const value of [undefined, null, 0, {}, true]) {
      expect(readErrorReference(value)).toBeNull()
    }
  })
})

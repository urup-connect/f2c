import { describe, expect, test } from 'vitest'
import { ApiError, type Passkey } from './api'
import {
  PASSKEY_NAME_MAX,
  enrolmentProblem,
  passkeyNameToSend,
  passkeyTimeline,
  suggestPasskeyName,
  trimPasskeyName,
} from './passkeys'
import { SIGN_IN_PROBLEMS } from './sign-in-content'
import { PASSKEYS_CARD } from './store-content'

const passkey = (overrides: Partial<Passkey> = {}): Passkey => ({
  id: 1,
  name: 'Windows PC',
  backed_up: false,
  device_type: 'single_device',
  created_at: '2026-03-15T10:00:00Z',
  last_used_at: null,
  ...overrides,
})

const domError = (name: string): Error => {
  const error = new Error('the browser said something developer-facing')
  error.name = name
  return error
}

describe('enrolmentProblem', () => {
  test('blames the device when the authenticator refused', () => {
    expect(enrolmentProblem(domError('NotAllowedError'))).toBe(SIGN_IN_PROBLEMS.passkeyNotAllowed)
  })

  test("shows the API's own sentence when Django refused", () => {
    // The two failures read completely differently: one is about this device, one about the account.
    expect(enrolmentProblem(new ApiError(429, 'Too many passkeys on this account.'))).toBe(
      'Too many passkeys on this account.',
    )
  })

  test('falls back to our wording for anything unrecognised', () => {
    expect(enrolmentProblem(new TypeError('Failed to fetch'))).toBe(SIGN_IN_PROBLEMS.unreachable)
  })
})

describe('suggestPasskeyName', () => {
  test('names the device from a user-agent string it was given', () => {
    // A parameter, never read from `navigator` in the module — so the Windows case is a test rather
    // than something that only misbehaves on somebody else's laptop.
    expect(suggestPasskeyName('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)')).toBe('iPhone or iPad')
    expect(suggestPasskeyName('Mozilla/5.0 (Linux; Android 15)')).toBe('Android device')
    expect(suggestPasskeyName('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')).toBe('Mac')
    expect(suggestPasskeyName('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('Windows PC')
  })

  test('answers something for a user agent it does not recognise', () => {
    expect(suggestPasskeyName('')).toBe('This device')
  })
})

describe('passkeyNameToSend', () => {
  test('sends what was typed', () => {
    expect(passkeyNameToSend('  Work laptop  ', 'anything')).toBe('Work laptop')
  })

  test('falls back to the suggestion rather than letting Django name it "Passkey"', () => {
    expect(passkeyNameToSend('   ', 'Mozilla/5.0 (Macintosh)')).toBe('Mac')
  })

  test('truncates where Django truncates, so the customer sees what will be stored', () => {
    expect(passkeyNameToSend('x'.repeat(200), 'anything')).toHaveLength(PASSKEY_NAME_MAX)
  })
})

describe('trimPasskeyName', () => {
  test('stops at the limit', () => {
    expect(trimPasskeyName('y'.repeat(PASSKEY_NAME_MAX + 10))).toHaveLength(PASSKEY_NAME_MAX)
  })
})

describe('passkeyTimeline', () => {
  test('says a passkey has never been used rather than showing an epoch date', () => {
    // Somebody reading "Last used 1 January 1970" would conclude the store had lost track of
    // something.
    expect(passkeyTimeline(passkey())).toContain(PASSKEYS_CARD.neverUsed)
  })

  test('names both dates when there are two', () => {
    const line = passkeyTimeline(passkey({ last_used_at: '2026-04-01T08:30:00Z' }))

    expect(line).toContain(PASSKEYS_CARD.addedPrefix)
    expect(line).toContain(PASSKEYS_CARD.lastUsedPrefix)
    expect(line).toContain('2026')
  })

  test('survives a date it cannot read', () => {
    const line = passkeyTimeline(passkey({ created_at: 'nonsense' }))

    expect(line).toContain(PASSKEYS_CARD.addedPrefix)
    expect(line).not.toContain('Invalid')
  })
})

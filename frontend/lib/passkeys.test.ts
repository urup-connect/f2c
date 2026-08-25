import { describe, expect, test } from 'vitest'
import { ApiError, type Passkey } from './api'
import { PASSKEYS_CARD } from './club-content'
import { SIGN_IN_PROBLEMS } from './sign-in-content'
import {
  PASSKEY_NAME_MAX,
  enrolmentProblem,
  passkeyNameToSend,
  passkeyTimeline,
  suggestPasskeyName,
  trimPasskeyName,
} from './passkeys'

const AGENTS = {
  iphone:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 Version/18.2 Mobile Safari/604.1',
  android:
    'Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36',
  mac: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36',
  windows:
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36',
  unknown: 'Mozilla/5.0 (SomethingElse)',
} as const

const PASSKEY: Passkey = {
  id: 1,
  name: 'Windows PC',
  backed_up: false,
  device_type: 'single_device',
  created_at: '2026-03-15T08:00:00Z',
  last_used_at: '2026-08-01T19:30:00Z',
}

describe('suggestPasskeyName', () => {
  test('recognises an iPhone or iPad', () => {
    expect(suggestPasskeyName(AGENTS.iphone)).toBe('iPhone or iPad')
  })

  test('recognises an Android device', () => {
    expect(suggestPasskeyName(AGENTS.android)).toBe('Android device')
  })

  test('recognises a Mac', () => {
    expect(suggestPasskeyName(AGENTS.mac)).toBe('Mac')
  })

  test('recognises a Windows PC', () => {
    // A test rather than something that only misbehaves on somebody else's laptop.
    expect(suggestPasskeyName(AGENTS.windows)).toBe('Windows PC')
  })

  test('has something to say about anything else', () => {
    expect(suggestPasskeyName(AGENTS.unknown)).toBe('This device')
    expect(suggestPasskeyName('')).toBe('This device')
  })
})

describe('trimPasskeyName', () => {
  test('leaves a sensible name alone', () => {
    expect(trimPasskeyName('Work laptop')).toBe('Work laptop')
  })

  test('cuts at the length Django stores, so the member sees what will be kept', () => {
    expect(trimPasskeyName('x'.repeat(200))).toHaveLength(PASSKEY_NAME_MAX)
  })
})

describe('passkeyNameToSend', () => {
  test('sends what the member typed', () => {
    expect(passkeyNameToSend('Work laptop', AGENTS.windows)).toBe('Work laptop')
  })

  test('trims what they typed', () => {
    expect(passkeyNameToSend('  Work laptop  ', AGENTS.windows)).toBe('Work laptop')
  })

  test('suggests a name when they typed nothing', () => {
    // Django would store the literal "Passkey", which tells a member with three of
    // them nothing at all.
    expect(passkeyNameToSend('', AGENTS.mac)).toBe('Mac')
    expect(passkeyNameToSend('   ', AGENTS.iphone)).toBe('iPhone or iPad')
  })

  test('cuts a long name down before sending it', () => {
    expect(passkeyNameToSend('x'.repeat(200), AGENTS.mac)).toHaveLength(PASSKEY_NAME_MAX)
  })
})

describe('passkeyTimeline', () => {
  test('says when it was added and when it was last used', () => {
    const line = passkeyTimeline(PASSKEY)

    expect(line).toContain(PASSKEYS_CARD.addedPrefix)
    expect(line).toContain('15 Mar 2026')
    expect(line).toContain(PASSKEYS_CARD.lastUsedPrefix)
    expect(line).toContain('1 Aug 2026')
  })

  test('says a passkey has never been used rather than showing an epoch date', () => {
    const line = passkeyTimeline({ ...PASSKEY, last_used_at: null })

    expect(line).toContain(PASSKEYS_CARD.neverUsed)
    expect(line).not.toContain('1970')
  })

  test('says nothing misleading when a date cannot be read', () => {
    const line = passkeyTimeline({ ...PASSKEY, created_at: 'not a date' })

    expect(line).not.toMatch(/invalid/i)
    expect(line).toContain(PASSKEYS_CARD.addedPrefix)
  })
})

describe('enrolmentProblem', () => {
  test('blames the device when the authenticator refused', () => {
    const cancelled = new Error('irrelevant')
    cancelled.name = 'NotAllowedError'

    expect(enrolmentProblem(cancelled)).toBe(SIGN_IN_PROBLEMS.passkeyNotAllowed)
  })

  test('says what a security error means, which is a hosting problem', () => {
    const insecure = new Error('irrelevant')
    insecure.name = 'SecurityError'

    expect(enrolmentProblem(insecure)).toBe(SIGN_IN_PROBLEMS.passkeySecurity)
  })

  test('shows what Django said when Django is the one refusing', () => {
    expect(enrolmentProblem(new ApiError(409, 'That passkey is already registered.'))).toBe(
      'That passkey is already registered.',
    )
  })

  test('never shows what a network failure said', () => {
    expect(enrolmentProblem(new TypeError('Failed to fetch'))).toBe(
      SIGN_IN_PROBLEMS.unreachable,
    )
  })

  test('survives being handed something that is not an error at all', () => {
    expect(enrolmentProblem(null)).toBe(SIGN_IN_PROBLEMS.unreachable)
  })
})

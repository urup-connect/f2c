import { describe, expect, test } from 'vitest'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'
import {
  ALL_SIGN_IN_COPY,
  CODE_SENT_PREFIX,
  CODE_SENT_SUFFIX,
  SIGN_IN,
  SIGN_IN_PROBLEMS,
} from './sign-in-content'

/*
 * The sign-in screen is a signed-out surface, so it takes no exemption at all — including from
 * `RETAIL_VOICE`, unlike the club area behind it. See `club-content.test.ts`.
 *
 * The rule that matters most here is not in `copy-compliance.ts`: nothing on this screen may say
 * whether an address belongs to a member. design/features/authentication.md section 3.
 */

describe('nothing here says who is a member', () => {
  test('the code notice is conditional, and reads as one sentence', () => {
    // "If <address> belongs to a member, a code is on its way." An unknown address and a
    // real one produce byte-identical answers from Django; copy that said "we have sent
    // you a code" would give away in words what the API withholds in bytes.
    expect(CODE_SENT_PREFIX).toBe('If')
    expect(CODE_SENT_SUFFIX).toMatch(/^belongs to a member/)
  })

  test('no refusal distinguishes an unknown address from a wrong credential', () => {
    for (const line of Object.values(SIGN_IN_PROBLEMS)) {
      expect(line, line).not.toMatch(/no such|not found|unknown address|not a member|no account/i)
    }
  })

  test('the passkey refusals cover cancelling and not matching in one sentence', () => {
    // The browser gives the same NotAllowedError for both, so the copy cannot separate them.
    expect(SIGN_IN_PROBLEMS.passkeyNotAllowed).toMatch(/cancelled/i)
    expect(SIGN_IN_PROBLEMS.passkeyNotAllowed).toMatch(/matched/i)
  })
})

describe('the screen is complete', () => {
  test('labels both credentials it can ask for', () => {
    expect(SIGN_IN.emailLabel.length).toBeGreaterThan(0)
    expect(SIGN_IN.codeLabel.length).toBeGreaterThan(0)
  })

  test('says how long a code lasts, so nobody waits on a dead one', () => {
    expect(SIGN_IN.codeHintSuffix).toMatch(/five minutes/i)
  })

  test('offers a way back to the address step', () => {
    expect(SIGN_IN.startOver.length).toBeGreaterThan(0)
  })

  test('offers a code both before and after a passkey has failed', () => {
    expect(SIGN_IN.requestCode).not.toBe(SIGN_IN.requestCodeInstead)
  })

  test('says up front that there is no password', () => {
    // Members have none. Saying so is what stops somebody hunting for the field.
    expect(SIGN_IN.standfirst).toMatch(/no password/i)
  })

  test('never asks for one', () => {
    // The staff endpoint at POST /api/auth/login exists for Django admin and is not
    // offered here. No label, no button, no prompt.
    const asks = [
      SIGN_IN.emailLabel,
      SIGN_IN.codeLabel,
      SIGN_IN.emailContinue,
      SIGN_IN.codeSubmit,
      SIGN_IN.requestCode,
      SIGN_IN.requestCodeInstead,
      SIGN_IN.resend,
      SIGN_IN.startOver,
    ]

    for (const line of asks) expect(line, line).not.toMatch(/password/i)
  })
})

describe('the corpus', () => {
  test('gathers every line', () => {
    expect(ALL_SIGN_IN_COPY.length).toBeGreaterThan(15)
  })

  test('makes no medical, therapeutic or dosage claim', () => {
    for (const line of ALL_SIGN_IN_COPY) expect(line, line).not.toMatch(CLINICAL_CLAIM)
  })

  test('reads as a club rather than a shop', () => {
    for (const line of ALL_SIGN_IN_COPY) expect(line, line).not.toMatch(RETAIL_VOICE)
  })

  test('names no amount, in any currency', () => {
    for (const line of ALL_SIGN_IN_COPY) {
      for (const pattern of CURRENCY) expect(line, line).not.toMatch(pattern)
    }
  })

  test('says nothing about who may join', () => {
    for (const line of ALL_SIGN_IN_COPY) expect(line, line).not.toMatch(ELIGIBILITY_CLAIM)
  })
})

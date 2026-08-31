import { describe, expect, test } from 'vitest'

import {
  ALL_BLOCKED_COPY,
  BLOCKED_COPY,
  BLOCKED_SHELL,
  isBlockedReason,
} from './blocked-content'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'

/*
 * The blocked-membership screen's wording, held to all four rules with no exemption.
 *
 * The `CURRENCY` rule matters here in a way it does not on most screens: this is the screen a
 * member reaches *because* money will not fix their situation, so a figure on it would invite
 * exactly the payment `/payments/me/checkout` now refuses with a 409.
 */

describe('the blocked-membership copy', () => {
  test('has a sentence in it', () => {
    // Guards the corpus itself: one that silently collected nothing would pass every rule below.
    expect(ALL_BLOCKED_COPY.length).toBeGreaterThan(8)
  })

  test('makes no clinical claim', () => {
    for (const line of ALL_BLOCKED_COPY) expect(line, line).not.toMatch(CLINICAL_CLAIM)
  })

  test('does not speak in a shop’s voice', () => {
    for (const line of ALL_BLOCKED_COPY) expect(line, line).not.toMatch(RETAIL_VOICE)
  })

  test('names no amount, and takes no exemption to do so', () => {
    for (const line of ALL_BLOCKED_COPY) {
      for (const pattern of CURRENCY) expect(line, line).not.toMatch(pattern)
    }
  })

  test('says nothing about who may join', () => {
    for (const line of ALL_BLOCKED_COPY) expect(line, line).not.toMatch(ELIGIBILITY_CLAIM)
  })

  test('never states why a membership was blocked', () => {
    /*
     * **The privacy rule on this screen.** A reason an administrator recorded is not something to
     * render into a page: the session is real, but a shared device and a forwarded screenshot both
     * are ordinary. The private channel is the email, which carries it. So the screen says where
     * somebody stands, not what they are alleged to have done.
     */
    for (const line of ALL_BLOCKED_COPY) {
      expect(line, line).not.toMatch(
        /\b(breach|violat\w+|misconduct|fraud\w*|abuse|banned|expelled|complaint)\b/i,
      )
    }
  })

  test('every situation offers a way out, or has nothing to ask for', () => {
    /*
     * The point of the screen. Two of the three carry the support label; the third deliberately
     * does not, because "is it done yet" is not a useful email and the club has undertaken to
     * write first.
     */
    expect(BLOCKED_COPY.blocked.contact).not.toBeNull()
    expect(BLOCKED_COPY['not-settled-by-payment'].contact).not.toBeNull()
    expect(BLOCKED_COPY['awaiting-verification'].contact).toBeNull()
  })

  test('the mail subject says nothing about the member’s standing', () => {
    // It travels through the member's own mail client and whatever their provider indexes.
    expect(BLOCKED_SHELL.subject).not.toMatch(/block\w*|suspend\w*|hold|refus\w*/i)
  })

  test('recognises exactly the reasons it has wording for', () => {
    /*
     * The guard the page depends on: `owes-payment` and `not-a-member` have destinations of their
     * own, and the page redirects rather than rendering an undefined notice.
     */
    expect(isBlockedReason('blocked')).toBe(true)
    expect(isBlockedReason('awaiting-verification')).toBe(true)
    expect(isBlockedReason('not-settled-by-payment')).toBe(true)
    expect(isBlockedReason('owes-payment')).toBe(false)
    expect(isBlockedReason('not-a-member')).toBe(false)
  })
})

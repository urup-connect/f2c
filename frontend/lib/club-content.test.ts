import { describe, expect, test } from 'vitest'
import {
  ALL_CLUB_COPY,
  CLUB_HOMES_COPY,
  CLUB_SHELL,
  DESTINATIONS,
  DETAILS_CARD,
  MEMBERSHIP_CARD,
  PASSKEYS_CARD,
} from './club-content'
import { CLUB_ROLES } from './club-roles'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'

/*
 * The signed-in club screens.
 *
 * These take **one exemption**, and it is worth stating plainly because it is the first time the
 * product has taken it: the club area is exempt from `RETAIL_VOICE`.
 *
 * `RETAIL_VOICE` exists so the *public* product reads as a club rather than a shop — see
 * `copy-compliance.ts` and the landing page's corpus, which is held to it. Behind sign-in the
 * product genuinely does the transactional things: a member buys a plant, tracks an order and
 * looks at their stock, and a screen that would not say "order" cannot describe the screen a
 * member is standing on. Refusing the word would not make the club less of a shop; it would only
 * make the navigation harder to read.
 *
 * Nothing else is exempt. `CLINICAL_CLAIM` in particular is not, here or anywhere: a claim about
 * health is no more defensible to a member than to a visitor.
 */

describe('every home is complete', () => {
  test.each(CLUB_ROLES)('%s has a title, a greeting and a standfirst', (role) => {
    const copy = CLUB_HOMES_COPY[role]

    expect(copy.title.length).toBeGreaterThan(0)
    expect(copy.greeting.length).toBeGreaterThan(0)
    expect(copy.standfirst.length).toBeGreaterThan(0)
  })

  test('gives the three homes three different titles', () => {
    const titles = CLUB_ROLES.map((role) => CLUB_HOMES_COPY[role].title)

    expect(new Set(titles).size).toBe(titles.length)
  })
})

describe('the details card', () => {
  test('labels every field the card shows', () => {
    // Four, not five. The date of birth moved to the profile screen, which labels it itself.
    expect(Object.keys(DETAILS_CARD.labels)).toEqual([
      'name',
      'nickname',
      'email',
      'mobile',
    ])
  })

  test('never labels an identity number', () => {
    // It is encrypted at rest and is not in UserOut. A label for it would be the
    // first step towards putting it on a screen.
    const labels = Object.values(DETAILS_CARD.labels).join(' ')

    expect(labels).not.toMatch(/identity|\bid\b/i)
  })

  test('says which fields are the member’s own to change, and which are not', () => {
    /*
     * This used to assert only that the note existed, because the note said nothing here could be
     * changed at all. Two of the four now can. Both halves are asserted because either one alone
     * misleads: the invitation without the exception sends a member looking for an email field
     * that is not there, and the exception without the invitation is the old apology.
     */
    expect(DETAILS_CARD.note.length).toBeGreaterThan(0)
    expect(DETAILS_CARD.editLabel.length).toBeGreaterThan(0)
    expect(DETAILS_CARD.fixedNote).toMatch(/nickname/i)
    expect(DETAILS_CARD.fixedNote).toMatch(/email/i)
  })
})

describe('the membership card', () => {
  const STATUSES = [
    'active',
    'pending',
    'pending_payment',
    'suspended',
    'inactive',
    'sharing',
  ] as const

  test.each(STATUSES)('has a label and a sentence for %s', (status) => {
    expect(MEMBERSHIP_CARD.statusLabels[status].length).toBeGreaterThan(0)
    expect(MEMBERSHIP_CARD.statusNotes[status].length).toBeGreaterThan(0)
  })

  test('covers every status and invents none', () => {
    expect(Object.keys(MEMBERSHIP_CARD.statusLabels).sort()).toEqual([...STATUSES].sort())
    expect(Object.keys(MEMBERSHIP_CARD.statusNotes).sort()).toEqual([...STATUSES].sort())
  })
})

describe('the passkey card', () => {
  test('explains what a passkey is before asking for one', () => {
    expect(PASSKEYS_CARD.standfirst).toMatch(/device/i)
  })

  test('says what happens until there is one', () => {
    expect(PASSKEYS_CARD.standfirst).toMatch(/code/i)
  })

  test('has something to say to a browser that cannot make one', () => {
    expect(PASSKEYS_CARD.unsupported).toMatch(/code/i)
  })
})

describe('the shell', () => {
  test('offers a way past the furniture', () => {
    expect(CLUB_SHELL.skipToContent.length).toBeGreaterThan(0)
  })

  test('offers a way out', () => {
    expect(CLUB_SHELL.signOut.length).toBeGreaterThan(0)
  })
})

describe('a destination with nothing behind it', () => {
  test('is marked in words rather than only by being inert', () => {
    expect(DESTINATIONS.planned.length).toBeGreaterThan(0)
  })

  test('says the same thing at length, for a screen reader', () => {
    expect(DESTINATIONS.plannedDescription.length).toBeGreaterThan(
      DESTINATIONS.planned.length,
    )
  })
})

describe('the corpus', () => {
  test('gathers every line', () => {
    expect(ALL_CLUB_COPY.length).toBeGreaterThan(30)
    for (const line of ALL_CLUB_COPY) expect(typeof line).toBe('string')
  })

  test('makes no medical, therapeutic or dosage claim', () => {
    for (const line of ALL_CLUB_COPY) expect(line, line).not.toMatch(CLINICAL_CLAIM)
  })

  test('names no amount, in any currency', () => {
    for (const line of ALL_CLUB_COPY) {
      for (const pattern of CURRENCY) expect(line, line).not.toMatch(pattern)
    }
  })

  test('says nothing about who may join', () => {
    // Legal has not written this. The age gate is the only surface that states any part of it.
    for (const line of ALL_CLUB_COPY) expect(line, line).not.toMatch(ELIGIBILITY_CLAIM)
  })

  test('takes the retail exemption knowingly, and only in the club area', () => {
    /*
     * Asserted rather than skipped, so the exemption is visible: this corpus *does* use the
     * vocabulary, on purpose, and the day it stops needing to is the day this test should fail
     * and the exemption be withdrawn.
     */
    const transactional = ALL_CLUB_COPY.filter((line) => RETAIL_VOICE.test(line))

    expect(transactional.length).toBeGreaterThan(0)
  })
})

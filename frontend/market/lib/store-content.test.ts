import { describe, expect, test } from 'vitest'
import { STORE_BRAND, STOREFRONT_CODE } from './brand'
import { LANDING } from './landing-content'
import { LEGAL } from './legal-content'
import { SIGN_IN, SIGN_IN_PROBLEMS } from './sign-in-content'
import { SIGN_UP, SIGN_UP_OUTCOME } from './sign-up-content'
import { ACCOUNT_HOME, ORDERS_CARD, PASSKEYS_CARD, PROFILE_COPY, STORE_SHELL } from './store-content'

/*
 * The store's copy, held to the two rules that apply to it.
 *
 * There is no `copy-compliance.ts` in this application and there must not be: it forbids currency,
 * retail voice and clinical claims in member-facing copy, and those are cannabis constraints. A store
 * that could not name a price would not be a store — `design/verticals.md` risk 6, mitigated by the
 * rules living in the club application rather than in a shared package.
 *
 * What replaces it is narrower and runs here: the store must not speak as the club, and it must be
 * able to speak as a shop.
 */

/** Every fixed string the store shows, flattened. */
const corpus = (): string[] => {
  const strings: string[] = []

  const walk = (value: unknown): void => {
    if (typeof value === 'string') {
      strings.push(value)
      return
    }
    if (Array.isArray(value)) {
      value.forEach(walk)
      return
    }
    if (typeof value === 'object' && value !== null) {
      Object.values(value).forEach(walk)
    }
  }

  walk([
    STORE_BRAND,
    LANDING,
    LEGAL,
    SIGN_IN,
    SIGN_IN_PROBLEMS,
    SIGN_UP,
    SIGN_UP_OUTCOME,
    STORE_SHELL,
    ACCOUNT_HOME,
    PROFILE_COPY,
    PASSKEYS_CARD,
    ORDERS_CARD,
  ])

  return strings
}

describe('the corpus', () => {
  test('is not empty, so the guards below are actually reading something', () => {
    expect(corpus().length).toBeGreaterThan(50)
  })
})

describe('the store never speaks as the club', () => {
  /*
   * The two storefronts are separate businesses on separate domains with separate mail servers. Copy
   * here that named the club would be the same failure `storefronts/mail.py` exists to prevent, in the
   * other direction: a shopper told the club is emailing them has been told something indistinguishable
   * from a phishing attempt.
   *
   * "Club" is not on the list, because one passkeys sentence names it deliberately: a customer who is
   * also a club member has two sets of passkeys and needs telling. It is asserted below instead.
   */
  const forbidden = ['cultivators collective', 'cannabis', 'strain', 'cultivator', 'membership fee']

  test.each(forbidden)('never says "%s"', (word) => {
    const offenders = corpus().filter((line) => line.toLowerCase().includes(word))

    expect(offenders).toEqual([])
  })

  test('names the club exactly once, and only to explain that passkeys do not cross domains', () => {
    const mentions = corpus().filter((line) => /\bclub\b/i.test(line))

    expect(mentions).toEqual([PASSKEYS_CARD.perDomain])
  })
})

describe('the store speaks as a shop', () => {
  test('names what something costs, which the club may not', () => {
    const everything = corpus().join(' ').toLowerCase()

    expect(everything).toContain('price')
  })

  test('offers an account rather than a membership', () => {
    // The commercial difference between the two storefronts, and the reason the store can open first.
    expect(SIGN_UP.standfirst.toLowerCase()).toContain('no subscription')
  })
})

describe('the brand', () => {
  test('is named once, so nothing else spells it', () => {
    expect(STORE_BRAND.name).toBe('Farm to Consumer')
    expect(STORE_BRAND.shortName).toBe('F2C')
  })

  test('knows the storefront code Django files it under', () => {
    // Renaming this would move every document a customer has already agreed to. See
    // app/core/storefronts/models.py.
    expect(STOREFRONT_CODE).toBe('market')
  })

  test('uses the name in the copy that greets a visitor, rather than a second spelling', () => {
    expect(SIGN_IN.back).toContain(STORE_BRAND.name)
    expect(LANDING.title).toBe(STORE_BRAND.name)
  })
})

describe('the not-open copy', () => {
  test('says the store is not trading yet, on the front door', () => {
    // A landing page that invited a shopper to browse would send them to a catalogue that does not
    // exist; one that said nothing would leave them hunting for it.
    expect(LANDING.notYet.heading.toLowerCase()).toContain('not open')
  })

  test('tells a customer where orders will appear, rather than hiding the gap', () => {
    expect(ORDERS_CARD.body.toLowerCase()).toContain('catalogue')
  })
})

import { describe, expect, test } from 'vitest'
import {
  ACCOUNT_MENU,
  ACCOUNT_PATH,
  DETAILS_PATH,
  SECURITY_PATH,
  navigable,
} from './navigation'

describe('the account menu', () => {
  test('offers details, security and orders, in that order', () => {
    expect(ACCOUNT_MENU.map((destination) => destination.key)).toEqual([
      'details',
      'security',
      'orders',
    ])
  })

  test('is not derived from permissions, because a customer holds none', () => {
    /*
     * The finding this module records. `permissions_for` grants from a club membership, a storefront
     * appointment or a producer appointment; an ordinary shopper has no row in any of the three, so a
     * permission-derived menu would render empty for every customer the store has. Both destinations
     * here are "your own" and the endpoints behind them take no account identifier.
     *
     * Asserted as the absence of a `permission` key, so adding one has to come with a decision about
     * what it is checked against.
     */
    for (const destination of ACCOUNT_MENU) {
      expect(destination).not.toHaveProperty('permission')
    }
  })

  test('every ready destination has somewhere to go, and every planned one does not', () => {
    for (const destination of ACCOUNT_MENU) {
      if (destination.state === 'ready') {
        expect(destination.href).toBeTruthy()
      } else {
        expect(destination.href).toBeNull()
      }
    }
  })

  test('every destination says what it is for', () => {
    for (const destination of ACCOUNT_MENU) {
      expect(destination.title.length).toBeGreaterThan(0)
      expect(destination.description.length).toBeGreaterThan(0)
    }
  })

  test('has no administration tile, because there is no codename to gate one on', () => {
    // Showing every shopper a locked door is worse than showing them nothing, and a tile gated on a
    // codename that does not exist would be gated on `undefined`. See C29.
    const titles = ACCOUNT_MENU.map((destination) => destination.title.toLowerCase())

    expect(titles.some((title) => title.includes('administration'))).toBe(false)
  })
})

describe('navigable', () => {
  test('returns only what works, for the header bar', () => {
    expect(navigable().map((destination) => destination.href)).toEqual([
      DETAILS_PATH,
      SECURITY_PATH,
    ])
  })
})

describe('the paths', () => {
  test('sit under the account area, so one guard covers all of them', () => {
    // The route group's layout is the gate. A screen outside it would need its own.
    expect(DETAILS_PATH.startsWith(`${ACCOUNT_PATH}/`)).toBe(true)
    expect(SECURITY_PATH.startsWith(`${ACCOUNT_PATH}/`)).toBe(true)
  })
})

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'
import {
  CLUB_DESTINATIONS,
  CLUB_SECTIONS,
  SECTION_HEADINGS,
  destinationsFor,
  navigableFor,
  sectionsFor,
} from './club-navigation'

/* design/features/roles-and-permissions.md sections 12 and 13. */

/** A member, a cultivator and an administrator, as Django would send them. */
const MEMBER = [
  'platform.browse_catalogue',
  'platform.manage_own_profile',
  'platform.offer_inventory_for_swap',
  'platform.purchase_plants',
  'platform.query_orders',
  'platform.submit_reviews',
  'platform.submit_support_request',
  'platform.track_orders',
  'platform.use_swap_zone',
  'platform.view_own_inventory',
] as const

const CULTIVATOR = [
  'platform.allocate_sharing_member_stock',
  'platform.appoint_cultivator_staff',
  'platform.browse_catalogue',
  'platform.change_plant_status',
  'platform.manage_own_cultivator_profile',
  'platform.manage_own_pricing',
  'platform.manage_own_profile',
  'platform.manage_own_strain_listings',
  'platform.manage_plant_stock',
  'platform.manage_sharing_members',
  'platform.record_notes',
  'platform.register_sharing_member',
  'platform.request_catalogue_addition',
  'platform.respond_to_reviews',
  'platform.submit_support_request',
  'platform.view_fulfilment_documents',
] as const

const ADMIN = [
  'platform.browse_catalogue',
  'platform.cancel_membership',
  'platform.disable_batch',
  'platform.disable_plant',
  'platform.disable_user',
  'platform.hide_cultivator',
  'platform.manage_club_rules',
  'platform.manage_cultivators',
  'platform.manage_own_profile',
  'platform.manage_product_types',
  'platform.manage_strain_catalogue',
  'platform.record_notes',
  'platform.refund_transaction',
  'platform.respond_to_reviews',
  'platform.revoke_access',
] as const

const keys = (permissions: readonly string[]) =>
  destinationsFor(permissions).map((destination) => destination.key)

const sectionNames = (permissions: readonly string[]) =>
  sectionsFor(permissions).map((band) => band.section)

describe('the catalogue itself', () => {
  test('gives every destination a key of its own', () => {
    const allKeys = CLUB_DESTINATIONS.map((destination) => destination.key)

    expect(new Set(allKeys).size).toBe(allKeys.length)
  })

  test('names a permission on every destination', () => {
    for (const destination of CLUB_DESTINATIONS) {
      expect(destination.permission).toMatch(/^platform\.[a-z_]+$/)
    }
  })

  test('files every destination under a section that has a heading', () => {
    for (const destination of CLUB_DESTINATIONS) {
      expect(CLUB_SECTIONS).toContain(destination.section)
      expect(SECTION_HEADINGS[destination.section]).toBeTruthy()
    }
  })

  test('gives a planned destination nowhere to go, and a ready one somewhere', () => {
    // A tile that says "not built yet" is honest. A link to a route that answers 404 is not.
    for (const destination of CLUB_DESTINATIONS) {
      if (destination.state === 'planned') expect(destination.href).toBeNull()
      else expect(destination.href).toMatch(/^\//)
    }
  })
})

describe('the codenames match Django', () => {
  /*
   * A contract test that reads source as text, in the manner of `lib/brand.test.ts` and
   * `app/globals.test.ts`. `accounts/roles.py` is the only catalogue that grants anything; a
   * codename here that it does not recognise grants nothing, so the destination would silently
   * never appear for anybody. That is a defect no amount of rendering will surface.
   */
  const rolesSource = readFileSync(
    join(process.cwd(), '..', 'app', 'accounts', 'roles.py'),
    'utf8',
  )

  test.each(CLUB_DESTINATIONS.map((destination) => [destination.key, destination.permission]))(
    '%s asks for a codename roles.py grants: %s',
    (_key, permission) => {
      expect(rolesSource).toContain(`'${permission}'`)
    },
  )
})

describe('destinationsFor', () => {
  test('offers nothing at all to an account holding nothing', () => {
    // An inactive account, and a sharing member, both hold the empty set.
    expect(destinationsFor([])).toEqual([])
  })

  test('offers a member their plants, their orders and the swap zone', () => {
    expect(keys(MEMBER)).toEqual([
      'catalogue',
      'purchase-plants',
      'own-inventory',
      'track-orders',
      'query-orders',
      'submit-reviews',
      'swap-zone',
      'offer-for-swap',
      'own-profile',
      'support',
    ])
  })

  test('offers a member nothing that belongs to a cultivator or an administrator', () => {
    expect(sectionNames(MEMBER)).toEqual(['catalogue', 'plants', 'swap', 'account'])
  })

  test('offers a cultivator their stock, their listings and their sharing members', () => {
    expect(keys(CULTIVATOR)).toContain('plant-stock')
    expect(keys(CULTIVATOR)).toContain('strain-listings')
    expect(keys(CULTIVATOR)).toContain('register-sharing-member')
  })

  test('offers a cultivator no way to buy a plant or enter the swap zone', () => {
    // One role per account: the club gives those to members, and a cultivator who
    // also wants them needs a second account. Roles doc section 5.
    expect(keys(CULTIVATOR)).not.toContain('purchase-plants')
    expect(keys(CULTIVATOR)).not.toContain('swap-zone')
  })

  test('offers an administrator the collective own records', () => {
    expect(keys(ADMIN)).toContain('cultivators')
    expect(keys(ADMIN)).toContain('strain-catalogue')
    expect(keys(ADMIN)).toContain('club-rules')
    expect(keys(ADMIN)).toContain('refunds')
  })

  test('offers an administrator nothing that belongs to a grower', () => {
    expect(keys(ADMIN)).not.toContain('plant-stock')
    expect(keys(ADMIN)).not.toContain('pricing')
  })

  test('ignores a codename it does not recognise', () => {
    expect(destinationsFor(['platform.invented_action'])).toEqual([])
  })
})

describe('sectionsFor', () => {
  test('drops a band nobody in this role holds anything under', () => {
    expect(sectionNames(CULTIVATOR)).toEqual([
      'catalogue',
      'growing',
      'people',
      'community',
      'account',
    ])
  })

  test('puts the administrator bands in catalogue order', () => {
    expect(sectionNames(ADMIN)).toEqual([
      'catalogue',
      'community',
      'administration',
      'account',
    ])
  })

  test('gives a cultivator no band headed for something they do not do', () => {
    // The correction that produced the `catalogue` and `community` bands: browsing is
    // held by all three roles, and administrators answer reviews too, so filing either
    // under a grower's or a member's heading leaves somebody with a band that lies.
    expect(sectionNames(CULTIVATOR)).not.toContain('plants')
    expect(sectionNames(ADMIN)).not.toContain('growing')
  })

  test('heads each band with the wording from the headings map', () => {
    for (const band of sectionsFor(MEMBER)) {
      expect(band.heading).toBe(SECTION_HEADINGS[band.section])
    }
  })

  test('leaves no empty band behind', () => {
    for (const band of sectionsFor(ADMIN)) {
      expect(band.destinations.length).toBeGreaterThan(0)
    }
  })
})

describe('navigableFor', () => {
  test('offers nothing while nothing behind a destination is built', () => {
    // Section 13 of the roles document: none of the models these act on exist. The
    // header renders no nav at all rather than a row of dead links, and this test
    // changes on the day the first screen lands.
    expect(navigableFor(ADMIN)).toEqual([])
    expect(navigableFor(CULTIVATOR)).toEqual([])
    expect(navigableFor(MEMBER)).toEqual([])
  })
})

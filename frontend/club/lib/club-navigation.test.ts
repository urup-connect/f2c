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

/**
 * A member, a cultivator and an administrator, as Django would send them.
 *
 * **None of the three carries `platform.manage_own_profile`, and that is current rather than an
 * oversight.** Django retired the codename when the produce market arrived: a store customer holds
 * none of the three granting relationships, so an empty set refused them their own name and
 * photograph — and the endpoints behind that screen are scoped to `request.user`, so there was
 * nothing for a codename to decide. `own-profile` is offered on the session instead, which is why
 * it still appears in every expectation below.
 */
const MEMBER = [
  'platform.browse_catalogue',
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
  'platform.manage_product_types',
  'platform.manage_strain_catalogue',
  'platform.record_notes',
  'platform.refund_transaction',
  'platform.respond_to_reviews',
  'platform.revoke_access',
  'platform.view_member_inventory',
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

  test('names a well-formed permission, or names none at all', () => {
    /*
     * `null` is the second legal value and it means every signed-in account — see
     * `ClubDestination.permission`. Written as an either/or rather than relaxed to allow anything
     * falsy: an empty string or `undefined` from a half-finished entry would be a destination
     * shown to everybody by accident, which is the failure the strict version was catching.
     */
    for (const destination of CLUB_DESTINATIONS) {
      if (destination.permission === null) continue
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
  // Two levels up, not one: this application lives at `frontend/club` since the
  // Block 0.5 layout move, and the catalogue at `app/core/accounts`.
  const rolesSource = readFileSync(
    join(process.cwd(), '..', '..', 'app', 'core', 'accounts', 'roles.py'),
    'utf8',
  )

  test.each(
    CLUB_DESTINATIONS.filter((destination) => destination.permission !== null).map(
      (destination) => [destination.key, destination.permission],
    ),
  )('%s asks for a codename roles.py grants: %s', (_key, permission) => {
    expect(rolesSource).toContain(`'${permission}'`)
  })

  test('only the profile is offered without a codename', () => {
    /*
     * `null` is a real value in this catalogue and it is meant to stay rare — it says there is no
     * object to authorise. Pinning the list means a second destination cannot quietly acquire it
     * as a way around a missing permission, which would be a screen shown to everybody with an
     * endpoint that refuses them.
     */
    expect(
      CLUB_DESTINATIONS.filter((destination) => destination.permission === null).map(
        (destination) => destination.key,
      ),
    ).toEqual(['own-profile'])
  })

  test('does not ask for the codename Django retired', () => {
    /*
     * The other half of the same contract. `manage_own_profile` grants nothing now, so a
     * destination still asking for it would silently never appear — exactly the defect this
     * describe block exists to catch, and it would pass the check above by finding the string in
     * the comments that explain the removal.
     */
    for (const destination of CLUB_DESTINATIONS) {
      expect(destination.permission).not.toBe('platform.manage_own_profile')
    }
  })
})

describe('destinationsFor', () => {
  test('offers an account holding nothing its own profile, and nothing else', () => {
    /*
     * This used to expect `[]`, and the change is the point rather than a concession. An account
     * with no permissions is a member who has not paid, or a store customer, or a suspended
     * account — and the first two have a name and a photograph that are theirs to correct. What
     * they still hold is nothing else: every other destination needs a codename.
     *
     * A suspended account never reaches this function anyway; it cannot hold a session, and the
     * `(club)` layout turns an unpaid member away before any of this renders.
     */
    expect(keys([])).toEqual(['own-profile'])
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
    // Not 'refunds' or 'cancel-membership': C29 makes both the platform operator's, done in the
    // Django admin, so neither is a destination here or a codename in the catalogue.
    expect(keys(ADMIN)).not.toContain('refunds')
  })

  test('offers an administrator holdings to read and no sharing member to write', () => {
    // C14. The read is the whole of what the decision granted: registering, managing and
    // allocating to sharing members stay with the primary cultivator, so none of those three
    // destinations appears for an administrator however the register is filtered.
    expect(keys(ADMIN)).toContain('member-holdings')
    expect(keys(ADMIN)).not.toContain('register-sharing-member')
    expect(keys(ADMIN)).not.toContain('sharing-members')
    expect(keys(ADMIN)).not.toContain('allocate-stock')
  })

  test('offers an administrator nothing that belongs to a grower', () => {
    expect(keys(ADMIN)).not.toContain('plant-stock')
    expect(keys(ADMIN)).not.toContain('pricing')
  })

  test('ignores a codename it does not recognise', () => {
    /*
     * `own-profile` is the floor, not a match: it is offered on the session and an invented
     * codename adds nothing on top of it. Asserted as "exactly the floor" rather than "empty", so
     * a codename that quietly started matching something would still fail here.
     */
    expect(keys(['platform.invented_action'])).toEqual(['own-profile'])
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
  /*
   * This block used to assert that every role was offered nothing at all, and said it would change
   * on the day the first screen landed. Three have landed now: the profile, which all three roles
   * hold, and the strain catalogue and the membership register, which only an administrator does.
   * The assertions below are the same claim from the other side -- exactly those three, each to
   * exactly the roles that hold its permission, and nothing else has quietly acquired a route.
   */
  test('offers the profile, to every role that can sign in', () => {
    // None of the three holds a codename for it any more -- Django retired `manage_own_profile` --
    // so all three get it on the session alone. Kept as three cases rather than collapsed into
    // one: what is asserted is that the profile is reachable from every home page, and that
    // remains true whether the gate is a codename or a session.
    for (const permissions of [ADMIN, CULTIVATOR, MEMBER]) {
      expect(navigableFor(permissions).map((destination) => destination.key)).toContain(
        'own-profile',
      )
    }
  })

  test('offers the two administrative screens to an administrator alone', () => {
    // `manage_strain_catalogue` and `disable_user` are both in ADMIN_ACTIONS and in no other
    // role's set. The catalogue is administrator-curated -- `member-roles.md` gives a cultivator a
    // request, not a write -- and authority over another person's account is the club's alone.
    expect(navigableFor(ADMIN).map((destination) => destination.key)).toEqual([
      'strain-catalogue',
      'accounts',
      'own-profile',
    ])

    for (const permissions of [CULTIVATOR, MEMBER]) {
      expect(navigableFor(permissions).map((destination) => destination.key)).toEqual([
        'own-profile',
      ])
    }
  })

  test('offers nothing else, because nothing else is built', () => {
    /*
     * Section 13 of the roles document: almost none of the models the other destinations act on
     * exist. The assertion is on the catalogue rather than on one role's list, so a fourth `href`
     * added anywhere fails here -- which is the point. The header renders links from this and
     * nothing else, so an href pointing at a route that does not exist becomes a 404 in the bar on
     * every signed-in screen.
     */
    const ready = CLUB_DESTINATIONS.filter((destination) => destination.href !== null)

    expect(ready.map((destination) => destination.key)).toEqual([
      'strain-catalogue',
      'accounts',
      'own-profile',
    ])
    // `state` and `href` are two fields that have to agree. A `ready` destination with no href
    // renders as inert text; a `planned` one with an href renders as a link marked "not built yet".
    for (const destination of CLUB_DESTINATIONS) {
      expect(destination.state === 'ready', destination.key).toBe(destination.href !== null)
    }
  })

  test('points each destination at the route that actually exists', () => {
    expect(navigableFor(MEMBER)[0].href).toBe('/profile')
    expect(navigableFor(ADMIN)[0].href).toBe('/admin/strains')
    expect(navigableFor(ADMIN)[1].href).toBe('/admin/members')
  })
})

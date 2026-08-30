/**
 * What a signed-in customer is offered, and where each thing lives.
 *
 * **This is not the club's `club-navigation.ts` with the labels changed, and the difference is a
 * finding rather than a shortcut.** The club derives its menu from the `permissions` array on the
 * session, resolved from the `platform.*` catalogue in `app/core/accounts/roles.py`. A store
 * customer holds *none* of those codenames: `permissions_for` grants from a club membership, a
 * storefront appointment or a producer appointment, and an ordinary shopper has no row in any of
 * the three. Deriving this menu from permissions would therefore render an empty account area for
 * every customer the store has.
 *
 * The reason it does not need to is that both destinations here are *your own*: the endpoints behind
 * them — `/api/accounts/me/profile` and `/api/auth/passkeys` — take no account identifier and check
 * only the session, which is `accounts/api.py`'s recorded design rather than an omission. There is
 * no permission to consult because there is no decision to make.
 *
 * When a destination arrives that *is* a decision — market administration, held by
 * `StorefrontStaff` — it needs a codename in the catalogue first, and this module gains the
 * permission check at that point. Until then there is deliberately no administration tile: showing
 * every shopper a locked door is worse than showing them nothing, and a tile gated on a codename
 * that does not exist would be gated on `undefined`. See `design/verticals.md` section 7 and C29.
 */

import { ACCOUNT_DESTINATIONS } from './store-content'

export const ACCOUNT_PATH = '/account'
export const DETAILS_PATH = '/account/details'
export const SECURITY_PATH = '/account/security'

/**
 * Whether there is somewhere to go yet.
 *
 * `ready` carries an `href` and is rendered as a link. `planned` carries none and is rendered as
 * inert text, marked as such — never as a link to a route that would answer 404. The club's own
 * convention, and it earns its keep here for the same reason: it tells a customer what the store
 * intends, and it tells the next developer where the screen goes.
 */
export type DestinationState = 'ready' | 'planned'

export type AccountDestination = {
  /** Stable key, used for React keys and in tests. Never shown. */
  readonly key: string
  readonly title: string
  /** One line saying what the destination is for, in the store's own words. */
  readonly description: string
  readonly state: DestinationState
  /** Where it goes, once there is somewhere to go. `null` while `planned`. */
  readonly href: string | null
}

/**
 * Every destination the signed-in area offers, in the order it shows them.
 *
 * Details before security before orders: the first is what a customer came to change, the second is
 * what they came to set up once, and the third does not work yet.
 */
export const ACCOUNT_MENU = [
  {
    key: 'details',
    title: ACCOUNT_DESTINATIONS.profile.title,
    description: ACCOUNT_DESTINATIONS.profile.description,
    state: 'ready',
    href: DETAILS_PATH,
  },
  {
    key: 'security',
    title: ACCOUNT_DESTINATIONS.security.title,
    description: ACCOUNT_DESTINATIONS.security.description,
    state: 'ready',
    href: SECURITY_PATH,
  },
  {
    /*
     * Planned, and it is the one destination whose absence a customer will notice. It stays on the
     * screen saying so rather than being hidden: somebody who created an account expecting to buy
     * something should be told where that will appear, not left to conclude the page is broken.
     */
    key: 'orders',
    title: ACCOUNT_DESTINATIONS.orders.title,
    description: ACCOUNT_DESTINATIONS.orders.description,
    state: 'planned',
    href: null,
  },
] as const satisfies readonly AccountDestination[]

/**
 * The destinations that can actually be navigated to, for the header's nav bar.
 *
 * A function rather than a filtered constant so the nav and the tiles cannot fall out of step: the
 * tiles render `ACCOUNT_MENU` whole, including what is planned, and the bar renders only what
 * works.
 */
export const navigable = (): readonly AccountDestination[] =>
  ACCOUNT_MENU.filter((destination) => destination.state === 'ready' && destination.href !== null)

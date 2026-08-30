/**
 * What each signed-in account is offered, derived from its permissions and never from its role.
 *
 * Django sends `permissions` on the session — every `platform.*` codename the account holds,
 * resolved from `app/core/accounts/roles.py`. This module turns that list into things to draw. The role
 * is not consulted anywhere in here, and that is the point: a second role-to-ability map in this
 * bundle would drift from the one the API enforces, and the drift would show up as a menu offering
 * a member something the API then refuses.
 *
 * **For rendering, never for deciding.** Every endpoint checks the permission itself. Nothing here
 * grants anything. See design/features/roles-and-permissions.md section 12.
 *
 * ## Why almost everything is `planned`
 *
 * The catalogue in `roles.py` names actions against plants, strains, batches, orders, swaps,
 * reviews and transactions, and none of those models exist yet — section 13 of the same document
 * is explicit about it. So the honest state of nearly every destination is *described, not built*,
 * and a tile that says so is worth more than a tile missing altogether: it tells a cultivator what
 * the club intends them to be able to do, and it tells the next developer where the screen goes.
 *
 * When a feature lands, one entry gains an `href` and changes state. Nothing else moves. That has
 * now happened once — `own-profile` — so the claim is tested rather than promised.
 */

import { CATALOGUE_PATH } from './catalogue-routes'
import { PROFILE_PATH } from './club-roles'
import { MEMBERS_PATH } from './member-register-routes'

/**
 * Whether there is somewhere to go yet.
 *
 * `ready` carries an `href` and is rendered as a link. `planned` carries none and is rendered as
 * inert text, marked as such — never as a link to a route that would answer 404.
 */
export type ClubDestinationState = 'ready' | 'planned'

/**
 * The bands a home page groups its destinations into, in the order they are shown.
 *
 * The bands are drawn around **who holds what**, not around subject matter, and that is a
 * correction rather than the first instinct. Filing "browse the catalogue" under plants and
 * "reviews" under growing reads perfectly well until you notice that all three roles browse and
 * that administrators answer reviews too — at which point a cultivator gets a band headed *Plants
 * and orders* holding one browse link, and an administrator gets one headed *Growing* holding
 * nothing they grow. A destination two roles hold needs a band that makes sense to both.
 */
export const CLUB_SECTIONS = [
  'catalogue',
  'plants',
  'swap',
  'growing',
  'people',
  'community',
  'administration',
  'account',
] as const

export type ClubSection = (typeof CLUB_SECTIONS)[number]

export const SECTION_HEADINGS = {
  catalogue: 'The catalogue',
  plants: 'Plants and orders',
  swap: 'The swap zone',
  growing: 'Growing',
  people: 'Sharing members',
  community: 'Reviews and notes',
  administration: 'Club administration',
  account: 'Your account',
} as const satisfies Record<ClubSection, string>

export type ClubDestination = {
  /** Stable key, used for React keys and in tests. Never shown. */
  readonly key: string
  readonly label: string
  /** One line saying what the destination is for, in the club's own words. */
  readonly description: string
  /**
   * The `platform.*` codename that puts this on screen. Exactly as spelled in
   * `app/core/accounts/roles.py` — a contract test reads that file and refuses a codename it does not
   * find there, so a renamed action cannot quietly empty a menu.
   */
  readonly permission: string
  readonly section: ClubSection
  readonly state: ClubDestinationState
  /** Where it goes, once there is somewhere to go. `null` while `planned`. */
  readonly href: string | null
}

/**
 * Every destination the platform describes, in one list.
 *
 * One entry per codename a person would recognise as a place to go. A few codenames are
 * deliberately absent because they are not destinations at all: `platform.disable_plant` and
 * `platform.disable_batch` are actions taken *inside* a screen already listed here rather than
 * screens of their own, and `platform.appoint_cultivator_staff` is an object-level rule with no
 * model behind it yet.
 */
export const CLUB_DESTINATIONS = [
  /* --------------------------------------------------------- catalogue */
  {
    key: 'catalogue',
    label: 'Browse the catalogue',
    description: 'Strains and cultivators, with their ratings and reviews.',
    permission: 'platform.browse_catalogue',
    section: 'catalogue',
    state: 'planned',
    href: null,
  },

  /* ------------------------------------------------------------ plants */
  {
    key: 'purchase-plants',
    label: 'Buy a plant',
    description: 'Choose a plant with grow services and place the order.',
    permission: 'platform.purchase_plants',
    section: 'plants',
    state: 'planned',
    href: null,
  },
  {
    key: 'own-inventory',
    label: 'Your plants',
    description: 'Everything you own, and where each plant is in its cycle.',
    permission: 'platform.view_own_inventory',
    section: 'plants',
    state: 'planned',
    href: null,
  },
  {
    key: 'track-orders',
    label: 'Track an order',
    description: 'Where an order is, from harvest to the courier.',
    permission: 'platform.track_orders',
    section: 'plants',
    state: 'planned',
    href: null,
  },
  {
    key: 'query-orders',
    label: 'Query an order',
    description: 'Raise a question about something you have ordered.',
    permission: 'platform.query_orders',
    section: 'plants',
    state: 'planned',
    href: null,
  },
  {
    key: 'submit-reviews',
    label: 'Rate and review',
    description: 'Say how a cultivator and their plants did.',
    permission: 'platform.submit_reviews',
    section: 'plants',
    state: 'planned',
    href: null,
  },

  /* -------------------------------------------------------------- swap */
  {
    key: 'swap-zone',
    label: 'Enter the swap zone',
    description: 'Browse what other members have offered, and make a swap.',
    permission: 'platform.use_swap_zone',
    section: 'swap',
    state: 'planned',
    href: null,
  },
  {
    key: 'offer-for-swap',
    label: 'Offer a plant',
    description: 'Put one of your own plants up, or withdraw it again.',
    permission: 'platform.offer_inventory_for_swap',
    section: 'swap',
    state: 'planned',
    href: null,
  },

  /* ----------------------------------------------------------- growing */
  {
    key: 'cultivator-profile',
    label: 'Your cultivator profile',
    description: 'How the collective sees you, and what members read first.',
    permission: 'platform.manage_own_cultivator_profile',
    section: 'growing',
    state: 'planned',
    href: null,
  },
  {
    key: 'plant-stock',
    label: 'Plant stock',
    description: 'Upload stock and adjust how many plants are available.',
    permission: 'platform.manage_plant_stock',
    section: 'growing',
    state: 'planned',
    href: null,
  },
  {
    key: 'strain-listings',
    label: 'Your strain listings',
    description: 'Image, description, finished product types and price.',
    permission: 'platform.manage_own_strain_listings',
    section: 'growing',
    state: 'planned',
    href: null,
  },
  {
    key: 'pricing',
    label: 'Pricing',
    description: 'Set prices, including a promotion by strain, period, batch or quantity.',
    permission: 'platform.manage_own_pricing',
    section: 'growing',
    state: 'planned',
    href: null,
  },
  {
    key: 'plant-status',
    label: 'Move a plant on',
    description: 'Preflowering, in bloom, harvested, processed, shipped.',
    permission: 'platform.change_plant_status',
    section: 'growing',
    state: 'planned',
    href: null,
  },
  {
    key: 'fulfilment-documents',
    label: 'Fulfilment documents',
    description: 'Ownership certificates, packing labels and the paperwork the courier needs.',
    permission: 'platform.view_fulfilment_documents',
    section: 'growing',
    state: 'planned',
    href: null,
  },
  {
    key: 'catalogue-addition',
    label: 'Ask for a listing',
    description: 'Request a new strain or finished product type from an administrator.',
    permission: 'platform.request_catalogue_addition',
    section: 'growing',
    state: 'planned',
    href: null,
  },

  /* ------------------------------------------------------------ people */
  {
    key: 'register-sharing-member',
    label: 'Register a sharing member',
    description: 'A name, an identity number and a nickname, on your attestation.',
    permission: 'platform.register_sharing_member',
    section: 'people',
    state: 'planned',
    href: null,
  },
  {
    key: 'sharing-members',
    label: 'Your sharing members',
    description: 'Read, update and withdraw the people you put on the register.',
    permission: 'platform.manage_sharing_members',
    section: 'people',
    state: 'planned',
    href: null,
  },
  {
    key: 'allocate-stock',
    label: 'Allocate stock',
    description: 'Put flowering plants with a sharing member, up to the four-plant limit.',
    permission: 'platform.allocate_sharing_member_stock',
    section: 'people',
    state: 'planned',
    href: null,
  },

  /* --------------------------------------------------------- community */
  {
    key: 'respond-to-reviews',
    label: 'Reviews and ratings',
    description: 'Read what members said, and reply.',
    permission: 'platform.respond_to_reviews',
    section: 'community',
    state: 'planned',
    href: null,
  },
  {
    key: 'notes',
    label: 'Notes',
    description: 'Record a note against a member, strain, plant or subscription.',
    permission: 'platform.record_notes',
    section: 'community',
    state: 'planned',
    href: null,
  },

  /* ---------------------------------------------------- administration */
  {
    key: 'cultivators',
    label: 'Cultivators',
    description: 'Create, read, update and remove the growers in the collective.',
    permission: 'platform.manage_cultivators',
    section: 'administration',
    state: 'planned',
    href: null,
  },
  {
    /*
     * The second destination to land, and the first under `administration`. As
     * with `own-profile`, one entry gained an `href` and changed state and
     * nothing else in this file moved -- which is the shape doing its job.
     *
     * The screens behind it are `/admin/strains` and the three routes under it.
     * They answer to this permission and not to the role: `role` and
     * `manage_strain_catalogue` are independent facts, and a suspended
     * administrator holds the first without the second -- so the pages check the
     * role for a useful redirect and the API checks the permission for the
     * actual answer. See `lib/catalogue-routes.ts`.
     */
    key: 'strain-catalogue',
    label: 'Strain catalogue',
    description: 'The strains every cultivator may list against, platform-wide.',
    permission: 'platform.manage_strain_catalogue',
    section: 'administration',
    state: 'ready',
    href: CATALOGUE_PATH,
  },
  {
    key: 'product-types',
    label: 'Finished product types',
    description: 'The product types a cultivator may offer, and their prices.',
    permission: 'platform.manage_product_types',
    section: 'administration',
    state: 'planned',
    href: null,
  },
  {
    key: 'club-rules',
    label: 'Club rules and documents',
    description: 'Publish and withdraw the club rules, annexures and constitution.',
    permission: 'platform.manage_club_rules',
    section: 'administration',
    state: 'planned',
    href: null,
  },
  {
    /*
     * The third destination to land, and the second under `administration`.
     * Relabelled rather than added beside: `platform.disable_user` is the only
     * codename in `roles.py` that names authority over a member's account, and
     * the register is what exercising it looks like — you open a record to
     * suspend it. A second entry would have had to invent a codename, and the
     * contract test below this list reads `roles.py` and refuses one it cannot
     * find there.
     *
     * The description moved with the label because the screen is wider than the
     * codename: correcting a mistyped address is most of what an administrator
     * actually does here, and a tile promising only "disable an account" would
     * send them to the Django admin for the ordinary case.
     *
     * Reading, editing and suspending are built. Warnings, expulsions, revoking
     * access and cancelling a membership are not — the last two hold their own
     * codenames, which keep their own `planned` entries below.
     */
    key: 'accounts',
    label: 'Members',
    description: 'The whole register: correct a record, suspend an account, lift a suspension.',
    permission: 'platform.disable_user',
    section: 'administration',
    state: 'ready',
    href: MEMBERS_PATH,
  },
  {
    key: 'revoke-access',
    label: 'Revoke access',
    description: 'Take away access to the platform from an account.',
    permission: 'platform.revoke_access',
    section: 'administration',
    state: 'planned',
    href: null,
  },
  /*
   * Cancelling a membership and reversing a transaction used to sit here as planned destinations.
   * They are gone rather than deferred: C29 makes both the platform operator's, done in the Django
   * admin under `is_staff`, so their codenames left the catalogue and the contract test below
   * failed on them — which is the test doing its job.
   */
  {
    key: 'hide-cultivator',
    label: 'Hide a cultivator',
    description: 'Take a cultivator and everything they offer out of view.',
    permission: 'platform.hide_cultivator',
    section: 'administration',
    state: 'planned',
    href: null,
  },

  /* ----------------------------------------------------------- account */
  {
    /*
     * The first destination to land, and the one that proves the shape works: one entry gained an
     * `href` and changed state, and nothing else in this file moved. The header's nav starts
     * rendering on its own as a consequence -- see `ClubHeader`, which was written waiting for
     * exactly this.
     */
    key: 'own-profile',
    label: 'Your profile',
    description:
      'Your name and mobile number, your photograph, and what the club holds from your ID.',
    permission: 'platform.manage_own_profile',
    section: 'account',
    state: 'ready',
    href: PROFILE_PATH,
  },
  {
    key: 'support',
    label: 'Support',
    description: 'Raise a request with the club.',
    permission: 'platform.submit_support_request',
    section: 'account',
    state: 'planned',
    href: null,
  },
] as const satisfies readonly ClubDestination[]

/** One band of a home page: a heading and the destinations under it. */
export type ClubSectionContent = {
  readonly section: ClubSection
  readonly heading: string
  readonly destinations: readonly ClubDestination[]
}

/**
 * The destinations this account holds, in catalogue order.
 *
 * A `Set` rather than repeated `includes`: a superuser carries the whole catalogue, and this runs
 * on every render of every club page.
 */
export const destinationsFor = (permissions: readonly string[]): readonly ClubDestination[] => {
  const held = new Set(permissions)
  return CLUB_DESTINATIONS.filter((destination) => held.has(destination.permission))
}

/**
 * The same list, banded into sections, with empty bands dropped.
 *
 * Dropping the empty ones is what lets all three home pages render from one function: a member
 * holds nothing under `growing` or `administration`, so those headings simply do not appear, and
 * no page needs to know which bands are its own.
 */
export const sectionsFor = (permissions: readonly string[]): readonly ClubSectionContent[] => {
  const held = destinationsFor(permissions)

  return CLUB_SECTIONS.map((section) => ({
    section,
    heading: SECTION_HEADINGS[section],
    destinations: held.filter((destination) => destination.section === section),
  })).filter((band) => band.destinations.length > 0)
}

/**
 * The destinations that can actually be navigated to, for the header's nav bar.
 *
 * Empty today, by construction — nothing behind them is built. The nav renders nothing rather than
 * a row of dead links, and starts working on its own the moment the first destination gains an
 * `href`.
 */
export const navigableFor = (permissions: readonly string[]): readonly ClubDestination[] =>
  destinationsFor(permissions).filter(
    (destination) => destination.state === 'ready' && destination.href !== null,
  )

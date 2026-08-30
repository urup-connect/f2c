/**
 * Every word on the signed-in screens.
 *
 * Held apart from the components that render it for the reason the club's `club-content.ts` gives:
 * fixed content in one file is content a sign-off pass can read end to end, and a string in a
 * component is a string nobody proof-reads.
 *
 * **What is deliberately absent is a compliance corpus.** The club flattens its copy into a list so
 * `copy-compliance.ts` can hold it to the cannabis rules — no currency, no retail voice, no
 * clinical claims. The store is held to none of that and must not be: it sells produce by the
 * kilogram and has to be able to say so. `design/verticals.md` risk 6 is the note that this must
 * never leak across, and the absence of the corpus here is what keeping it means in practice.
 */

import { STORE_BRAND } from './brand'

/** The frame around every signed-in screen. */
export const STORE_SHELL = {
  homeLabel: `${STORE_BRAND.name} — your account`,
  navLabel: 'Account',
  skipToContent: 'Skip to content',
  signOut: 'Sign out',
  signingOut: 'Signing out…',
  /** The trail's first crumb. Named for where it goes, not for what it is. */
  breadcrumbsLabel: 'Breadcrumb',
} as const

/** The signed-in home page. */
export const ACCOUNT_HOME = {
  title: 'Your account',
  /** Completed with the customer's first name at the call site, so this file holds no interpolation. */
  greetingPrefix: 'Welcome back,',
  greetingFallback: 'Welcome back',
  standfirst:
    'Your details, how you sign in, and — once the store opens — your orders and deliveries.',
} as const

/** The tiles on the signed-in home page. */
export const ACCOUNT_DESTINATIONS = {
  profile: {
    title: 'Your details',
    description: 'Your name and the number a driver can reach you on.',
  },
  security: {
    title: 'How you sign in',
    description: 'Add a passkey to this device, or remove one you no longer use.',
  },
  orders: {
    title: 'Your orders',
    description: 'Nothing here yet. Orders arrive with the produce catalogue.',
  },
  administration: {
    title: 'Store administration',
    description: 'Farms, produce types and orders. Not built yet.',
  },
} as const

/** The details form. */
export const PROFILE_COPY = {
  title: 'Your details',
  standfirst: 'What the store holds about you, and the three fields you can change.',

  firstNameLabel: 'First name',
  lastNameLabel: 'Last name',
  mobileLabel: 'Mobile number',
  mobileHint: 'Optional. A driver uses it to reach you on the day of a delivery.',

  emailLabel: 'Email address',
  emailNote: 'This is how you sign in, so it cannot be changed here.',

  save: 'Save changes',
  saving: 'Saving…',
  saved: 'Your details are saved.',
  unchanged: 'Nothing has changed yet.',
  /** Shown when the API refused for a reason no field owns. */
  refused: 'Your details could not be saved.',
  failed: 'Your details could not be saved just now. Please try again.',
  mobileUnavailable: 'That mobile number is already on another account.',
} as const

/** What the details form says when it refuses a value, keyed by reason. */
export const PROFILE_REFUSAL_MESSAGES = {
  'name-missing': 'Please give this name.',
  'name-too-long': 'That is longer than the store can store. Please shorten it.',
  'name-unexpected-characters': 'That does not look like a name.',
  'mobile-unexpected-characters': 'A mobile number is digits, and may carry + ( ) . or -',
  'mobile-length': 'A South African mobile number has ten digits, starting 0.',
  'mobile-not-a-mobile': 'That does not look like a South African mobile number.',
} as const

/** The passkeys card. */
export const PASSKEYS_CARD = {
  heading: 'Passkeys',
  standfirst:
    'A passkey signs you in with your face, fingerprint or device PIN. Nothing is typed and nothing is shared, so there is nothing to phish.',

  empty: 'No passkey on this account yet. You can still sign in with an emailed code.',
  synced: 'Synced',
  remove: 'Remove',
  removing: 'Removing…',

  addLabel: 'Name this device',
  addHint: 'Optional. Leave it blank and the store will name it after the device you are on.',
  add: 'Add a passkey',
  adding: 'Adding…',

  addedPrefix: 'Added',
  lastUsedPrefix: 'Last used',
  neverUsed: 'Not used yet',

  loadFailed: 'Your passkeys could not be read just now.',
  unsupported:
    'This browser cannot create a passkey. An emailed code works everywhere, and is a full way in rather than a fallback.',
  /**
   * Said once, on the security screen, because it is the surprise a customer who is also a club
   * member will otherwise report as a bug.
   */
  perDomain:
    'A passkey belongs to the site it was made on. If you also belong to the club, its passkeys are separate from these.',
} as const

/** The orders card, which has nothing to list. */
export const ORDERS_CARD = {
  heading: 'Your orders',
  standfirst: 'Nothing to show yet.',
  body:
    'The produce catalogue is still being built. When it opens, everything you buy appears here with its delivery.',
} as const

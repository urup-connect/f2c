/**
 * Every word the signed-in club screens say, in one place.
 *
 * The same arrangement as `lib/landing-content.ts` and for the same reasons: the copy is fixed
 * club content rather than anything a caller varies, the client's sign-off pass has one file to
 * review, and the compliance tests get a corpus that cannot fall out of step with the screens.
 *
 * Three home pages, one shell. What separates the three is the greeting and the standfirst — what
 * each role is here to do — because everything below that is drawn from the account's permissions
 * and needs no copy of its own. See `lib/club-navigation.ts`.
 */

import type { ClubRole } from './club-roles'

/** The frame every signed-in screen sits in. */
export const CLUB_SHELL = {
  /** Reached by a screen reader before the nav, so it says where "here" is. */
  skipToContent: 'Skip to content',
  homeLabel: 'Cultivators Collective',
  navLabel: 'Club',
  signOut: 'Sign out',
  signingOut: 'Signing out…',
  /** Shown in place of the nav while nothing behind it is built. */
  navEmpty: 'The club is being built. What you can reach is on this page.',
} as const

/**
 * The greeting and standfirst for each home.
 *
 * `greeting` is completed with the member's display name at the call site rather than interpolated
 * here, so this file stays free of anything that has to be escaped or translated.
 */
export const CLUB_HOMES_COPY = {
  member: {
    title: 'Your club',
    greeting: 'Welcome back',
    standfirst:
      'Your plants, your orders and the swap zone. Everything you own sits here, and everything ' +
      'you have on the way.',
  },
  cultivator: {
    title: 'Your cultivation',
    greeting: 'Welcome back',
    standfirst:
      'Your stock, your listings and the people you have put on the register. What members see ' +
      'of you starts here.',
  },
  admin: {
    title: 'Club administration',
    greeting: 'Welcome back',
    standfirst:
      "The collective's own records, and authority over everybody else. Cultivators, the strain " +
      'catalogue, the club documents and the accounts on the register.',
  },
} as const satisfies Record<ClubRole, { title: string; greeting: string; standfirst: string }>

/** The card holding what the club has on file about this account. */
export const DETAILS_CARD = {
  heading: 'Your details',
  /**
   * Said plainly rather than left to be inferred from a missing button. There is no screen to
   * change these on yet, and a member who cannot find one should be told why rather than hunt.
   */
  note:
    'Changing these is not yet possible here. Ask the club and an administrator will amend the ' +
    'record.',
  labels: {
    name: 'Name',
    nickname: 'Nickname',
    email: 'Email address',
    mobile: 'Mobile number',
    dateOfBirth: 'Date of birth',
  },
  /** What a field says when the club holds nothing in it. */
  blank: 'Not on file',
} as const

/** The card describing the standing of the membership itself. */
export const MEMBERSHIP_CARD = {
  heading: 'Your membership',
  roleLabel: 'You are here as',
  statusLabel: 'Standing',
  /**
   * One line per status, addressed to the person reading it rather than describing the column.
   * `sharing` is present because the type admits it; no session can belong to one.
   */
  statusLabels: {
    active: 'Active',
    pending: 'Pending',
    pending_payment: 'Awaiting payment',
    suspended: 'Suspended',
    inactive: 'Closed',
    sharing: 'On the register',
  },
  statusNotes: {
    active: 'Your membership is in good standing.',
    pending: 'The club has not yet opened this account.',
    pending_payment: 'Your membership opens as soon as a payment lands.',
    suspended: 'Access is suspended. Contact the club.',
    inactive: 'This account is closed.',
    sharing: 'An identity held on the register by a cultivator.',
  },
} as const

/** The card for the credential a member gets in with. */
export const PASSKEYS_CARD = {
  heading: 'How you sign in',
  standfirst:
    'A passkey uses this device to prove who you are: a face, a fingerprint or a PIN, and ' +
    'nothing to remember or to lose. Until you add one, every sign-in needs a code emailed to you.',
  empty: 'No passkey yet on any device.',
  addLabel: 'Name this device',
  addHint: 'Optional. It only helps you tell one passkey from another later.',
  add: 'Add a passkey',
  adding: 'Working…',
  remove: 'Remove',
  removing: 'Removing…',
  synced: 'Synced',
  addedPrefix: 'Added',
  lastUsedPrefix: 'Last used',
  neverUsed: 'never used',
  unsupported:
    'This browser cannot create passkeys. Sign in here with an emailed code, then add a passkey ' +
    'from a browser that can.',
  loadFailed: 'Your passkeys could not be read just now. Reload the page to try again.',
} as const

/** How a destination that has nothing behind it yet is marked. */
export const DESTINATIONS = {
  heading: 'What the club will offer you',
  planned: 'Not built yet',
  /** Read by a screen reader in place of the badge, which is too terse on its own. */
  plannedDescription: 'This is part of the club and is not built yet.',
  empty: 'This account holds nothing it can act on. Contact the club.',
} as const

/**
 * Every string on the signed-in screens, flattened.
 *
 * The compliance tests read a corpus rather than each module, so a line added above is checked
 * without anyone remembering to add it here too.
 */
export const ALL_CLUB_COPY: readonly string[] = [
  ...Object.values(CLUB_SHELL),
  ...Object.values(CLUB_HOMES_COPY).flatMap((home) => Object.values(home)),
  DETAILS_CARD.heading,
  DETAILS_CARD.note,
  DETAILS_CARD.blank,
  ...Object.values(DETAILS_CARD.labels),
  MEMBERSHIP_CARD.heading,
  MEMBERSHIP_CARD.roleLabel,
  MEMBERSHIP_CARD.statusLabel,
  ...Object.values(MEMBERSHIP_CARD.statusLabels),
  ...Object.values(MEMBERSHIP_CARD.statusNotes),
  ...Object.values(PASSKEYS_CARD),
  ...Object.values(DESTINATIONS),
]

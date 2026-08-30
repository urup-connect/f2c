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
  /** Names the trail landmark, so a screen reader says what the second nav on the page is for. */
  breadcrumbLabel: 'Where you are',
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
   * This used to say that changing these was not possible and to ask the club. Two of the four
   * rows can now be changed on /profile, so the note is a link rather than an apology — and it
   * still says which rows cannot, because a member who goes looking for the email address on that
   * screen and does not find it has been sent on a wasted trip.
   */
  note: 'Your name and mobile number are yours to change.',
  /** Where the note leads. The label is the link text, so it reads as a destination. */
  editLabel: 'Edit your profile',
  /**
   * The two rows /profile shows and will not change, said here so the details card can point at
   * the right screen without promising more than it delivers.
   */
  fixedNote:
    'Your nickname and email address are changed by the club. Ask an administrator and they will ' +
    'amend the record.',
  labels: {
    name: 'Name',
    nickname: 'Nickname',
    email: 'Email address',
    mobile: 'Mobile number',
  },
  /** What a field says when the club holds nothing in it. */
  blank: 'Not on file',
} as const

/**
 * The profile screen: the fields a member may change, the two they may only read, and their
 * photograph.
 *
 * Grouped by what a member can do with each rather than by which column it came from, which is why
 * the date of birth and the identity number share a card with a heading that says so. A screen
 * that mixed the two would have a member trying to correct a field that has no input.
 */
export const PROFILE_COPY = {
  title: 'Your profile',
  heading: 'Your profile',
  standfirst:
    'What the club holds about you, and the parts of it you can change yourself. Everything here ' +
    'is yours alone — no other member sees it.',
  /** The card with the three editable fields. */
  details: {
    heading: 'Your details',
    firstNameLabel: 'First name',
    lastNameLabel: 'Last name',
    mobileLabel: 'Mobile number',
    mobileHint: 'A South African mobile number. The club uses it to reach you, never to sign you in.',
    /**
     * The two the screen shows and will not change. Shown rather than omitted because a member
     * came here to check what the club holds, and leaving them off would send them back to their
     * home page to read the other half of their own record.
     */
    fixedHeading: 'Changed by the club',
    fixedNote:
      'Your nickname is how other members know you, and your email address is how you sign in. ' +
      'Ask an administrator to change either.',
    nicknameLabel: 'Nickname',
    emailLabel: 'Email address',
    blank: 'Not on file',
    save: 'Save changes',
    saving: 'Saving…',
    saved: 'Your details are saved.',
    unchanged: 'Nothing has changed yet.',
    errorSummaryHeading: 'Your details could not be saved',
  },
  /** The card with the two fields taken from an identity document. */
  identity: {
    heading: 'From your ID',
    /**
     * Why these two have no inputs, said rather than left to be inferred from their absence. A
     * member who cannot see a way to correct their own date of birth should be told why.
     */
    standfirst:
      'These came from the identity document you gave when you joined, so they are not yours to ' +
      'retype here. If either is wrong, ask an administrator — they will need to see the document.',
    dateOfBirthLabel: 'Date of birth',
    idNumberLabel: 'Identity number',
    /** Said beside the masked number, so the hidden digits read as deliberate. */
    idNumberNote: 'Only the last four digits are shown. The club stores the rest encrypted.',
    verifiedLabel: 'Checked against a document',
    /**
     * What the verification line says when nothing has been checked. Registration does not
     * inspect a document, so this is the normal state and it must not read as a fault.
     */
    unverified: 'Not yet checked against a document.',
    unreadable:
      'The club holds a document number it cannot currently read. Please contact an administrator.',
    blank: 'Not on file',
  },
  /** The card holding the photograph, its cropper and its buttons. */
  photograph: {
    heading: 'Your photograph',
    standfirst:
      'A picture of you, so other members recognise you. Square, and you choose which part of the ' +
      'image is used.',
    empty: 'No photograph yet.',
    /** Read by a screen reader in place of the image itself. */
    imageAlt: 'Your photograph',
    choose: 'Choose an image',
    replace: 'Choose a different image',
    remove: 'Remove',
    removing: 'Removing…',
    upload: 'Save photograph',
    uploading: 'Saving…',
    cancel: 'Cancel',
    /** The cropper. */
    cropHeading: 'Choose what to show',
    cropHint:
      'Drag the image to move it, and use the slider to zoom. What sits inside the square is what ' +
      'the club keeps.',
    zoomLabel: 'Zoom',
    /** Said out loud, because it is the surprising part of a crop. */
    cropNote: 'Only the square is kept. The rest of the image is never uploaded.',
    /** Keyboard equivalents for the drag, announced where a mouse user would not need them. */
    keyboardHint: 'With the image focused, the arrow keys move it and plus and minus zoom.',
    tooLarge: 'That image is too large. Choose one under 8 MB.',
    notAnImage: 'That file is not an image. Choose a JPEG, PNG or WebP.',
    unreadable: 'That image could not be read. It may be damaged.',
    failed: 'Your photograph could not be saved just now. Try again.',
  },
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
  /*
   * Keyed on the *membership* status, not the account status. The two were one column until the
   * produce market arrived and they had to come apart — see `lib/club-membership.ts` and C27. The
   * account keys that used to be here, `inactive` among them, describe an identity rather than a
   * membership and never belonged on this card.
   *
   * `none` is the account that holds no membership at all. Unreachable behind the club gate, which
   * sends it to the front door, and written out anyway: a card that renders nothing for an
   * unexpected value looks broken at the exact moment something has gone wrong.
   */
  statusLabels: {
    active: 'Active',
    pending: 'Pending',
    pending_payment: 'Awaiting payment',
    suspended: 'Suspended',
    lapsed: 'Lapsed',
    sharing: 'On the register',
    none: 'Not a member',
  },
  statusNotes: {
    active: 'Your membership is in good standing.',
    pending: 'The club has not yet opened this membership.',
    pending_payment: 'Your membership opens as soon as a payment lands.',
    suspended: 'Access is suspended. Contact the club.',
    lapsed: 'Your subscription stopped paying. Renew to open the club again.',
    sharing: 'A placeholder held on the register by a cultivator.',
    none: 'This account has not joined the club.',
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
  DETAILS_CARD.editLabel,
  DETAILS_CARD.fixedNote,
  DETAILS_CARD.blank,
  ...Object.values(DETAILS_CARD.labels),
  PROFILE_COPY.title,
  PROFILE_COPY.heading,
  PROFILE_COPY.standfirst,
  ...Object.values(PROFILE_COPY.details),
  ...Object.values(PROFILE_COPY.identity),
  ...Object.values(PROFILE_COPY.photograph),
  MEMBERSHIP_CARD.heading,
  MEMBERSHIP_CARD.roleLabel,
  MEMBERSHIP_CARD.statusLabel,
  ...Object.values(MEMBERSHIP_CARD.statusLabels),
  ...Object.values(MEMBERSHIP_CARD.statusNotes),
  ...Object.values(PASSKEYS_CARD),
  ...Object.values(DESTINATIONS),
]

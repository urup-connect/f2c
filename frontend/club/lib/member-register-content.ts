/**
 * Every string on the administrator's membership screens.
 *
 * A module of its own rather than more keys in `club-content.ts`, following
 * `strain-catalogue-content.ts` -- but for a different reason, and the
 * difference is worth stating because the two files look alike.
 *
 * The catalogue's corpus is out of `ALL_CLUB_COPY` because it has to name `THC`
 * and `CBD` columns, which `CLINICAL_CLAIM` bans. **This corpus has no such
 * problem and takes no such scope.** It is held to `CLINICAL_CLAIM` in full,
 * along with `THERAPEUTIC_CLAIM`, `CURRENCY` and `ELIGIBILITY_CLAIM` -- there is
 * nothing on a membership register that needs to name a cannabinoid, quote an
 * amount or describe who may join, and a rule that is easy to keep should be
 * kept rather than relaxed by association.
 *
 * `RETAIL_VOICE` is the one pattern this is not held to, and the club area is
 * already exempt from it for the same reason: an administrative screen has to
 * say "order", "stock" and "delivery" because those are the club's own nouns for
 * its own records.
 *
 * ## Why the copy is here rather than in the components
 *
 * So that the rule above can be a test over an array. A sentence written inline
 * in a `.tsx` file is a sentence no compliance test reads.
 *
 * ## Two things this copy is careful about, beyond compliance
 *
 * **It never says "delete".** There is no delete on this screen and there is not
 * going to be one: suspension is reversible and erasure is a POPIA act in the
 * Django admin. Copy that offered a delete would be describing a button nobody
 * can build.
 *
 * **It says what reading an identity number costs before it is read.** The
 * masked form is the default and the full read is recorded against the member.
 * An administrator who learns that afterwards has already been recorded.
 */

/** The register: every account, narrowed by four filters, each row a way in. */
export const MEMBER_REGISTER = {
  title: 'Members',
  heading: 'The membership register',
  standfirst:
    'Every account the club holds, whatever it is for. Correct a detail, suspend an account, ' +
    'or lift a suspension. Appointing somebody a cultivator or an administrator is not done ' +
    'here — authority over other people’s records is granted by hand, in the back office.',

  /** The four narrowings, and the control that clears them. */
  filterHeading: 'Narrow the register',
  searchLabel: 'Search',
  searchHint:
    'Matches the name, the nickname and the email address. A full identity number matches ' +
    'exactly — a partial one matches nothing.',
  statusLabel: 'Standing',
  roleLabel: 'Role',
  joinedLabel: 'Joined',
  anyStatus: 'Any standing',
  anyRole: 'Any role',
  anyTime: 'Any time',
  clearLabel: 'Clear',

  /** The table. */
  columnMember: 'Member',
  columnRole: 'Role',
  columnStatus: 'Standing',
  columnMembership: 'Subscription',
  columnContact: 'Contact',
  columnJoined: 'Joined',

  /** In the standing column, beside a status that cannot sign in. */
  cannotSignIn: 'Cannot sign in',
  /** In the subscription column, for an account with no live arrangement. */
  noSubscription: 'None in force',
  paidUntil: 'Paid to',
  /** In the contact column, for an account whose address has been erased. */
  noContact: 'Erased',
  /** Against an erased row. */
  erasedBadge: 'Erased at the member’s request',

  empty: 'The register holds no accounts yet.',
  emptyFiltered: 'No account matches what you are narrowing by.',
  loadFailed: 'The register could not be read just now. What is shown may be out of date.',
} as const

/** The record screen: one member, and everything the club holds about them. */
export const MEMBER_RECORD = {
  backLabel: 'Back to the register',
  heading: 'Member record',
  detailsHeading: 'Details',
  detailsStandfirst:
    'The five things an administrator may correct. Everything else on this record is set ' +
    'somewhere it can be checked: the role in the back office, the standing by the buttons ' +
    'below, and the date of birth by the identity document itself.',

  firstNameLabel: 'First name',
  lastNameLabel: 'Last name',
  nicknameLabel: 'Nickname',
  nicknameHint:
    'What other members see. It may be left blank — the record then shows their full name ' +
    'instead.',
  emailLabel: 'Email address',
  emailHint: 'How they sign in. Changing it changes where their sign-in codes go.',
  mobileLabel: 'Mobile number',

  save: 'Save the record',
  saving: 'Saving…',
  saved: 'Saved.',
  unchanged: 'Nothing has changed yet.',
  refusedSummary: 'This record could not be saved. What needs fixing is marked below.',
  failed: 'The record could not be saved just now. Try again in a moment.',

  /** The read-only banner, and the two reasons for it. */
  readOnlyErased:
    'This account was erased at the member’s request. Its details are gone and cannot be ' +
    'written back. The row survives because the club’s own history points at it.',
  readOnlySharing:
    'This is a sharing member. Their record belongs to the cultivator who put them on the ' +
    'register, and it is changed there.',

  /** The facts the screen reports rather than offers. */
  factsHeading: 'On file',
  roleFact: 'Role',
  statusFact: 'Standing',
  joinedFact: 'Joined',
  updatedFact: 'Last changed',
  lastSeenFact: 'Last signed in',
  neverSeen: 'Never',
  birthFact: 'Date of birth',
  birthVerified: 'Checked against a document',
  birthUnverified: 'Taken from the identity number, not yet checked against a document',
  registeredByFact: 'Put on the register by',
  unknownFact: 'Not on file',
} as const

/** The subscription card: where a membership stands, and what this screen will not do to it. */
export const MEMBER_MEMBERSHIP = {
  heading: 'Subscription',
  standfirst:
    'The arrangement in force, if there is one. Pausing, cancelling and reversing a ' +
    'subscription are held by the platform operator rather than by the club, so none of them ' +
    'is offered here.',
  statusLabel: 'Standing',
  paidUntilLabel: 'Paid to',
  none: 'No subscription is in force against this account.',
} as const

/** The standing card: suspending an account, and lifting a suspension. */
export const MEMBER_STANDING = {
  heading: 'Access',
  standfirst:
    'Suspending an account blocks it from signing in and ends every session it has open. ' +
    'Nothing is deleted and nothing is lost — a suspension can be lifted from this card. ' +
    'Erasing an account is a separate act, and it is not done from this screen.',

  suspendLabel: 'Suspend this account',
  suspending: 'Suspending…',
  /** The standing itself, shown for as long as the account is suspended. */
  suspended: 'This account is suspended and cannot sign in.',
  /**
   * What just happened, announced once.
   *
   * Deliberately different words from `suspended` above. The two appear
   * together after a suspension — one is the state and one is the event — and
   * the same sentence twice reads as the screen having drawn something twice.
   */
  suspendedNow: 'Suspended. They have been signed out of every device.',
  confirmSuspendHeading: 'Suspend this account?',
  confirmSuspendBody:
    'They will be signed out of every device immediately and will not be able to sign in ' +
    'again until the suspension is lifted.',
  confirmSuspendAction: 'Yes, suspend',
  confirmCancel: 'Leave it as it is',

  reinstateLabel: 'Lift the suspension',
  reinstating: 'Lifting…',
  reinstated: 'The suspension has been lifted. This account can sign in again.',

  /** Why one of the buttons is not there. */
  cannotSuspendSelf:
    'You cannot suspend your own account. It would sign you out, and nobody could undo it ' +
    'on your behalf from this screen.',
  onlySuspendedCanBeReinstated:
    'Only a suspended account can be reinstated. This one is not blocked by the club.',
  failed: 'That could not be done just now. Try again in a moment.',
} as const

/** The identity card: the masked number, and the recorded read. */
export const MEMBER_IDENTITY = {
  heading: 'Identity document',
  standfirst:
    'The club shows the last four digits and nothing more. Putting the whole number on a ' +
    'screen puts it in the browser cache, the proxy logs and anyone standing behind you — so ' +
    'reading it in full is a deliberate act, and it is recorded against this member.',
  maskedLabel: 'Document on file',
  none: 'No identity document is on file for this member.',
  unreadable:
    'The number on file cannot be read back. That is a key or an integrity problem rather ' +
    'than a missing document, and somebody has to look at it.',

  revealLabel: 'Read the whole number',
  reasonLabel: 'Why do you need it?',
  reasonHint:
    'Recorded against this member, with your name and the time. Say enough that somebody ' +
    'reviewing this later understands it.',
  reasonTooShort: 'Say why the number has to be read — at least 10 characters.',
  confirmReveal: 'Read it, and record this',
  revealing: 'Reading…',
  cancelReveal: 'Never mind',
  revealed: 'Read, and recorded against this member.',
  hideLabel: 'Hide it again',
  failed: 'The number could not be read just now. Nothing has been recorded.',

  historyHeading: 'Who has read it',
  historyEmpty: 'Nobody has read this number through the register.',
  historyBy: 'Read by',
  historyUnknown: 'An account that no longer exists',
} as const

/** What the browser refuses before it asks the API. */
export const MEMBER_REFUSALS = {
  firstNameMissing: 'A first name is needed.',
  firstNameCharacters: 'That first name has characters a name does not usually have.',
  firstNameLong: 'That first name is too long.',
  lastNameMissing: 'A last name is needed.',
  lastNameCharacters: 'That last name has characters a name does not usually have.',
  lastNameLong: 'That last name is too long.',
  nicknameLength: 'A nickname is 3 to 20 characters long. Leave it blank if they want none.',
  nicknameCharacters:
    'A nickname can hold letters, numbers, spaces, hyphens, full stops and underscores.',
  nicknameShape:
    'A nickname starts with a letter, and does not end with or repeat a separator.',
  nicknameReserved: 'That nickname is kept for the club and cannot be given out.',
  emailMissing: 'An email address is needed. It is how this account signs in.',
  emailMalformed: 'That does not look like an email address.',
  emailLong: 'That email address is too long.',
  mobileMissing: 'A mobile number is needed.',
  mobileCharacters: 'A mobile number holds digits, spaces and an optional leading plus.',
  mobileLength: 'A South African mobile number has ten digits, or eleven after the country code.',
  mobileNotAMobile: 'That is not a mobile number. It looks like a landline or a service number.',
} as const

/**
 * Every line, for the compliance tests.
 *
 * Gathered from the objects rather than written again, so a key added above
 * cannot skip the rules without somebody also editing this line.
 */
export const ALL_MEMBER_REGISTER_COPY: readonly string[] = [
  ...Object.values(MEMBER_REGISTER),
  ...Object.values(MEMBER_RECORD),
  ...Object.values(MEMBER_MEMBERSHIP),
  ...Object.values(MEMBER_STANDING),
  ...Object.values(MEMBER_IDENTITY),
  ...Object.values(MEMBER_REFUSALS),
]

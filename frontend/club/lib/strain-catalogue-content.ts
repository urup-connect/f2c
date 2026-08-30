/**
 * Every string on the strain catalogue's administration screens.
 *
 * A module of its own rather than more keys in `club-content.ts`, and the reason
 * is a compliance one worth reading before adding a line here.
 *
 * `ALL_CLUB_COPY` is held to `CLINICAL_CLAIM`, which bans `thc`, `cbd`,
 * `potency` and `medic*` outright — and this corpus has to label the columns
 * `Strain.thc_content` and `Strain.cbd_content`. That is not an exemption being
 * taken; it is a corpus that was never in scope. These screens are back-office
 * tooling behind `platform.manage_strain_catalogue`: no member reads a word of
 * them, they replace the Django admin whose own `help_text` says "Typical THC,
 * as a percentage", and a form that could not name the column it writes would be
 * unusable. `copy-compliance.ts` records the scope decision in full.
 *
 * What this corpus *is* held to is `THERAPEUTIC_CLAIM` — the half of
 * `CLINICAL_CLAIM` that is an assertion rather than a vocabulary. "Relieves
 * anxiety" is refused here exactly as it would be on the landing page, because
 * the words an administrator reads are the words they will repeat to a member.
 * `Strain.description`'s own help text makes the same point to whoever types
 * into it: describe the plant, claim nothing about what it treats.
 *
 * ## Why the copy is here rather than in the components
 *
 * So that the rule above can be a test over an array. A sentence written inline
 * in a `.tsx` file is a sentence no compliance test reads.
 */

/** The list screen: the whole catalogue, and the way into every other screen. */
export const CATALOGUE_LIST = {
  title: 'Strain catalogue',
  heading: 'The strain catalogue',
  standfirst:
    'Every strain a cultivator may offer, platform-wide. Botanical facts only — what a grower ' +
    'charges and how much they undertake to deliver belongs to their own offer against a strain.',
  addLabel: 'Add a strain',
  termsLabel: 'Aromas and effects',
  /** The three narrowings, and the option that clears each one. */
  filterHeading: 'Narrow the list',
  searchLabel: 'Search',
  searchHint: 'Matches the name, the lineage and the breeder.',
  statusLabel: 'Status',
  typeLabel: 'Type',
  anyStatus: 'Any status',
  anyType: 'Any type',
  clearLabel: 'Clear',
  /** The table. */
  columnName: 'Strain',
  columnType: 'Type',
  columnStatus: 'Status',
  columnReserved: 'Reserved to',
  columnOffers: 'Offers',
  columnUpdated: 'Last changed',
  /** In the reserved column, for the normal case: any cultivator may offer it. */
  openToAll: 'Open to all',
  /** Beside a status that keeps a strain out of the member-facing catalogue. */
  notBrowsable: 'Not shown to members',
  offersSummary: 'listed of',
  empty: 'The catalogue holds no strains yet.',
  emptyFiltered: 'No strain matches what you are narrowing by.',
  loadFailed: 'The catalogue could not be read just now. Reload the page to try again.',
} as const

/** The form, shared by the add screen and the edit screen. */
export const STRAIN_FORM = {
  addHeading: 'Add a strain',
  addStandfirst:
    'A new strain starts as Pending, so the botanical facts can be checked before any ' +
    'cultivator offers it. Publish it by setting the status to Active.',
  editHeading: 'Edit this strain',
  /* ---------------------------------------------------------- identity */
  identityHeading: 'Identity',
  nameLabel: 'Name',
  nameHint: 'Unique across the catalogue. Case and spacing are ignored when checking that.',
  statusLabel: 'Status',
  statusHint: 'Only Active strains are shown to members and can be offered against.',
  typeLabel: 'Type',
  typeHint: 'The classification, not the parentage.',
  chooseOne: 'Choose one',
  exclusiveLabel: 'Reserved to',
  exclusiveHint:
    'Leave this blank for a strain any cultivator may offer. Setting it reserves the strain to ' +
    'one grower — their own genetics, which nobody else may offer. It does not make the strain ' +
    'theirs to edit.',
  exclusiveNobody: 'Any cultivator may offer it',
  /**
   * Appended to the reserved cultivator's name when they are no longer offerable.
   *
   * A grower who has left the club keeps their reservation in the column until an
   * administrator clears it — `Strain.exclusive_to` is `PROTECT` precisely so a
   * departing cultivator cannot take a catalogue entry with them, and clearing
   * this is what releases the strain back to the club. So the picker has to be
   * able to show a name it would not otherwise offer, marked, rather than falling
   * back to its empty option and misreporting the record as unreserved.
   */
  exclusiveDeparted: '— no longer a cultivator, clear this to release the strain',
  /* --------------------------------------------------------- botanical */
  botanicalHeading: 'Botanical',
  lineageLabel: 'Genetic lineage',
  lineageHint: 'Parentage as text, for example OG Kush x Durban Poison.',
  breederLabel: 'Breeder or origin',
  descriptionLabel: 'Description',
  descriptionHint:
    'Shown on the strain’s own page. Describe the plant; claim nothing about what it does for ' +
    'anyone.',
  /* ---------------------------------------------------------- chemical */
  chemicalHeading: 'Chemical profile',
  chemicalStandfirst:
    'Typical figures as percentages. Leave a field blank when nobody has measured it — blank ' +
    'means unknown, and a zero would be a statement about the plant.',
  thcLabel: 'THC %',
  cbdLabel: 'CBD %',
  cannabinoidsLabel: 'Minor cannabinoids',
  cannabinoidsHint: 'For example CBG against 0.8. Shown to members and never searched.',
  terpenesLabel: 'Terpenes',
  terpenesHint: 'For example myrcene against 0.5.',
  /* ----------------------------------------------------------- sensory */
  sensoryHeading: 'Aroma and effect',
  sensoryStandfirst:
    'A strain usually carries several of each. A term withdrawn from the club’s list cannot be ' +
    'added to a strain that does not already have it.',
  aromasLabel: 'Aromas',
  effectsLabel: 'Effects',
  noTerms: 'The club’s list is empty. Add a term first.',
  termsLinkLabel: 'Manage aromas and effects',
  /* ------------------------------------------------------- cultivation */
  cultivationHeading: 'Cultivation',
  cultivationStandfirst:
    'How the plant grows, whoever grows it. A cultivator’s own dates for an individual plant are ' +
    'a separate record.',
  floweringLabel: 'Weeks in flower',
  environmentLabel: 'Preferred environment',
  difficultyLabel: 'Difficulty',
  anyEnvironment: 'Not stated',
  anyDifficulty: 'Not stated',
  resistanceLabel: 'Disease and pest resistance',
  resistanceHint: 'For example botrytis against good.',
  /* ---------------------------------------------------------- controls */
  save: 'Save',
  saving: 'Saving…',
  saved: 'Saved.',
  create: 'Add to the catalogue',
  creating: 'Adding…',
  unchanged: 'Nothing has changed yet.',
  cancel: 'Back to the catalogue',
  refusedSummary: 'This could not be saved. See the fields marked below.',
} as const

/** The key/value editor the three free-form fields share. */
export const PAIR_EDITOR = {
  nameColumn: 'Name',
  valueColumn: 'Value',
  addLabel: 'Add another',
  removeLabel: 'Remove',
  /** Announced instead of the row number, which tells a screen reader nothing. */
  removeDescription: 'Remove this entry',
  empty: 'Nothing recorded.',
} as const

/** The card listing who offers a strain, and the retire control beneath it. */
export const OFFERS_CARD = {
  heading: 'Who offers this strain',
  standfirst:
    'Read-only. A grower’s price, minimum yield and product types are theirs to set, not an ' +
    'administrator’s to change while curating botanical facts.',
  empty: 'No cultivator offers this strain yet.',
  columnCultivator: 'Cultivator',
  columnStatus: 'Status',
  columnPrice: 'Grow price',
  columnYield: 'Minimum yield',
  columnTypes: 'Product types',
  columnPlants: 'Plants',
  noTypes: 'None',
  /** Grams, because that is the unit the statutory limits and the courier both use. */
  yieldUnit: 'g',
} as const

/** Retirement: what stands in for a delete, and the confirmation in front of it. */
export const RETIRE_CARD = {
  /*
   * The heading names the section and the action names the act, deliberately
   * different strings. Both read "Retire this strain" at first, which put the
   * same sentence on a card heading and on the button inside it -- redundant on
   * screen, and ambiguous to anything navigating by accessible name.
   */
  heading: 'Retirement',
  standfirst:
    'A strain is never deleted. Plants already growing against it are owned by members, so the ' +
    'record stays and the strain is retired instead — which takes it out of the members’ ' +
    'catalogue and every live offer against it off the shelf at once.',
  action: 'Retire this strain',
  retiring: 'Retiring…',
  confirmHeading: 'Retire this strain?',
  confirmAction: 'Yes, retire it',
  confirmCancel: 'Leave it as it is',
  /** Shown when there is nothing behind the strain, so nothing comes down with it. */
  noOffers: 'No cultivator offers this strain, so nothing else changes.',
  /** Both halves are filled in by the screen from the counts. */
  offersWarning: 'live offers come off the shelf.',
  plantsWarning:
    'plants are already growing against those offers. They are unaffected and stay with their ' +
    'owners.',
  reinstate: 'Set the status back to Active to bring it back.',
  alreadyRetired: 'This strain is already retired.',
  retired: 'Retired.',
  failed: 'The strain could not be retired just now.',
} as const

/** The aroma and effect vocabularies. */
export const TERMS_SCREEN = {
  title: 'Aromas and effects',
  heading: 'Aromas and effects',
  standfirst:
    'The club’s two lists of terms. A cultivator may ask for an addition; an administrator adds ' +
    'it here. Withdrawing a term stops it being offered on new strains and leaves every strain ' +
    'that already carries it untouched.',
  backLabel: 'Back to the catalogue',
  aromasHeading: 'Aromas',
  effectsHeading: 'Effects',
  addLabel: 'Add',
  adding: 'Adding…',
  newLabel: 'New term',
  nameLabel: 'Name',
  /**
   * The add button is inert while the field is empty, so this is only reached by
   * a browser that submits the form on Enter regardless. Worded properly anyway:
   * an unreachable branch that renders a column heading as an error message is
   * how a screen ends up saying "Name" in red.
   */
  blankName: 'A term needs a name.',
  saveLabel: 'Save',
  saving: 'Saving…',
  withdrawLabel: 'Withdraw',
  restoreLabel: 'Offer it again',
  withdrawnBadge: 'Withdrawn',
  usedBy: 'strains',
  usedByOne: 'strain',
  unused: 'Not used yet',
  empty: 'This list is empty.',
  loadFailed: 'The lists could not be read just now. Reload the page to try again.',
} as const

/**
 * Every string above, flattened.
 *
 * The compliance test reads a corpus rather than each object, so a line added to
 * any of them is checked without anybody remembering to add it here too — the
 * same arrangement `ALL_CLUB_COPY` has, and deliberately a *different* array.
 * See the module docstring on why these two corpora are held to different rules.
 */
export const ALL_CATALOGUE_COPY: readonly string[] = [
  ...Object.values(CATALOGUE_LIST),
  ...Object.values(STRAIN_FORM),
  ...Object.values(PAIR_EDITOR),
  ...Object.values(OFFERS_CARD),
  ...Object.values(RETIRE_CARD),
  ...Object.values(TERMS_SCREEN),
]

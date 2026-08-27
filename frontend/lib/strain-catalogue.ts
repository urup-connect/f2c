/**
 * The strain catalogue's own types and the rules a browser can apply to one.
 *
 * No React, no `fetch`, no DOM. The screens are thin because everything decidable
 * without the server is decided here and tested without a renderer — the same
 * split `lib/profile.ts` and `lib/registration.ts` make.
 *
 * ## What this refuses, and what it deliberately does not
 *
 * A browser can tell that a name is blank, that a percentage is not a number,
 * and that two rows of a key/value editor claim the same name. It cannot tell
 * whether "OG Kush" is already in the catalogue, or whether an account holds the
 * cultivator role. So this file refuses only the first kind, and the API's
 * refusals are rendered rather than treated as a drift — which is the opposite
 * of the profile form, where `checkProfile` duplicates every rule and an API
 * refusal means the two rule sets have diverged. Said plainly because the two
 * files look alike and behave differently on purpose.
 *
 * ## Why percentages are strings all the way through
 *
 * `thc_content` and `cbd_content` are `DECIMAL` columns and the API sends them
 * as JSON strings. Nothing here parses one into a `number` except to check that
 * it could be: `Number('12.35')` is not `12.35`, and a form that round-tripped a
 * percentage through a float would send back a value that disagrees with the
 * database. The input holds the string the administrator typed and the string is
 * what gets submitted.
 *
 * ## The key/value editor's model
 *
 * The three JSON columns are edited as a list of `{ key, value }` rows rather
 * than as an object, and the list is the state — not a derivation of it. Two
 * reasons, both discovered by trying the other way: an object cannot hold two
 * rows that are mid-edit and momentarily share a name, and an object has no
 * stable order, so re-deriving rows from it reorders the fields under the
 * administrator's cursor. `mappingFrom` and `pairsFrom` are the two crossings.
 */

/** A term in one of the two vocabularies, mirroring `TermOut`. */
export type Term = {
  id: string
  name: string
  slug: string
  /** False for a withdrawn term. Kept out of the pickers, shown where a strain still carries one. */
  is_available: boolean
  /** How many strains carry it. What makes withdrawing one a considered act. */
  strain_count: number
}

export type Vocabularies = {
  aromas: readonly Term[]
  effects: readonly Term[]
}

/**
 * One grower, as the *Reserved to* picker needs them. Mirrors `CultivatorOut`.
 *
 * Two fields, and `display_name` is the only name in the payload — section 6.6
 * of `roles-and-permissions.md` makes that the rule for every payload, and a
 * picker over the club's growers is exactly where it gets broken for the sake of
 * a nicer autocomplete.
 */
export type Cultivator = {
  id: string
  display_name: string
}

/** One cultivator's offer against a strain, read-only. Mirrors `ListingRowOut`. */
export type StrainListing = {
  id: string
  /** A `display_name`, never a legal name or an email address. */
  cultivator: string
  status: string
  /** A decimal string. Never parsed. */
  default_grow_price: string
  minimum_yield_grams: string
  short_description: string
  finished_product_types: readonly string[]
  /** `Plant.listing` is PROTECT, so anything above zero makes the listing permanent. */
  plant_count: number
  updated_at: string
}

/** One row on the administrator's list, mirroring `StrainRowOut`. */
export type StrainRow = {
  id: string
  name: string
  slug: string
  status: string
  strain_type: string
  /** The cultivator a strain is reserved to, or null for the normal case. */
  reserved_to: string | null
  listings_live: number
  listings_total: number
  updated_at: string
}

/** A strain in full, mirroring `StrainOut`. */
export type Strain = {
  id: string
  name: string
  slug: string
  status: string
  strain_type: string
  /** The reserved cultivator's id, for the picker. */
  exclusive_to: string | null
  /** The same cultivator's display name, for the screen. */
  reserved_to: string | null
  genetic_lineage: string
  breeder_origin: string
  description: string
  /** Decimal strings, or null when nobody has measured it. */
  thc_content: string | null
  cbd_content: string | null
  other_cannabinoids: Readonly<Record<string, string | number>>
  terpene_profile: Readonly<Record<string, string | number>>
  disease_resistance: Readonly<Record<string, string | number>>
  aromas: readonly Term[]
  effects: readonly Term[]
  flowering_time_weeks: number | null
  preferred_growing_environment: string
  difficulty_level: string
  listings: readonly StrainListing[]
  created_at: string
  updated_at: string
}

/* -------------------------------------------------------------------------- */
/* The choice lists                                                           */
/* -------------------------------------------------------------------------- */

/*
 * Mirroring the `TextChoices` in `app/strains/models.py`. Written out rather
 * than fetched, because these are not runtime data: they change when that file
 * changes, they are held by check constraints, and an endpoint answering with
 * them would be a round trip for a list that is fixed at deploy time. The
 * aromas and effects are the opposite — runtime rows an administrator extends —
 * which is why those come from `/api/catalogue/terms` and these do not.
 *
 * The value is what crosses the wire; the label is what an administrator reads.
 * Never the label in the column: `StrainStatus` learned that lesson before this
 * file existed, and its docstring records it.
 */

export const STRAIN_STATUSES = [
  { value: 'pending', label: 'Pending' },
  { value: 'active', label: 'Active' },
  { value: 'hidden', label: 'Hidden' },
  { value: 'inactive', label: 'Inactive' },
] as const

export const STRAIN_TYPES = [
  { value: 'indica', label: 'Indica' },
  { value: 'sativa', label: 'Sativa' },
  { value: 'hybrid', label: 'Hybrid' },
] as const

export const GROWING_ENVIRONMENTS = [
  { value: 'indoor', label: 'Indoor' },
  { value: 'outdoor', label: 'Outdoor' },
  { value: 'greenhouse', label: 'Greenhouse' },
] as const

export const DIFFICULTY_LEVELS = [
  { value: 'easy', label: 'Easy' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced' },
] as const

export const LISTING_STATUSES = [
  { value: 'draft', label: 'Draft' },
  { value: 'listed', label: 'Listed' },
  { value: 'withdrawn', label: 'Withdrawn' },
] as const

/** A choice's label, or the raw value when the API has one this build does not know. */
export const labelFor = (
  choices: readonly { value: string; label: string }[],
  value: string,
): string => choices.find((choice) => choice.value === value)?.label ?? value

/**
 * Whether a strain in this status is in front of members.
 *
 * Only `active` is, and `StrainQuerySet.browsable` is the authority. Used to
 * mark the list rather than to decide anything: a status column that says
 * "Hidden" without saying that hidden means invisible leaves an administrator
 * guessing which of the three non-active states takes a strain off the shelf.
 */
export const isBrowsable = (status: string): boolean => status === 'active'

/* -------------------------------------------------------------------------- */
/* The key/value editor                                                       */
/* -------------------------------------------------------------------------- */

/** One row of a JSON column's editor. The list of these is the form's state. */
export type Pair = {
  /**
   * Stable across edits, and the reason a row is not keyed by its index.
   *
   * Deleting the second of four rows shifts every index below it, so React
   * reuses the DOM node of row 3 for what is now row 2 — which moves the
   * administrator's cursor into a different field mid-sentence. An id assigned
   * once at creation survives every insertion and deletion.
   */
  id: string
  key: string
  value: string
}

/** The caps in `strains.services`, restated so the form can refuse before submitting. */
export const MAX_PAIRS = 40
export const MAX_PAIR_KEY_LENGTH = 40
export const MAX_PAIR_VALUE_LENGTH = 100

/**
 * A counter for `Pair.id`, per module rather than per editor.
 *
 * Module-scoped state, which is worth justifying because it usually is not.
 * These ids never leave the browser, never reach the API, and are only ever
 * compared with each other inside one list — so uniqueness across the module is
 * more than enough and shared state costs nothing. `crypto.randomUUID` would do
 * the same job and is not available in every test environment; a counter is.
 */
let pairSequence = 0

export const newPair = (key = '', value = ''): Pair => ({
  id: `pair-${(pairSequence += 1)}`,
  key,
  value,
})

/**
 * A JSON object as editor rows, in a stable order.
 *
 * Sorted by key rather than left in the object's own order. `Object.entries`
 * follows insertion order, which for a payload parsed from JSON is whatever the
 * database happened to serialise — so an administrator opening the same strain
 * twice could find myrcene above limonene one time and below it the next.
 * Alphabetical is arbitrary too, but it is the same arbitrary every time.
 *
 * Values are stringified, including numbers: the editor is a text field, and
 * `0.8` has to become `"0.8"` to be typed into one. `mappingFrom` puts the
 * number back.
 */
export const pairsFrom = (
  mapping: Readonly<Record<string, string | number>>,
): Pair[] =>
  Object.entries(mapping)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => newPair(key, String(value)))

/**
 * Editor rows as a JSON object, with numeric-looking values sent as numbers.
 *
 * The coercion is the interesting half. `{"CBG": 0.8}` is what the model's help
 * text asks for and `{"botrytis": "good"}` is what disease resistance holds, so
 * the column has to carry both — and the editor cannot ask an administrator
 * which they meant. A value that is a finite number *written as a number* is
 * sent as one; everything else is sent as the string it was typed as.
 *
 * `Number('')` is `0`, and `Number(' ')` is `0` as well, which is why the guard
 * checks for a non-empty trimmed string before trusting `Number`. Without it, a
 * row whose value the administrator cleared would be stored as zero — a claim
 * about the plant rather than the absence of one.
 *
 * Blank rows are dropped entirely. An editor always shows one empty row to type
 * into, and submitting that as `{"": ""}` would fail the service's own
 * blank-key rule for something the administrator never entered.
 */
export const mappingFrom = (
  pairs: readonly Pair[],
): Record<string, string | number> => {
  const mapping: Record<string, string | number> = {}

  for (const pair of pairs) {
    const key = pair.key.trim()
    if (!key) continue

    const value = pair.value.trim()
    const asNumber = Number(value)
    mapping[key] = value !== '' && Number.isFinite(asNumber) ? asNumber : pair.value
  }

  return mapping
}

/**
 * Why a set of editor rows cannot be submitted, or null.
 *
 * Duplicate keys are the refusal worth having. `mappingFrom` builds an object,
 * so two rows named "myrcene" silently become one and the administrator loses
 * whichever they typed first — with a save that reports success. Everything else
 * here is a length the service would refuse anyway, checked in the browser so
 * the common mistake never leaves it.
 */
export const pairsRefusal = (pairs: readonly Pair[]): string | null => {
  const named = pairs.filter((pair) => pair.key.trim() !== '')

  if (named.length > MAX_PAIRS) {
    return `This holds at most ${MAX_PAIRS} entries.`
  }

  const keys = named.map((pair) => pair.key.trim().toLowerCase())
  const duplicate = keys.find((key, index) => keys.indexOf(key) !== index)
  if (duplicate !== undefined) {
    return `“${duplicate}” is entered twice. Each entry needs its own name.`
  }

  const longKey = named.find((pair) => pair.key.trim().length > MAX_PAIR_KEY_LENGTH)
  if (longKey) {
    return `“${longKey.key.trim().slice(0, 20)}…” is too long — ${MAX_PAIR_KEY_LENGTH} characters at most.`
  }

  const longValue = named.find(
    (pair) => pair.value.trim().length > MAX_PAIR_VALUE_LENGTH,
  )
  if (longValue) {
    return `The value against “${longValue.key.trim()}” is too long — ${MAX_PAIR_VALUE_LENGTH} characters at most.`
  }

  return null
}

/* -------------------------------------------------------------------------- */
/* The form                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * The whole strain form as the browser holds it.
 *
 * Every scalar is a string, including the two percentages and the flowering
 * time, because an `input` holds a string and converting on every keystroke is
 * how a half-typed `1.` becomes `1` under the cursor. The crossing happens once,
 * in `submissionFrom`.
 */
export type StrainInput = {
  name: string
  status: string
  strainType: string
  /** A cultivator's id, or '' for the normal case: a strain any cultivator may offer. */
  exclusiveTo: string
  geneticLineage: string
  breederOrigin: string
  description: string
  thcContent: string
  cbdContent: string
  otherCannabinoids: readonly Pair[]
  terpeneProfile: readonly Pair[]
  diseaseResistance: readonly Pair[]
  aromas: readonly string[]
  effects: readonly string[]
  floweringTimeWeeks: string
  preferredGrowingEnvironment: string
  difficultyLevel: string
}

/** The body `PUT`/`POST` send, mirroring `StrainIn`. */
export type StrainSubmission = {
  name: string
  status: string
  strain_type: string
  exclusive_to: string | null
  genetic_lineage: string
  breeder_origin: string
  description: string
  thc_content: string | null
  cbd_content: string | null
  other_cannabinoids: Record<string, string | number>
  terpene_profile: Record<string, string | number>
  disease_resistance: Record<string, string | number>
  aromas: readonly string[]
  effects: readonly string[]
  flowering_time_weeks: number | null
  preferred_growing_environment: string
  difficulty_level: string
}

/**
 * A blank form, for the create screen.
 *
 * `pending` rather than `active`, matching the model's own default and
 * `member-roles.md`: an administrator typing in a strain a cultivator asked for
 * has not checked the botanical facts yet, and the checking comes before the
 * publishing. The field is on the form, so publishing in one step is still one
 * click away — the default just is not that.
 *
 * Each JSON editor starts with one empty row. A zero-row editor shows nothing
 * but an "add" button, which reads as a section with no fields rather than a
 * section that is empty.
 */
export const blankStrainInput = (): StrainInput => ({
  name: '',
  status: 'pending',
  strainType: '',
  exclusiveTo: '',
  geneticLineage: '',
  breederOrigin: '',
  description: '',
  thcContent: '',
  cbdContent: '',
  otherCannabinoids: [newPair()],
  terpeneProfile: [newPair()],
  diseaseResistance: [newPair()],
  aromas: [],
  effects: [],
  floweringTimeWeeks: '',
  preferredGrowingEnvironment: '',
  difficultyLevel: '',
})

/**
 * A stored strain as the form holds it.
 *
 * `?? ''` on both percentages: null means nobody has measured it, and an empty
 * field is what that looks like. A `'0'` there would be a claim about the plant.
 *
 * Each JSON editor gets a trailing empty row so there is always somewhere to
 * type. It is dropped again by `mappingFrom`, so a form opened and saved without
 * being touched stores exactly what it loaded.
 */
export const strainInputFrom = (strain: Strain): StrainInput => ({
  name: strain.name,
  status: strain.status,
  strainType: strain.strain_type,
  exclusiveTo: strain.exclusive_to ?? '',
  geneticLineage: strain.genetic_lineage,
  breederOrigin: strain.breeder_origin,
  description: strain.description,
  thcContent: strain.thc_content ?? '',
  cbdContent: strain.cbd_content ?? '',
  otherCannabinoids: [...pairsFrom(strain.other_cannabinoids), newPair()],
  terpeneProfile: [...pairsFrom(strain.terpene_profile), newPair()],
  diseaseResistance: [...pairsFrom(strain.disease_resistance), newPair()],
  aromas: strain.aromas.map((term) => term.id),
  effects: strain.effects.map((term) => term.id),
  floweringTimeWeeks:
    strain.flowering_time_weeks === null ? '' : String(strain.flowering_time_weeks),
  preferredGrowingEnvironment: strain.preferred_growing_environment,
  difficultyLevel: strain.difficulty_level,
})

/** A field the form can mark a refusal against, keyed as the API keys it. */
export type StrainFieldRefusal = {
  field: keyof StrainSubmission
  message: string
}

/** The largest a percentage can be, matching `MAX_PERCENT` in the model. */
const MAX_PERCENT = 100

/** The flowering-time range, matching the model's validators. */
const MIN_FLOWERING_WEEKS = 1
const MAX_FLOWERING_WEEKS = 52

/**
 * A percentage as it will be submitted, or a refusal.
 *
 * Blank is acceptable and means unknown, which is why the empty case returns a
 * `null` value rather than a refusal. Anything else has to parse as a number in
 * range — and the *string* is what is returned, not the parsed number: see the
 * module docstring on why a `DECIMAL` never goes through a float here.
 */
const checkPercent = (
  raw: string,
  field: 'thc_content' | 'cbd_content',
  label: string,
): { value: string | null } | { refusal: StrainFieldRefusal } => {
  const trimmed = raw.trim()
  if (trimmed === '') return { value: null }

  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) {
    return { refusal: { field, message: `${label} has to be a number, or blank.` } }
  }
  if (parsed < 0 || parsed > MAX_PERCENT) {
    return {
      refusal: { field, message: `${label} has to be between 0 and ${MAX_PERCENT}.` },
    }
  }

  return { value: trimmed }
}

export type StrainCheck =
  | { readonly status: 'valid'; readonly submission: StrainSubmission }
  | { readonly status: 'invalid'; readonly refusals: readonly StrainFieldRefusal[] }

/**
 * Everything about a submission a browser can decide, and the body if it passes.
 *
 * Every refusal is collected rather than returned at the first one. A form that
 * reports one problem at a time is a form somebody submits four times, and each
 * of those is a round trip.
 *
 * Note what is *not* checked: whether the name is already in the catalogue,
 * whether `exclusiveTo` holds the cultivator role, and whether an aroma has been
 * withdrawn. None is answerable here, all three are refused by the service, and
 * the screen renders those refusals against the same field keys this function
 * uses — which is what lets one renderer handle both sources.
 */
export const checkStrain = (input: StrainInput): StrainCheck => {
  const refusals: StrainFieldRefusal[] = []

  const name = input.name.trim()
  if (name === '') {
    refusals.push({ field: 'name', message: 'A strain needs a name.' })
  }

  if (input.status === '') {
    refusals.push({ field: 'status', message: 'Choose a status.' })
  }

  if (input.strainType === '') {
    refusals.push({
      field: 'strain_type',
      message: 'Choose Indica, Sativa or Hybrid.',
    })
  }

  const thc = checkPercent(input.thcContent, 'thc_content', 'THC')
  if ('refusal' in thc) refusals.push(thc.refusal)

  const cbd = checkPercent(input.cbdContent, 'cbd_content', 'CBD')
  if ('refusal' in cbd) refusals.push(cbd.refusal)

  let floweringWeeks: number | null = null
  const weeks = input.floweringTimeWeeks.trim()
  if (weeks !== '') {
    const parsed = Number(weeks)
    if (!Number.isInteger(parsed)) {
      refusals.push({
        field: 'flowering_time_weeks',
        message: 'Weeks in flower has to be a whole number, or blank.',
      })
    } else if (parsed < MIN_FLOWERING_WEEKS || parsed > MAX_FLOWERING_WEEKS) {
      refusals.push({
        field: 'flowering_time_weeks',
        message: `Weeks in flower has to be between ${MIN_FLOWERING_WEEKS} and ${MAX_FLOWERING_WEEKS}.`,
      })
    } else {
      floweringWeeks = parsed
    }
  }

  const editors = [
    { field: 'other_cannabinoids', pairs: input.otherCannabinoids },
    { field: 'terpene_profile', pairs: input.terpeneProfile },
    { field: 'disease_resistance', pairs: input.diseaseResistance },
  ] as const

  for (const editor of editors) {
    const refusal = pairsRefusal(editor.pairs)
    if (refusal) refusals.push({ field: editor.field, message: refusal })
  }

  if (refusals.length > 0) return { status: 'invalid', refusals }

  return {
    status: 'valid',
    submission: {
      name,
      status: input.status,
      strain_type: input.strainType,
      // '' is the picker's "any cultivator may offer it", and the API wants null
      // for that. An empty string would be an id nothing matches.
      exclusive_to: input.exclusiveTo === '' ? null : input.exclusiveTo,
      genetic_lineage: input.geneticLineage.trim(),
      breeder_origin: input.breederOrigin.trim(),
      description: input.description.trim(),
      thc_content: 'value' in thc ? thc.value : null,
      cbd_content: 'value' in cbd ? cbd.value : null,
      other_cannabinoids: mappingFrom(input.otherCannabinoids),
      terpene_profile: mappingFrom(input.terpeneProfile),
      disease_resistance: mappingFrom(input.diseaseResistance),
      aromas: input.aromas,
      effects: input.effects,
      flowering_time_weeks: floweringWeeks,
      preferred_growing_environment: input.preferredGrowingEnvironment,
      difficulty_level: input.difficultyLevel,
    },
  }
}

/** The message against one field, from either source, or undefined. */
export const refusalFor = (
  refusals: readonly StrainFieldRefusal[],
  field: keyof StrainSubmission,
): string | undefined => refusals.find((refusal) => refusal.field === field)?.message

/**
 * The API's per-field refusal body as this screen's own refusal list.
 *
 * `RefusedOut.fields` is keyed by the API's field names, which is why
 * `StrainFieldRefusal.field` is too: one renderer, two sources, no translation
 * table to keep in step. A key this build does not know is dropped rather than
 * rendered against nothing — and `detail` is always shown as well, so the
 * sentence is never lost even when its field is.
 */
export const refusalsFromApi = (
  fields: Readonly<Record<string, readonly string[]>>,
): StrainFieldRefusal[] => {
  const known = new Set<string>([
    'name',
    'status',
    'strain_type',
    'exclusive_to',
    'genetic_lineage',
    'breeder_origin',
    'description',
    'thc_content',
    'cbd_content',
    'other_cannabinoids',
    'terpene_profile',
    'disease_resistance',
    'aromas',
    'effects',
    'flowering_time_weeks',
    'preferred_growing_environment',
    'difficulty_level',
  ])

  return Object.entries(fields)
    .filter(([field, messages]) => known.has(field) && messages.length > 0)
    .map(([field, messages]) => ({
      field: field as keyof StrainSubmission,
      message: messages.join(' '),
    }))
}

/**
 * Whether a strain can be retired at all, and what retiring it would do.
 *
 * Never a refusal — retirement is always possible, which is the whole reason the
 * catalogue has no delete. This is what the confirmation says: how many live
 * offers come off the shelf, and how many plants are already growing against
 * them. The second number is the one that matters, because those plants are
 * owned by members and `Plant.listing` is `PROTECT`, so nothing about them
 * changes and nothing ever can.
 */
export type RetirementImpact = {
  readonly liveListings: number
  readonly plants: number
  readonly alreadyRetired: boolean
}

export const retirementImpact = (strain: Strain): RetirementImpact => ({
  liveListings: strain.listings.filter((listing) => listing.status === 'listed').length,
  plants: strain.listings.reduce((total, listing) => total + listing.plant_count, 0),
  alreadyRetired: strain.status === 'inactive',
})

import { describe, expect, test } from 'vitest'

import {
  DIFFICULTY_LEVELS,
  GROWING_ENVIRONMENTS,
  LISTING_STATUSES,
  MAX_PAIRS,
  MAX_PAIR_KEY_LENGTH,
  MAX_PAIR_VALUE_LENGTH,
  STRAIN_STATUSES,
  STRAIN_TYPES,
  blankStrainInput,
  checkStrain,
  isBrowsable,
  labelFor,
  mappingFrom,
  newPair,
  pairsFrom,
  pairsRefusal,
  refusalFor,
  refusalsFromApi,
  retirementImpact,
  strainInputFrom,
  type Pair,
  type Strain,
  type StrainInput,
  type StrainListing,
} from './strain-catalogue'

/*
 * The rules a browser can apply to a strain.
 *
 * Two things are asserted here that look like implementation detail and are not.
 *
 * A percentage never becomes a `number`. `Number('12.35')` is not 12.35, and a
 * DECIMAL column that round-trips through a float comes back disagreeing with
 * the database — so `checkStrain` returns the string it was given, and the test
 * for it asserts on `typeof`.
 *
 * A cleared value never becomes zero. `Number('')` is `0`, which is the trap
 * this file exists to sit in front of: a blank THC field means nobody measured
 * it, and a zero would be a statement about the plant.
 */

const listing = (overrides: Partial<StrainListing> = {}): StrainListing => ({
  id: 'listing-1',
  cultivator: 'Kloof',
  status: 'listed',
  default_grow_price: '950.00',
  minimum_yield_grams: '30.00',
  short_description: 'Grown slow, under glass.',
  finished_product_types: ['Pre-rolls'],
  plant_count: 0,
  updated_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

const strain = (overrides: Partial<Strain> = {}): Strain => ({
  id: 'strain-1',
  name: 'OG Kush',
  slug: 'og-kush',
  status: 'active',
  strain_type: 'hybrid',
  exclusive_to: null,
  reserved_to: null,
  genetic_lineage: '',
  breeder_origin: '',
  description: '',
  thc_content: null,
  cbd_content: null,
  other_cannabinoids: {},
  terpene_profile: {},
  disease_resistance: {},
  aromas: [],
  effects: [],
  flowering_time_weeks: null,
  preferred_growing_environment: '',
  difficulty_level: '',
  listings: [],
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

/** A valid form, so each test varies exactly one thing. */
const valid = (overrides: Partial<StrainInput> = {}): StrainInput => ({
  ...blankStrainInput(),
  name: 'Durban Poison',
  status: 'active',
  strainType: 'sativa',
  ...overrides,
})

const submissionOf = (input: StrainInput) => {
  const checked = checkStrain(input)
  if (checked.status !== 'valid') {
    throw new Error(`expected valid, got: ${JSON.stringify(checked.refusals)}`)
  }
  return checked.submission
}

const refusalsOf = (input: StrainInput) => {
  const checked = checkStrain(input)
  if (checked.status !== 'invalid') throw new Error('expected invalid')
  return checked.refusals
}

describe('the choice lists', () => {
  test('mirror the model’s own choices', () => {
    // Written out rather than fetched, because these change when the model
    // changes and are held by check constraints. A drift here is a strain the
    // API refuses for a value this form offered.
    expect(STRAIN_STATUSES.map((choice) => choice.value)).toEqual([
      'pending',
      'active',
      'hidden',
      'inactive',
    ])
    expect(STRAIN_TYPES.map((choice) => choice.value)).toEqual([
      'indica',
      'sativa',
      'hybrid',
    ])
    expect(GROWING_ENVIRONMENTS.map((choice) => choice.value)).toEqual([
      'indoor',
      'outdoor',
      'greenhouse',
    ])
    expect(DIFFICULTY_LEVELS.map((choice) => choice.value)).toEqual([
      'easy',
      'intermediate',
      'advanced',
    ])
    expect(LISTING_STATUSES.map((choice) => choice.value)).toEqual([
      'draft',
      'listed',
      'withdrawn',
    ])
  })

  test('never store the label in the column', () => {
    // `StrainStatus`'s docstring records the lesson: the earlier version stored
    // the display text, which makes renaming a label a data migration.
    for (const choice of [...STRAIN_STATUSES, ...STRAIN_TYPES]) {
      expect(choice.value).toBe(choice.value.toLowerCase())
    }
  })

  test('labelFor reads a label', () => {
    expect(labelFor(STRAIN_TYPES, 'hybrid')).toBe('Hybrid')
  })

  test('labelFor falls back to the raw value', () => {
    // A value the API has and this build does not. Showing it is worse than
    // showing nothing only if nothing is an option, and it is not: a blank
    // status cell reads as a strain with no status.
    expect(labelFor(STRAIN_TYPES, 'ruderalis')).toBe('ruderalis')
  })

  test('only active is in front of members', () => {
    expect(isBrowsable('active')).toBe(true)
    for (const status of ['pending', 'hidden', 'inactive']) {
      expect(isBrowsable(status)).toBe(false)
    }
  })
})

describe('the key/value editor', () => {
  test('gives every row an id of its own', () => {
    // Not keyed by index: deleting the second of four rows shifts every index
    // below it, which moves the cursor into a different field mid-sentence.
    const [first, second] = [newPair(), newPair()]

    expect(first.id).not.toBe(second.id)
  })

  test('reads an object into rows, sorted by name', () => {
    // `Object.entries` follows insertion order, which for a parsed payload is
    // whatever the database serialised. Alphabetical is arbitrary too, but it is
    // the same arbitrary every time the strain is opened.
    const pairs = pairsFrom({ myrcene: 0.5, limonene: 0.2 })

    expect(pairs.map((pair) => pair.key)).toEqual(['limonene', 'myrcene'])
  })

  test('stringifies a number so it can be typed into a text field', () => {
    expect(pairsFrom({ CBG: 0.8 })[0].value).toBe('0.8')
  })

  test('writes a numeric value back as a number', () => {
    expect(mappingFrom([newPair('CBG', '0.8')])).toEqual({ CBG: 0.8 })
  })

  test('leaves a non-numeric value a string', () => {
    // `{"CBG": 0.8}` and `{"botrytis": "good"}` are both things these columns
    // hold, and the editor cannot ask which was meant.
    expect(mappingFrom([newPair('botrytis', 'good')])).toEqual({ botrytis: 'good' })
  })

  test('does not turn a cleared value into zero', () => {
    // `Number('')` is 0. A row whose value was cleared would otherwise be stored
    // as a measurement of zero.
    expect(mappingFrom([newPair('CBG', '')])).toEqual({ CBG: '' })
  })

  test('drops a row with no name', () => {
    // The editor always shows one empty row to type into. Submitting it as
    // `{"": ""}` would fail the service's own blank-key rule for something
    // nobody entered.
    expect(mappingFrom([newPair('', ''), newPair('CBG', '0.8')])).toEqual({ CBG: 0.8 })
  })

  test('trims a name but not a value', () => {
    // The name is a key and has to match on the next read. The value is text an
    // administrator typed, and trimming it would silently edit their entry.
    expect(mappingFrom([newPair('  CBG  ', ' 0.8 ')])).toEqual({ CBG: 0.8 })
  })

  test('round-trips an object unchanged', () => {
    const original = { CBG: 0.8, botrytis: 'good' }

    expect(mappingFrom(pairsFrom(original))).toEqual(original)
  })

  test('refuses two rows claiming the same name', () => {
    // The refusal that matters. `mappingFrom` builds an object, so two rows
    // named "myrcene" silently become one and a save reports success having lost
    // whichever was typed first.
    const refusal = pairsRefusal([newPair('myrcene', '0.5'), newPair('myrcene', '0.2')])

    expect(refusal).toMatch(/twice/i)
  })

  test('folds case when looking for a duplicate', () => {
    expect(pairsRefusal([newPair('CBG', '1'), newPair('cbg', '2')])).not.toBeNull()
  })

  test('accepts two blank rows', () => {
    // Both are dropped, so they cannot collide.
    expect(pairsRefusal([newPair(), newPair()])).toBeNull()
  })

  test('refuses more entries than the column holds', () => {
    const many: Pair[] = Array.from({ length: MAX_PAIRS + 1 }, (_unused, index) =>
      newPair(`terpene-${index}`, '0.1'),
    )

    expect(pairsRefusal(many)).toMatch(new RegExp(String(MAX_PAIRS)))
  })

  test('accepts exactly as many as the column holds', () => {
    const many: Pair[] = Array.from({ length: MAX_PAIRS }, (_unused, index) =>
      newPair(`terpene-${index}`, '0.1'),
    )

    expect(pairsRefusal(many)).toBeNull()
  })

  test('refuses a name longer than the column allows', () => {
    const long = newPair('x'.repeat(MAX_PAIR_KEY_LENGTH + 1), '1')

    expect(pairsRefusal([long])).not.toBeNull()
  })

  test('refuses a value longer than the column allows', () => {
    const long = newPair('botrytis', 'y'.repeat(MAX_PAIR_VALUE_LENGTH + 1))

    expect(pairsRefusal([long])).not.toBeNull()
  })
})

describe('a blank form', () => {
  test('starts a strain as pending rather than active', () => {
    // Matching the model's default and `member-roles.md`: the botanical facts
    // are checked before the strain is published. The field is on the form, so
    // publishing in one step is still one click away.
    expect(blankStrainInput().status).toBe('pending')
  })

  test('chooses no type, so the administrator has to', () => {
    // A defaulted type is a type nobody looked at, and it reaches a check
    // constraint as a fact about a plant.
    expect(blankStrainInput().strainType).toBe('')
  })

  test('reserves the strain to nobody', () => {
    expect(blankStrainInput().exclusiveTo).toBe('')
  })

  test('gives each editor one row to type into', () => {
    const input = blankStrainInput()

    expect(input.otherCannabinoids).toHaveLength(1)
    expect(input.terpeneProfile).toHaveLength(1)
    expect(input.diseaseResistance).toHaveLength(1)
  })
})

describe('reading a stored strain into the form', () => {
  test('shows an unmeasured percentage as blank, not as zero', () => {
    const input = strainInputFrom(strain({ thc_content: null }))

    expect(input.thcContent).toBe('')
  })

  test('keeps a percentage as the string the API sent', () => {
    const input = strainInputFrom(strain({ thc_content: '18.50' }))

    expect(input.thcContent).toBe('18.50')
  })

  test('sets the picker from the reserved cultivator’s id', () => {
    const input = strainInputFrom(strain({ exclusive_to: 'user-7' }))

    expect(input.exclusiveTo).toBe('user-7')
  })

  test('holds the terms as ids', () => {
    const citrus = {
      id: 'aroma-1',
      name: 'Citrus',
      slug: 'citrus',
      is_available: true,
      strain_count: 3,
    }
    const input = strainInputFrom(strain({ aromas: [citrus] }))

    expect(input.aromas).toEqual(['aroma-1'])
  })

  test('leaves a trailing empty row in each editor', () => {
    const input = strainInputFrom(strain({ terpene_profile: { myrcene: 0.5 } }))

    expect(input.terpeneProfile).toHaveLength(2)
    expect(input.terpeneProfile[1].key).toBe('')
  })

  test('a form opened and saved untouched stores exactly what it loaded', () => {
    // The trailing row is dropped again by `mappingFrom`, so the no-op edit is
    // genuinely a no-op rather than a save that adds a blank entry.
    const stored = strain({ terpene_profile: { myrcene: 0.5 }, strain_type: 'hybrid' })

    expect(submissionOf(strainInputFrom(stored)).terpene_profile).toEqual({
      myrcene: 0.5,
    })
  })
})

describe('checking a submission', () => {
  test('accepts a complete form', () => {
    expect(checkStrain(valid()).status).toBe('valid')
  })

  test('refuses a blank name', () => {
    expect(refusalFor(refusalsOf(valid({ name: '  ' })), 'name')).toBeTruthy()
  })

  test('refuses a form with no type chosen', () => {
    expect(
      refusalFor(refusalsOf(valid({ strainType: '' })), 'strain_type'),
    ).toBeTruthy()
  })

  test('collects every refusal rather than stopping at the first', () => {
    // A form that reports one problem at a time is a form somebody submits four
    // times, and each of those is a round trip.
    const refusals = refusalsOf(valid({ name: '', strainType: '', thcContent: 'lots' }))

    expect(refusals.map((refusal) => refusal.field).sort()).toEqual([
      'name',
      'strain_type',
      'thc_content',
    ])
  })

  test('trims the text it submits', () => {
    expect(submissionOf(valid({ name: '  Cheese  ' })).name).toBe('Cheese')
  })

  test('sends a blank percentage as null', () => {
    expect(submissionOf(valid({ thcContent: '' })).thc_content).toBeNull()
  })

  test('sends a percentage as a string, never as a number', () => {
    // The reason: `Number('12.35')` is not 12.35, and this column is a DECIMAL.
    const submission = submissionOf(valid({ thcContent: '12.35' }))

    expect(submission.thc_content).toBe('12.35')
    expect(typeof submission.thc_content).toBe('string')
  })

  test('refuses a percentage that is not a number', () => {
    expect(refusalFor(refusalsOf(valid({ cbdContent: 'high' })), 'cbd_content')).toBeTruthy()
  })

  test('refuses a percentage over a hundred', () => {
    // 220 is a decimal point in the wrong place, not a strong plant — the
    // model's own comment on MAX_PERCENT.
    expect(refusalFor(refusalsOf(valid({ thcContent: '220' })), 'thc_content')).toBeTruthy()
  })

  test('refuses a negative percentage', () => {
    expect(refusalFor(refusalsOf(valid({ thcContent: '-1' })), 'thc_content')).toBeTruthy()
  })

  test('accepts zero as a measured percentage', () => {
    // Zero is a fact about a plant. Only blank means unknown.
    expect(submissionOf(valid({ cbdContent: '0' })).cbd_content).toBe('0')
  })

  test('sends a blank flowering time as null', () => {
    expect(submissionOf(valid({ floweringTimeWeeks: '' })).flowering_time_weeks).toBeNull()
  })

  test('sends a flowering time as a number', () => {
    // Unlike the percentages: this is a PositiveSmallIntegerField, so a number
    // is exact and is what the column holds.
    expect(submissionOf(valid({ floweringTimeWeeks: '9' })).flowering_time_weeks).toBe(9)
  })

  test('refuses a fractional flowering time', () => {
    expect(
      refusalFor(refusalsOf(valid({ floweringTimeWeeks: '9.5' })), 'flowering_time_weeks'),
    ).toBeTruthy()
  })

  test('refuses a flowering time beyond a year', () => {
    expect(
      refusalFor(refusalsOf(valid({ floweringTimeWeeks: '60' })), 'flowering_time_weeks'),
    ).toBeTruthy()
  })

  test('refuses a flowering time of zero', () => {
    expect(
      refusalFor(refusalsOf(valid({ floweringTimeWeeks: '0' })), 'flowering_time_weeks'),
    ).toBeTruthy()
  })

  test('sends no reserved cultivator as null rather than an empty string', () => {
    // An empty string is an id nothing matches, and the API's column is nullable
    // for exactly this case.
    expect(submissionOf(valid({ exclusiveTo: '' })).exclusive_to).toBeNull()
  })

  test('sends a chosen cultivator’s id', () => {
    expect(submissionOf(valid({ exclusiveTo: 'user-7' })).exclusive_to).toBe('user-7')
  })

  test('refuses a duplicate entry in a JSON editor, against that field', () => {
    const refusals = refusalsOf(
      valid({ terpeneProfile: [newPair('myrcene', '1'), newPair('myrcene', '2')] }),
    )

    expect(refusalFor(refusals, 'terpene_profile')).toBeTruthy()
  })

  test('checks all three editors separately', () => {
    const clash = [newPair('x', '1'), newPair('x', '2')]
    const refusals = refusalsOf(
      valid({
        otherCannabinoids: clash,
        terpeneProfile: clash,
        diseaseResistance: clash,
      }),
    )

    expect(refusals.map((refusal) => refusal.field).sort()).toEqual([
      'disease_resistance',
      'other_cannabinoids',
      'terpene_profile',
    ])
  })
})

describe('the API’s own refusals', () => {
  test('are keyed the same way the form’s are', () => {
    // One renderer, two sources. The form marks up `name` from either.
    const refusals = refusalsFromApi({
      name: ['A strain with that name already exists.'],
    })

    expect(refusalFor(refusals, 'name')).toBe('A strain with that name already exists.')
  })

  test('join several messages against one field into one sentence', () => {
    const refusals = refusalsFromApi({ name: ['First.', 'Second.'] })

    expect(refusalFor(refusals, 'name')).toBe('First. Second.')
  })

  test('drop a field this build does not know', () => {
    // Rendered against nothing is worse than not rendered: `detail` is always
    // shown as well, so the sentence is never lost.
    expect(refusalsFromApi({ invented_field: ['Something.'] })).toEqual([])
  })

  test('drop a field with no messages', () => {
    expect(refusalsFromApi({ name: [] })).toEqual([])
  })

  test('carry the refusals a browser could not have made', () => {
    // The three the form deliberately does not check: uniqueness across the
    // catalogue, whether an account holds the cultivator role, and whether a
    // term has been withdrawn.
    const refusals = refusalsFromApi({
      exclusive_to: ['A strain can only be reserved to an active cultivator.'],
      aromas: ['These terms are no longer offered on new strains: Gassy.'],
    })

    expect(refusals).toHaveLength(2)
  })
})

describe('what retiring a strain would do', () => {
  test('counts only the live offers', () => {
    // A withdrawn listing is already off the shelf, so retiring the strain does
    // not take it down — and saying it did would overstate the consequence.
    const impact = retirementImpact(
      strain({
        listings: [
          listing({ id: 'a', status: 'listed' }),
          listing({ id: 'b', status: 'withdrawn' }),
          listing({ id: 'c', status: 'draft' }),
        ],
      }),
    )

    expect(impact.liveListings).toBe(1)
  })

  test('totals the plants across every offer', () => {
    // Including withdrawn ones. Those plants exist and are owned by members
    // whatever the listing's status.
    const impact = retirementImpact(
      strain({
        listings: [
          listing({ id: 'a', status: 'listed', plant_count: 4 }),
          listing({ id: 'b', status: 'withdrawn', plant_count: 2 }),
        ],
      }),
    )

    expect(impact.plants).toBe(6)
  })

  test('reports a strain that is already retired', () => {
    expect(retirementImpact(strain({ status: 'inactive' })).alreadyRetired).toBe(true)
  })

  test('is never a refusal', () => {
    // Retirement is always possible, which is the whole reason the catalogue has
    // no delete: there is no state in which an administrator is stuck with a
    // strain they cannot take down.
    const impact = retirementImpact(
      strain({ listings: [listing({ plant_count: 99 })] }),
    )

    expect(impact.plants).toBe(99)
    expect(impact.alreadyRetired).toBe(false)
  })
})

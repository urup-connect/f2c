import { describe, expect, test } from 'vitest'
import { BRAND_IMAGERY } from './brand'
import { VALUE_ICONS } from './brand-icons'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'
import {
  ALL_COPY,
  FILM,
  FOOTER,
  HERO,
  JOIN,
  LEGAL,
  STORY,
  STRAPLINE_SEGMENTS,
  VALUES,
  WHY_JOIN,
} from './landing-content'

/* design/features/landing-page-engagement.md criteria 7, 9, 10, 12, 13, 14 and section 6.1.1. */

describe('hero copy', () => {
  test('names the club and carries the deck tagline', () => {
    expect(HERO.eyebrow).toBe('Cultivators Collective')
    expect(HERO.tagline).toBe('Growing together. Delivering excellence.')
  })

  test('keeps the proposition already approved in the root layout', () => {
    expect(HERO.proposition).toContain('A cannabis club for members, by cultivators.')
  })
})

describe('strapline', () => {
  test('carries the three segments the guidelines deck repeats', () => {
    expect(STRAPLINE_SEGMENTS).toEqual([
      'A cannabis club for members',
      'Grown by cultivators',
      'Made for community',
    ])
  })
})

describe('brand values', () => {
  test('has exactly four, labelled as the guidelines deck names them', () => {
    expect(VALUES.items.map((item) => item.label)).toEqual([
      'Community first',
      'Quality and care',
      'Sustainable cultivation',
      'Trust and transparency',
    ])
  })

  test('each carries a one-line description', () => {
    for (const item of VALUES.items) {
      expect(item.description.length).toBeGreaterThan(10)
      expect(item.description).toMatch(/\.$/)
    }
  })

  test('each names an icon that exists, and no two share one', () => {
    const iconKeys = VALUES.items.map((item) => item.iconKey)

    for (const key of iconKeys) expect(VALUE_ICONS[key]).toBeDefined()
    expect(new Set(iconKeys).size).toBe(iconKeys.length)
  })

  test('carries a section heading', () => {
    expect(VALUES.heading.length).toBeGreaterThan(0)
  })
})

describe('brand story', () => {
  test('is headed for the roots the emblem shows', () => {
    expect(STORY.heading).toBe('From root to harvest')
  })

  test('tells the roots-and-badge story in two paragraphs', () => {
    expect(STORY.paragraphs).toHaveLength(2)
    expect(STORY.paragraphs[0]).toMatch(/roots/i)
  })

  test('names the main image, which exists in the imagery manifest', () => {
    expect(BRAND_IMAGERY[STORY.imageKey]).toBeDefined()
  })

  test('has three steps, planted then tended then shared', () => {
    expect(STORY.steps.map((step) => step.label)).toEqual(['Planted', 'Tended', 'Shared'])
  })

  test('each step names an image that exists, and no two share one', () => {
    const imageKeys = STORY.steps.map((step) => step.imageKey)

    for (const key of imageKeys) expect(BRAND_IMAGERY[key]).toBeDefined()
    expect(new Set(imageKeys).size).toBe(imageKeys.length)
  })
})

describe('film copy', () => {
  test('heads the section and says what the film is, so it never stands alone', () => {
    expect(FILM.heading.length).toBeGreaterThan(0)
    expect(FILM.body).toMatch(/film/i)
  })

  test('names no file and no host, which belong in the film manifest', () => {
    for (const line of [FILM.heading, FILM.body]) {
      expect(line).not.toMatch(/https?:|\.mp4/i)
    }
  })
})

describe('why join copy', () => {
  test('names the club by the name the rest of the product uses', () => {
    expect(WHY_JOIN.body).toContain('Cultivators Collective')
    expect(WHY_JOIN.body).not.toMatch(/F2C/i)
  })

  test('lists five benefits, each a full sentence', () => {
    expect(WHY_JOIN.benefits).toHaveLength(5)
    for (const benefit of WHY_JOIN.benefits) {
      expect(benefit.length).toBeGreaterThan(20)
      expect(benefit).toMatch(/\.$/)
    }
  })

  test('heads the benefits separately from the section', () => {
    expect(WHY_JOIN.heading.length).toBeGreaterThan(0)
    expect(WHY_JOIN.benefitsHeading).toMatch(/benefit/i)
  })
})

describe('legal copy', () => {
  test('states the ground the club operates on', () => {
    expect(LEGAL.heading.length).toBeGreaterThan(0)
    expect(LEGAL.points.length).toBeGreaterThan(2)
  })

  test('names the age check without naming the threshold', () => {
    /*
     * The age gate is the one surface exempt from ELIGIBILITY_CLAIM. This section describes the
     * check the product performs; it does not say who may join.
     * See design/features/landing.md section 4.
     */
    expect(LEGAL.points.some((point) => /age check/i.test(point))).toBe(true)
  })

  test('rules out dealing and public consumption', () => {
    expect(LEGAL.points.some((point) => /dealing/i.test(point))).toBe(true)
  })
})

describe('join band copy', () => {
  test('invites the visitor to join', () => {
    expect(JOIN.heading.length).toBeGreaterThan(0)
    expect(JOIN.body).toMatch(/collective/i)
  })

  test('carries no caveat about the club being closed', () => {
    // The page describes the members area in the present tense; the two cannot both stand.
    // See design/features/landing.md risk 1.
    expect(Object.values(JOIN).join(' ')).not.toMatch(/not yet open/i)
  })
})

describe('footer copy', () => {
  test('carries a rights line with no year, so nothing goes stale', () => {
    expect(FOOTER.rights).toContain('Cultivators Collective')
    expect(FOOTER.rights).not.toMatch(/\d{4}/)
  })
})

describe('every line of copy on the page', () => {
  // Criterion 14. ALL_COPY is assembled in the module rather than in the test, so a new string
  // cannot be added to the page without this seeing it.
  test('is collected for review', () => {
    expect(ALL_COPY.length).toBeGreaterThan(15)
    expect(ALL_COPY).toContain(HERO.tagline)
    expect(ALL_COPY).toContain(FOOTER.rights)
    for (const segment of STRAPLINE_SEGMENTS) expect(ALL_COPY).toContain(segment)
    for (const item of VALUES.items) expect(ALL_COPY).toContain(item.description)
    for (const step of STORY.steps) expect(ALL_COPY).toContain(step.description)
    for (const benefit of WHY_JOIN.benefits) expect(ALL_COPY).toContain(benefit)
    for (const point of LEGAL.points) expect(ALL_COPY).toContain(point)
    expect(ALL_COPY).toContain(FILM.body)
  })

  /*
   * The patterns moved to src/lib/copy-compliance.ts when the age check became the second
   * surface with a corpus of its own. Same rules, one definition.
   */
  test('makes no medical, therapeutic or dosage claim', () => {
    for (const line of ALL_COPY) expect(line).not.toMatch(CLINICAL_CLAIM)
  })

  test('reads as a club rather than a shop', () => {
    for (const line of ALL_COPY) expect(line).not.toMatch(RETAIL_VOICE)
  })

  test('quotes no currency amount', () => {
    for (const line of ALL_COPY) {
      for (const pattern of CURRENCY) expect(line).not.toMatch(pattern)
    }
  })

  test('promises nothing about who may join, which legal has not yet written', () => {
    for (const line of ALL_COPY) expect(line).not.toMatch(ELIGIBILITY_CLAIM)
  })
})

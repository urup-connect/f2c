import { describe, expect, test } from 'vitest'
import { VALUE_ICONS, type BrandValueIconKey } from './brand-icons'

/*
 * design/features/landing-page-engagement.md criteria 10 and 11, section 6.4.
 *
 * The artwork is the guidelines deck's own vector icons, reissued as path data so it takes its
 * colour from `currentColor` and costs no extra request.
 */

describe('brand value icons', () => {
  const keys = Object.keys(VALUE_ICONS) as BrandValueIconKey[]

  test('covers the four values the guidelines deck names', () => {
    expect(keys).toEqual(['community', 'quality', 'sustainability', 'trust'])
  })

  test.each(keys)('%s declares a viewBox of four numbers', (key) => {
    expect(VALUE_ICONS[key].viewBox).toMatch(/^-?[\d.]+ -?[\d.]+ [\d.]+ [\d.]+$/)
  })

  test.each(keys)('%s carries path data starting at a move command', (key) => {
    // Either case: `M` is absolute and `m` relative, and the deck's artwork uses both.
    expect(VALUE_ICONS[key].path).toMatch(/^[Mm]/)
  })

  test.each(keys)('%s hardcodes no colour, so it can inherit currentColor', (key) => {
    // A fill or stroke baked into the path data would ignore the ground it is drawn on.
    expect(VALUE_ICONS[key].path).not.toMatch(/#[0-9a-f]{3,6}|fill=|stroke=/i)
  })

  test('no two values share the same artwork', () => {
    const paths = keys.map((key) => VALUE_ICONS[key].path)

    expect(new Set(paths).size).toBe(keys.length)
  })
})

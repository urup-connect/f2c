import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'

/**
 * Contract tests for the brand design tokens.
 *
 * These read the stylesheet as source text rather than through the DOM because jsdom does
 * not run Tailwind, so an `@theme` block is never resolved into computed styles at test time.
 * See design/features/brand-design-system.md section 7.
 */
const css = readFileSync(join(__dirname, 'globals.css'), 'utf8')

/** Strips comments so a token mentioned only in prose cannot satisfy a test. */
const code = css.replace(/\/\*[\s\S]*?\*\//g, '')

const declares = (token: string, value: string) =>
  new RegExp(`--${token}\\s*:\\s*${value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*;`, 'i').test(
    code,
  )

/** Every declared value for a token, in source order. A token may be declared more than once. */
const declarationsOf = (token: string) =>
  [...code.matchAll(new RegExp(`--${token}\\s*:\\s*([^;]+);`, 'g'))].map((match) =>
    match[1].trim(),
  )

/**
 * Expands `var()` references against the tokens this stylesheet declares, so a font stack can
 * be checked for a generic family even when the generic sits behind an indirection.
 */
const resolve = (value: string, seen: ReadonlySet<string> = new Set()): string =>
  value.replace(
    /var\(\s*(--[\w-]+)\s*(?:,([^)]*))?\)/g,
    (_match, name: string, fallback: string | undefined) => {
      if (seen.has(name)) return fallback?.trim() ?? ''
      const next = new Set(seen).add(name)
      const [declared] = declarationsOf(name.slice(2))
      if (declared !== undefined) return resolve(declared, next)
      return fallback ? resolve(fallback.trim(), next) : ''
    },
  )

/** A font stack is only safe if it ends in a generic family the browser always has. */
const GENERIC_TAIL =
  /(?:^|,)\s*(?:ui-sans-serif|ui-serif|ui-monospace|ui-rounded|sans-serif|serif|monospace|system-ui|cursive|fantasy)\s*$/

describe('brand colour tokens', () => {
  // design/features/brand-design-system.md section 6.1
  const colours: ReadonlyArray<readonly [string, string]> = [
    ['color-forest-green', '#1F3B2D'],
    ['color-forest-green-deep', '#0F1C13'],
    ['color-olive-green', '#7BA05D'],
    ['color-sage-green', '#C7D9B0'],
    ['color-cream-warm', '#F9F1E8'],
    ['color-cream-cool', '#F2F4ED'],
    ['color-bark', '#422B1C'],
    ['color-bark-light', '#725C4E'],
    ['color-ink', '#000000'],
    ['color-white', '#FFFFFF'],
    // Not from the guidelines deck. A placeholder, pending brand — risk 7 in that doc.
    ['color-clay-red', '#8E2F2A'],
  ]

  test.each(colours)('declares --%s as %s', (token, value) => {
    expect(declares(token, value)).toBe(true)
  })

  test('does not carry the create-next-app placeholder palette', () => {
    expect(code).not.toMatch(/#171717|#ededed|#0a0a0a/i)
  })

  test('the Forest Green typo from the guidelines deck is not adopted', () => {
    // The deck labels Forest Green as #F9F1E8. That value is the page ground, never the
    // primary. See design/features/brand-design-system.md risk 1.
    expect(declares('color-forest-green', '#F9F1E8')).toBe(false)
  })
})

describe('semantic colour aliases', () => {
  // design/features/brand-design-system.md section 6.1
  const aliases: ReadonlyArray<readonly [string, string]> = [
    ['color-background', 'var(--color-cream-warm)'],
    ['color-foreground', 'var(--color-bark)'],
    ['color-surface', 'var(--color-white)'],
    ['color-surface-muted', 'var(--color-cream-cool)'],
    ['color-primary', 'var(--color-forest-green)'],
    ['color-primary-foreground', 'var(--color-cream-warm)'],
    ['color-accent', 'var(--color-olive-green)'],
    ['color-border', 'var(--color-sage-green)'],
    ['color-error', 'var(--color-clay-red)'],
  ]

  test.each(aliases)('maps --%s to %s', (token, value) => {
    expect(declares(token, value)).toBe(true)
  })

  test('the error colour is reachable only through its semantic alias', () => {
    /*
     * design/features/age-gate-before-sign-up.md criterion 40. The red is a placeholder the
     * brand owner has not supplied, so replacing it must be one hex and no call-site edits.
     * That only holds while `clay-red` is declared once and named nowhere else.
     */
    expect(declarationsOf('color-clay-red')).toHaveLength(1)
    expect([...code.matchAll(/var\(\s*--color-clay-red/g)]).toHaveLength(1)
  })
})

describe('typography tokens', () => {
  // design/features/brand-design-system.md section 6.2
  test('routes --font-sans through the DM Sans variable supplied by next/font', () => {
    expect(declarationsOf('font-sans').at(0)).toContain('var(--font-dm-sans)')
  })

  test('routes --font-display through the Playfair Display variable supplied by next/font', () => {
    expect(declarationsOf('font-display').at(0)).toContain('var(--font-playfair-display)')
  })

  /*
   * next/font injects these two on <html> through a generated class, so nothing in the
   * stylesheet itself defines them. Declaring them anyway keeps them resolvable for static
   * analysis and guarantees a usable stack if the font ever fails to load.
   */
  test.each(['font-dm-sans', 'font-playfair-display'])('declares --%s as a fallback', (token) => {
    expect(declarationsOf(token).length).toBeGreaterThan(0)
  })

  test('references no custom property it does not itself declare', () => {
    const referenced = [...code.matchAll(/var\(\s*--([\w-]+)/g)].map((match) => match[1])
    const undeclared = [...new Set(referenced)].filter(
      (token) => declarationsOf(token).length === 0,
    )

    expect(undeclared).toEqual([])
  })

  test('every font-family resolves to a stack ending in a generic family', () => {
    const stacks = [...code.matchAll(/font-family\s*:\s*([^;]+);/g)].map((match) =>
      match[1].trim(),
    )

    expect(stacks.length).toBeGreaterThan(0)
    for (const stack of stacks) {
      expect(resolve(stack)).toMatch(GENERIC_TAIL)
    }
  })

  test.each(['font-sans', 'font-display', 'font-dm-sans', 'font-playfair-display'])(
    '--%s ends in a generic family once resolved',
    (token) => {
      for (const value of declarationsOf(token)) {
        expect(resolve(value)).toMatch(GENERIC_TAIL)
      }
    },
  )

  test('does not reference the create-next-app Geist fonts', () => {
    expect(code).not.toMatch(/geist/i)
  })

  test.each([
    ['tracking-display', '-0.02em'],
    ['tracking-label', '0.12em'],
  ])('declares --%s as %s', (token, value) => {
    expect(declares(token, value)).toBe(true)
  })
})

describe('shape tokens', () => {
  // design/features/brand-design-system.md section 6.3
  test.each([
    ['radius-card', '1rem'],
    ['radius-control', '0.75rem'],
    ['radius-pill', '9999px'],
  ])('declares --%s as %s', (token, value) => {
    expect(declares(token, value)).toBe(true)
  })
})

describe('colour scheme', () => {
  // design/features/brand-design-system.md risk 6
  test('does not switch theme on the OS dark preference', () => {
    expect(code).not.toMatch(/prefers-color-scheme/i)
  })

  test('scopes the dark variant to an opt-in class so it cannot fire unreviewed', () => {
    expect(code).toMatch(/@custom-variant\s+dark\s*\([^)]*\.dark/)
  })
})

describe('contrast (WCAG 2.1)', () => {
  // design/features/brand-design-system.md section 8
  const channel = (c: number) => {
    const s = c / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }

  const luminance = (hex: string) => {
    const h = hex.replace('#', '')
    const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(h.slice(i, i + 2), 16))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
  }

  const ratio = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  const AA_BODY = 4.5

  test.each([
    ['bark on cream-warm', '#422B1C', '#F9F1E8'],
    ['bark on cream-cool', '#422B1C', '#F2F4ED'],
    ['bark on white', '#422B1C', '#FFFFFF'],
    ['bark-light on cream-warm', '#725C4E', '#F9F1E8'],
    ['forest-green on cream-warm', '#1F3B2D', '#F9F1E8'],
    ['cream-warm on forest-green', '#F9F1E8', '#1F3B2D'],
    ['white on forest-green', '#FFFFFF', '#1F3B2D'],
    ['cream-warm on forest-green-deep', '#F9F1E8', '#0F1C13'],
    ['sage-green on forest-green', '#C7D9B0', '#1F3B2D'],
    // design/features/landing-page-engagement.md section 8, criterion 22
    ['forest-green on sage-green', '#1F3B2D', '#C7D9B0'],
    ['forest-green on cream-cool', '#1F3B2D', '#F2F4ED'],
    ['bark-light on cream-cool', '#725C4E', '#F2F4ED'],
    ['forest-green on white', '#1F3B2D', '#FFFFFF'],
    ['sage-green on forest-green-deep', '#C7D9B0', '#0F1C13'],
    ['bark-light on white', '#725C4E', '#FFFFFF'],
    // design/features/age-gate-before-sign-up.md criterion 41
    ['clay-red on white', '#8E2F2A', '#FFFFFF'],
    ['clay-red on cream-warm', '#8E2F2A', '#F9F1E8'],
    ['clay-red on cream-cool', '#8E2F2A', '#F2F4ED'],
  ])('%s meets AA for body text', (_name, fg, bg) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY)
  })

  test.each([
    ['olive-green on cream-warm', '#7BA05D', '#F9F1E8'],
    ['sage-green on cream-warm', '#C7D9B0', '#F9F1E8'],
    // Why clay-red is a light-ground colour only: a dark red on the primary green is a smudge.
    ['clay-red on forest-green', '#8E2F2A', '#1F3B2D'],
  ])('%s fails AA, so it stays a decorative colour only', (_name, fg, bg) => {
    // Guards the section 8 constraint: these are fills and borders, never body copy.
    expect(ratio(fg, bg)).toBeLessThan(AA_BODY)
  })
})

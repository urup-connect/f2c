import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, test } from 'vitest'
import { BRAND_IMAGERY, BRAND_LOGOS, type BrandImageKey, type BrandLogoVariant } from './brand'

const PUBLIC_DIR = join(process.cwd(), 'public')

/** The directories production source lives in. There is no src/ in this project. */
const SOURCE_ROOTS = ['app', 'components', 'lib'] as const

/**
 * Every production TypeScript source file, so a stale asset reference cannot hide.
 *
 * Test files are excluded because a test that names an asset in order to assert its absence
 * would otherwise match itself.
 */
const filesUnder = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return filesUnder(path)
    if (/\.(test|spec)\.tsx?$/.test(entry.name)) return []
    return /\.tsx?$/.test(entry.name) ? [path] : []
  })

const sourceFiles = (): string[] =>
  SOURCE_ROOTS.flatMap((root) => filesUnder(join(process.cwd(), root)))


/** Reads width and height out of a PNG IHDR chunk, so no image library is needed. */
const pngSize = (path: string) => {
  const buffer = readFileSync(path)
  const isPng = buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  if (!isPng) return null
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) }
}

describe('brand logo variants', () => {
  // design/features/brand-design-system.md section 6.4
  const variants = Object.keys(BRAND_LOGOS) as BrandLogoVariant[]

  test('covers every ground the guidelines supply artwork for', () => {
    expect(variants).toEqual(['onCream', 'onForestGreen', 'onBlack', 'mark'])
  })

  test.each(variants)('%s points at a path served from public/', (variant) => {
    expect(BRAND_LOGOS[variant].src).toMatch(/^\/brand\/[a-z0-9-]+\.png$/)
  })

  test.each(variants)('%s exists on disk as a real PNG', (variant) => {
    const path = join(PUBLIC_DIR, BRAND_LOGOS[variant].src)

    expect(existsSync(path)).toBe(true)
    expect(pngSize(path)).not.toBeNull()
  })

  test.each(variants)('%s declares the dimensions of the file it points at', (variant) => {
    const { src, width, height } = BRAND_LOGOS[variant]

    // Declared dimensions must match the file, or next/image reserves the wrong space.
    expect(pngSize(join(PUBLIC_DIR, src))).toEqual({ width, height })
  })

  test.each(variants)('%s carries alt text naming the brand', (variant) => {
    expect(BRAND_LOGOS[variant].alt).toMatch(/Cultivators Collective/)
  })

  test('the three badge variants are square, as the circular emblem requires', () => {
    for (const variant of ['onCream', 'onForestGreen', 'onBlack'] as const) {
      const { width, height } = BRAND_LOGOS[variant]
      expect(width).toBe(height)
    }
  })
})

describe('brand imagery', () => {
  // design/features/landing-page-engagement.md criteria 15, 17, 18 and section 6.4.
  const keys = Object.keys(BRAND_IMAGERY) as BrandImageKey[]
  const IMAGERY_DIR = join(PUBLIC_DIR, 'imagery')

  test('covers the four photographs taken from the guidelines deck', () => {
    expect(keys).toEqual(['leafCanopy', 'fieldSunrise', 'glovedHarvest', 'handsSeedling'])
  })

  test.each(keys)('%s points at a path served from public/imagery/', (key) => {
    expect(BRAND_IMAGERY[key].src).toMatch(/^\/imagery\/[a-z0-9-]+\.png$/)
  })

  test.each(keys)('%s exists on disk as a real PNG', (key) => {
    const path = join(PUBLIC_DIR, BRAND_IMAGERY[key].src)

    expect(existsSync(path)).toBe(true)
    expect(pngSize(path)).not.toBeNull()
  })

  test.each(keys)('%s declares the dimensions of the file it points at', (key) => {
    const { src, width, height } = BRAND_IMAGERY[key]

    // Declared dimensions must match the file, or next/image reserves the wrong space and the
    // page shifts as the image loads.
    expect(pngSize(join(PUBLIC_DIR, src))).toEqual({ width, height })
  })

  test.each(keys)('%s can never be drawn below 2x', (key) => {
    const { width, maxRenderedWidth } = BRAND_IMAGERY[key]

    /*
     * Criterion 15. The deck's photographs are small, and the failure mode is not that they
     * look bad today — it is somebody reusing one in a hero later. The ceiling travels with
     * the asset and this is what enforces it.
     */
    expect(maxRenderedWidth * 2).toBeLessThanOrEqual(width)
  })

  test.each(keys)('%s carries descriptive alternative text', (key) => {
    const { alt } = BRAND_IMAGERY[key]

    expect(alt.length).toBeGreaterThan(15)
    // "Image of" and "photo of" are noise a screen reader already announces.
    expect(alt).not.toMatch(/^(an? )?(image|photo|picture|photograph)\b/i)
  })

  test('no photograph of an identifiable person is served', () => {
    /*
     * Criterion 18. The deck's imagery set includes a cultivator's face. Publishing an
     * identifiable person needs their consent and the deck records none, so the file is not
     * in the repository at all — asserting the directory's contents is what keeps it out.
     * See design/features/landing-page-engagement.md section 9.
     */
    const onDisk = readdirSync(IMAGERY_DIR).sort()
    const declared = keys.map((key) => BRAND_IMAGERY[key].src.replace('/imagery/', '')).sort()

    expect(onDisk).toEqual(declared)
  })
})

describe('starter template artwork', () => {
  // design/features/public-landing-and-auth-routing.md criterion 4.
  const starterSvgs = ['file.svg', 'globe.svg', 'next.svg', 'vercel.svg', 'window.svg']

  test.each(starterSvgs)('%s is gone from public/', (name) => {
    expect(existsSync(join(PUBLIC_DIR, name))).toBe(false)
  })

  test('no source file still references one', () => {
    const referenced = sourceFiles().filter((file) => {
      const contents = readFileSync(file, 'utf8')
      return starterSvgs.some((name) => contents.includes(name))
    })

    expect(referenced).toEqual([])
  })
})

/**
 * Brand logo artwork, as supplied by the 2026 brand guidelines.
 *
 * Components reference these rather than hardcoding paths, so the artwork can be replaced
 * in one place and so the declared dimensions stay in step with the files on disk.
 * See design/features/brand-design-system.md section 6.4.
 */

export type BrandLogo = {
  /** Path under public/, served from the site root. */
  readonly src: string
  readonly width: number
  readonly height: number
  readonly alt: string
  /** The background this variant is drawn for. */
  readonly ground: string
}

export const BRAND_LOGOS = {
  /** Default badge. Cream ground, dark green emblem. */
  onCream: {
    src: '/brand/logo-badge-cream.png',
    width: 502,
    height: 502,
    alt: 'Cultivators Collective',
    ground: 'cream-warm',
  },
  /** Badge reversed out of the primary green. */
  onForestGreen: {
    src: '/brand/logo-badge-on-green.png',
    width: 502,
    height: 502,
    alt: 'Cultivators Collective',
    ground: 'forest-green',
  },
  /** Badge reversed out of black. */
  onBlack: {
    src: '/brand/logo-badge-on-black.png',
    width: 502,
    height: 502,
    alt: 'Cultivators Collective',
    ground: 'ink',
  },
  /** Compact "CC" mark on a transparent ground. The source of the site icons. */
  mark: {
    src: '/brand/logo-mark-cc.png',
    width: 922,
    height: 615,
    alt: 'Cultivators Collective',
    ground: 'transparent',
  },
} as const satisfies Record<string, BrandLogo>

export type BrandLogoVariant = keyof typeof BRAND_LOGOS

/**
 * Photography taken from the 2026 guidelines deck's imagery-style slide.
 *
 * Every entry declares the largest CSS width it may be rendered at, set so the file is never
 * drawn below 2x. The deck's photographs are small, and the failure mode is not that they look
 * bad today — it is somebody reusing one in a hero later. The ceiling travels with the asset,
 * a unit test asserts it, and `Brand/BrandImage` refuses a wider request at the call site.
 *
 * The deck's photograph of a cultivator's face is deliberately absent: publishing an
 * identifiable person needs their consent and the deck records none.
 * See design/features/landing-page-engagement.md sections 6.2, 6.4 and 9.
 */
export type BrandImage = {
  /** Path under public/, served from the site root. */
  readonly src: string
  /** Intrinsic pixel dimensions of the file on disk. */
  readonly width: number
  readonly height: number
  readonly alt: string
  /** Largest CSS width this file may be rendered at. Never more than half its intrinsic width. */
  readonly maxRenderedWidth: number
}

export const BRAND_IMAGERY = {
  leafCanopy: {
    src: '/imagery/leaf-canopy.png',
    width: 1076,
    height: 717,
    alt: 'A cannabis plant in full leaf, lit from above against dense foliage',
    maxRenderedWidth: 520,
  },
  fieldSunrise: {
    src: '/imagery/field-sunrise.png',
    width: 734,
    height: 543,
    alt: 'Rows of cannabis plants in an open field at first light',
    maxRenderedWidth: 160,
  },
  glovedHarvest: {
    src: '/imagery/gloved-harvest.png',
    width: 358,
    height: 298,
    alt: 'A gloved hand supporting a mature flowering branch',
    maxRenderedWidth: 160,
  },
  handsSeedling: {
    src: '/imagery/hands-seedling.png',
    width: 288,
    height: 278,
    alt: 'Two cupped hands holding a young seedling in dark soil',
    maxRenderedWidth: 140,
  },
} as const satisfies Record<string, BrandImage>

export type BrandImageKey = keyof typeof BRAND_IMAGERY

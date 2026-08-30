/**
 * What the store calls itself, in one place.
 *
 * The name is *Farm to Consumer*, shortened to *F2C* - which is what the platform's own package and
 * its mail configuration already call this storefront, and what the logo sets in type.
 *
 * **Nothing outside this file spells the name.** A component reading `STORE_BRAND.name` costs one
 * import; a component with the words typed into it is a find-and-replace across the application the
 * day marketing settles on something else.
 *
 * **There is a mark now, and it is vector.** This file used to record the opposite - no logo, the
 * wordmark set in the display face - because the store had no brand and an asset nobody had
 * commissioned was a liability. `design/F2C_new_logo-removebg-preview - Edited 1.png` settled it.
 * The mark is traced into `components/Brand/Mark.tsx` rather than served as an image, so it scales,
 * takes its colours from the palette, and costs no request. The palette in `app/globals.css` is
 * sampled from the same file.
 *
 * Type is still unsettled: the logo fixes colour, not typefaces. See `app/layout.tsx`.
 */
export const STORE_BRAND = {
  /** The full name, as it appears in a title, an email signature and a legal page. */
  name: 'Farm to Consumer',
  /** The short form, for a tab, a badge and anywhere the full name would wrap. */
  shortName: 'F2C',
  /**
   * One sentence saying what this is, for the document description and the front door.
   *
   * Names produce and price openly, which the club's copy rules forbid and the store's do not —
   * `frontend/club/lib/copy-compliance.ts` is a cannabis constraint and is not shared. A market
   * that could not name a price would not be a market.
   */
  standfirst:
    'Fresh produce bought straight from the farm that grew it. Real prices, named farms, delivered.',
} as const

/** The storefront code Django knows this application by. See `app/core/storefronts/models.py`. */
export const STOREFRONT_CODE = 'market' as const

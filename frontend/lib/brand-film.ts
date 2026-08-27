/**
 * The club's brand film, as served from the static content host.
 *
 * A manifest rather than a path inlined at the call site, for the same reason `brand.ts` holds
 * one: the file can be replaced in a single place, and the declared dimensions stay in step with
 * the file itself. Unlike the photographs under `public/`, this one is too large to ship with the
 * application, so it lives on the CDN and the address is assembled from `CDN_BASE_URL`.
 *
 * Pure, and taking a `SiteConfig` rather than reading one: importing this module validates no
 * configuration, so the manifest can be read by anything. The component supplies the running
 * application's config, exactly as `app/robots.ts` does for `lib/seo.ts`.
 *
 * See design/features/landing.md section 3.
 */

import type { SiteConfig } from './site'

export type BrandFilm = {
  /** Path beneath the CDN base, with a leading slash. */
  readonly path: string
  /** Intrinsic pixel dimensions of the file, so the page can reserve the right box. */
  readonly width: number
  readonly height: number
  /** Rounded up from the file's own duration. Recorded so nobody has to download it to find out. */
  readonly durationSeconds: number
  /**
   * The still frame shown before the film plays, also beneath the CDN base.
   *
   * A separate path rather than one derived from the film's, because the two are different file
   * types on a host neither this application nor Django controls. Deriving it would turn a
   * renamed asset into a silently broken image.
   */
  readonly posterPath: string
  /** Intrinsic dimensions of the still. 1201x675 is 16:9 to within a pixel of the film. */
  readonly posterWidth: number
  readonly posterHeight: number
}

export const BRAND_FILM = {
  path: '/media/26-cultivatorscollective.mp4',
  width: 1920,
  height: 1080,
  durationSeconds: 62,
  posterPath: '/media/26-cultivatorscollective.webp',
  posterWidth: 1201,
  posterHeight: 675,
} as const satisfies BrandFilm

/**
 * Where the film is served from, for a given deployment.
 *
 * `cdnBaseUrl` is normalised without a trailing slash by `readSiteConfig`, which is what lets
 * this concatenate rather than having to reason about the join.
 */
export const brandFilmSource = (config: SiteConfig): string => `${config.cdnBaseUrl}${BRAND_FILM.path}`

/**
 * Where the still frame is served from.
 *
 * The poster is an ordinary image as far as the browser is concerned, so it needs none of the
 * cross-origin handling a caption track does. See design/features/landing.md section 3.
 */
export const brandFilmPoster = (config: SiteConfig): string =>
  `${config.cdnBaseUrl}${BRAND_FILM.posterPath}`

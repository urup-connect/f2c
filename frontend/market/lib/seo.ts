/**
 * What search engines are told, in one place.
 *
 * **The store's indexable set is larger than the club's, and it is the first genuine divergence
 * between the two applications.** The club permits exactly one indexable route, because everything
 * else it serves is either behind a session or subject to cannabis copy rules. A store's public
 * pages are meant to be found: the front door, and the legal pages a shopper is entitled to read
 * before they buy. Nothing under `/account` is ever indexable, and neither is sign-in.
 *
 * When the catalogue arrives it belongs on this list, and it belongs *here* rather than in the page
 * itself: a route that decides its own indexability is a route that can be added to the index
 * without anybody choosing to add it.
 */

import type { SiteConfig } from './site'

/** Every route the product permits a search engine to index, in the order a crawler meets them. */
export const INDEXABLE_PATHS = ['/', '/legal'] as const

export type IndexablePath = (typeof INDEXABLE_PATHS)[number]

/**
 * Whether a path may declare itself indexable.
 *
 * Read by the public pages, so the list above is the only place the answer is written down. A page
 * that is not on it inherits `noindex, nofollow` from the root layout and cannot opt back in.
 */
export const isIndexable = (path: string): boolean =>
  INDEXABLE_PATHS.some((indexable): boolean => indexable === path)

/**
 * Paths a crawler needs in order to render a public page. A crawler blocked from a page's
 * stylesheet cannot assess how that page renders, and these are the pages meant to be assessed.
 */
const CRAWLABLE_ASSET_PATHS = ['/_next/static/', '/icon.png', '/apple-icon.png', '/favicon.ico']

export type RobotsRules = {
  rules: {
    userAgent: '*'
    /** Present only in Production, where the public pages are the exceptions. */
    allow?: string[]
    disallow: '/'
  }
  sitemap?: string
}

/**
 * `Allow: /$` alongside `Disallow: /` permits the front door and nothing below it; `/legal` is
 * allowed unanchored, so the document pages beneath it are crawlable too.
 *
 * The `$` anchor is an extension to the original exclusion standard rather than part of it,
 * honoured by Google and Bing but not guaranteed elsewhere. That is why the root layout also
 * declares `noindex` for every route by default and each public page opts itself back in: two
 * independent mechanisms, and a crawler that honours neither still finds nothing under `/account`,
 * because there is no session in which to render it.
 */
export const robotsRules = (config: SiteConfig): RobotsRules => {
  if (!config.isProduction) {
    return { rules: { userAgent: '*', disallow: '/' } }
  }

  return {
    rules: {
      userAgent: '*',
      allow: ['/$', '/legal', ...CRAWLABLE_ASSET_PATHS],
      disallow: '/',
    },
    sitemap: `${config.siteUrl}/sitemap.xml`,
  }
}

export type SitemapEntry = {
  url: string
  changeFrequency: 'monthly'
}

/** An absolute URL for a path, without the doubled slash a naive join gives `/`. */
const absolute = (siteUrl: string, path: string): string =>
  path === '/' ? siteUrl : `${siteUrl}${path}`

/** The public routes in Production, none anywhere else. */
export const siteSitemap = (config: SiteConfig): SitemapEntry[] =>
  config.isProduction
    ? INDEXABLE_PATHS.map((path) => ({
        url: absolute(config.siteUrl, path),
        changeFrequency: 'monthly' as const,
      }))
    : []

/**
 * Response headers suppressing indexing outside Production.
 *
 * Sent as a header rather than as page metadata because `export const metadata` is evaluated when
 * a static route is built: a build artefact promoted from QA to Production would otherwise carry
 * whichever environment's value was present at build time. Where a page-level `index` directive
 * and a `noindex` header disagree, crawlers take the more restrictive.
 */
export const indexingHeaders = (config: SiteConfig): Record<string, string> =>
  config.isProduction ? {} : { 'X-Robots-Tag': 'noindex, nofollow' }

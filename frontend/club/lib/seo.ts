/**
 * What search engines are told, in one place.
 *
 * See design/features/public-landing-and-auth-routing.md section 6.3. The landing page is the
 * only route the product ever permits to be indexed, and no environment other than Production
 * permits any indexing at all.
 */

import type { SiteConfig } from './site'

/** The one route the product permits a search engine to index. */
export const INDEXABLE_PATH = '/'

/**
 * Paths a crawler needs in order to render the landing page. A crawler blocked from a page's
 * stylesheet cannot assess how that page renders, and the landing page is the one page meant
 * to be assessed.
 */
const CRAWLABLE_ASSET_PATHS = ['/_next/static/', '/icon.png', '/apple-icon.png', '/favicon.ico']

export type RobotsRules = {
  rules: {
    userAgent: '*'
    /** Present only in Production, where the landing page is the single exception. */
    allow?: string[]
    disallow: '/'
  }
  sitemap?: string
}

/**
 * `Allow: /$` alongside `Disallow: /` permits the home page and nothing below it. The `$`
 * anchor is an extension to the original exclusion standard rather than part of it, honoured
 * by Google and Bing but not guaranteed elsewhere, which is why the root layout also declares
 * `noindex` for every route by default.
 */
export const robotsRules = (config: SiteConfig): RobotsRules => {
  if (!config.isProduction) {
    return { rules: { userAgent: '*', disallow: '/' } }
  }

  return {
    rules: {
      userAgent: '*',
      allow: [`${INDEXABLE_PATH}$`, ...CRAWLABLE_ASSET_PATHS],
      disallow: '/',
    },
    sitemap: `${config.siteUrl}/sitemap.xml`,
  }
}

export type SitemapEntry = {
  url: string
  changeFrequency: 'monthly'
}

/** One entry in Production, none anywhere else. */
export const siteSitemap = (config: SiteConfig): SitemapEntry[] =>
  config.isProduction ? [{ url: config.siteUrl, changeFrequency: 'monthly' }] : []

/**
 * Response headers suppressing indexing outside Production.
 *
 * Sent as a header rather than as page metadata because `export const metadata` is evaluated
 * when a static route is built: a build artefact promoted from QA to Production would
 * otherwise carry whichever environment's value was present at build time. Where a page-level
 * `index` directive and a `noindex` header disagree, crawlers take the more restrictive.
 */
export const indexingHeaders = (config: SiteConfig): Record<string, string> =>
  config.isProduction ? {} : { 'X-Robots-Tag': 'noindex, nofollow' }

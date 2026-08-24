import { describe, expect, test } from 'vitest'
import { INDEXABLE_PATH, indexingHeaders, robotsRules, siteSitemap } from './seo'
import type { AppEnv } from './env'
import type { SiteConfig } from './site'

/*
 * design/features/public-landing-and-auth-routing.md criteria 10 to 15.
 *
 * Every function here is a pure function of the site configuration, so each environment is
 * covered by passing a synthetic config rather than by reloading modules.
 */

const configFor = (appEnv: AppEnv): SiteConfig => ({
  appEnv,
  siteUrl: 'https://example.co.za',
  cdnBaseUrl: 'https://static.example.invalid/collective',
  isProduction: appEnv === 'production',
})

const production = configFor('production')
const nonProduction: SiteConfig[] = [configFor('local'), configFor('qa')]

describe('robotsRules in production', () => {
  const { rules, sitemap } = robotsRules(production)

  test('disallows the whole site, so nothing is crawlable by default', () => {
    expect(rules.disallow).toBe('/')
  })

  test('allows the site root as an anchored exception', () => {
    expect(rules.allow).toContain(`${INDEXABLE_PATH}$`)
  })

  test('allows the stylesheet and icon paths, so the one indexable page can be rendered', () => {
    expect(rules.allow).toEqual(
      expect.arrayContaining(['/_next/static/', '/icon.png', '/apple-icon.png', '/favicon.ico']),
    )
  })

  test('applies to every user agent', () => {
    expect(rules.userAgent).toBe('*')
  })

  test('names the sitemap as an absolute URL on the configured host', () => {
    expect(sitemap).toBe('https://example.co.za/sitemap.xml')
  })
})

describe.each(nonProduction)('robotsRules outside production ($appEnv)', (config) => {
  const { rules, sitemap } = robotsRules(config)

  test('disallows the whole site with no exception', () => {
    expect(rules.disallow).toBe('/')
    expect(rules.allow).toBeUndefined()
  })

  test('names no sitemap', () => {
    expect(sitemap).toBeUndefined()
  })
})

describe('siteSitemap', () => {
  test('lists exactly the landing page in production, as an absolute URL', () => {
    const entries = siteSitemap(production)

    expect(entries).toHaveLength(1)
    expect(entries[0]?.url).toBe('https://example.co.za')
  })

  test.each(nonProduction)('lists nothing outside production ($appEnv)', (config) => {
    expect(siteSitemap(config)).toEqual([])
  })
})

describe('indexingHeaders', () => {
  test('sets nothing in production, so the page-level directives stand', () => {
    expect(indexingHeaders(production)).toEqual({})
  })

  test.each(nonProduction)('suppresses indexing everywhere outside production ($appEnv)', (config) => {
    expect(indexingHeaders(config)).toEqual({ 'X-Robots-Tag': 'noindex, nofollow' })
  })
})

import { describe, expect, test } from 'vitest'
import {
  INDEXABLE_PATHS,
  indexingHeaders,
  isIndexable,
  robotsRules,
  siteSitemap,
} from './seo'
import type { SiteConfig } from './site'

const config = (appEnv: SiteConfig['appEnv']): SiteConfig => ({
  appEnv,
  siteUrl: 'https://store.example.co.za',
  isProduction: appEnv === 'production',
})

describe('the indexable set', () => {
  test('is the front door and the legal pages, and nothing else', () => {
    // Larger than the club's one route, because a store's public pages are meant to be found.
    expect(INDEXABLE_PATHS).toEqual(['/', '/legal'])
  })

  test('never includes the account area or sign-in', () => {
    expect(isIndexable('/account')).toBe(false)
    expect(isIndexable('/account/details')).toBe(false)
    expect(isIndexable('/sign-in')).toBe(false)
    expect(isIndexable('/sign-up')).toBe(false)
  })

  test('is exact rather than prefixed, so a route below one is not admitted by accident', () => {
    expect(isIndexable('/')).toBe(true)
    expect(isIndexable('/legal')).toBe(true)
    expect(isIndexable('/legalese')).toBe(false)
  })
})

describe('robotsRules', () => {
  test('permits nothing at all outside production', () => {
    for (const appEnv of ['local', 'qa'] as const) {
      const rules = robotsRules(config(appEnv))

      expect(rules.rules.disallow).toBe('/')
      expect(rules.rules.allow).toBeUndefined()
      expect(rules.sitemap).toBeUndefined()
    }
  })

  test('permits the public pages in production, and points at the sitemap', () => {
    const rules = robotsRules(config('production'))

    expect(rules.rules.disallow).toBe('/')
    expect(rules.rules.allow).toContain('/$')
    expect(rules.rules.allow).toContain('/legal')
    expect(rules.sitemap).toBe('https://store.example.co.za/sitemap.xml')
  })

  test('anchors the front door but not the legal prefix', () => {
    // `/$` is the home page and nothing under it. `/legal` is unanchored, because the documents
    // beneath it are crawlable too.
    const allow = robotsRules(config('production')).rules.allow ?? []

    expect(allow).not.toContain('/legal$')
  })

  test('lets a crawler fetch what a public page needs in order to render', () => {
    const allow = robotsRules(config('production')).rules.allow ?? []

    expect(allow).toContain('/_next/static/')
  })
})

describe('siteSitemap', () => {
  test('is empty everywhere but production', () => {
    expect(siteSitemap(config('local'))).toEqual([])
    expect(siteSitemap(config('qa'))).toEqual([])
  })

  test('lists the public routes as absolute URLs, with no doubled slash on the root', () => {
    expect(siteSitemap(config('production'))).toEqual([
      { url: 'https://store.example.co.za', changeFrequency: 'monthly' },
      { url: 'https://store.example.co.za/legal', changeFrequency: 'monthly' },
    ])
  })
})

describe('indexingHeaders', () => {
  test('suppresses indexing outside production', () => {
    expect(indexingHeaders(config('qa'))).toEqual({ 'X-Robots-Tag': 'noindex, nofollow' })
  })

  test('sends nothing in production, where page metadata decides', () => {
    expect(indexingHeaders(config('production'))).toEqual({})
  })
})

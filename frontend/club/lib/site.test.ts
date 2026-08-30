import { describe, expect, test } from 'vitest'
import type { AppEnv } from './env'
import { readSiteConfig } from './site'

/*
 * design/features/public-landing-and-auth-routing.md criteria 16 and 17, and
 * design/features/club-document-agreements-at-sign-up.md criteria 15 to 17.
 *
 * The reader is pure and takes the environment as an argument, so these tests never mutate
 * process.env and never need a module reset between cases.
 */

const validEnv = {
  APP_ENV: 'production',
  SITE_URL: 'https://example.co.za',
  CDN_BASE_URL: 'https://static.example.invalid/collective',
}

describe('readSiteConfig', () => {
  const environments: AppEnv[] = ['local', 'qa', 'production']

  test.each(environments)('accepts APP_ENV=%s', (appEnv) => {
    const config = readSiteConfig({ ...validEnv, APP_ENV: appEnv })

    expect(config.appEnv).toBe(appEnv)
  })

  test('reports production only for the production environment', () => {
    expect(readSiteConfig({ ...validEnv, APP_ENV: 'production' }).isProduction).toBe(true)
    expect(readSiteConfig({ ...validEnv, APP_ENV: 'qa' }).isProduction).toBe(false)
    expect(readSiteConfig({ ...validEnv, APP_ENV: 'local' }).isProduction).toBe(false)
  })

  test('keeps the configured site URL', () => {
    const config = readSiteConfig({ ...validEnv, SITE_URL: 'https://club.example.co.za' })

    expect(config.siteUrl).toBe('https://club.example.co.za')
  })

  test('strips a trailing slash from the site URL, so joined paths never double up', () => {
    const config = readSiteConfig({ ...validEnv, SITE_URL: 'https://example.co.za/' })

    expect(config.siteUrl).toBe('https://example.co.za')
  })

  test('accepts a localhost origin, for local development', () => {
    const config = readSiteConfig({ ...validEnv, SITE_URL: 'http://localhost:3000' })

    expect(config.siteUrl).toBe('http://localhost:3000')
  })
})

describe('readSiteConfig rejects a misconfigured environment', () => {
  test('throws naming APP_ENV when it is absent', () => {
    expect(() => readSiteConfig({ SITE_URL: validEnv.SITE_URL })).toThrow(/APP_ENV/)
  })

  test('throws naming APP_ENV when it is not a known environment', () => {
    expect(() => readSiteConfig({ ...validEnv, APP_ENV: 'staging' })).toThrow(/APP_ENV/)
  })

  test('throws naming APP_ENV when it is empty', () => {
    expect(() => readSiteConfig({ ...validEnv, APP_ENV: '' })).toThrow(/APP_ENV/)
  })

  test('throws naming SITE_URL when it is absent', () => {
    expect(() => readSiteConfig({ APP_ENV: validEnv.APP_ENV })).toThrow(/SITE_URL/)
  })

  test('throws naming SITE_URL when it is not an absolute URL', () => {
    expect(() => readSiteConfig({ ...validEnv, SITE_URL: 'example.co.za' })).toThrow(/SITE_URL/)
  })

  test('throws naming SITE_URL when it carries a path', () => {
    expect(() => readSiteConfig({ ...validEnv, SITE_URL: 'https://example.co.za/club' })).toThrow(
      /SITE_URL/,
    )
  })

  test('throws naming SITE_URL when the scheme is not http or https', () => {
    expect(() => readSiteConfig({ ...validEnv, SITE_URL: 'ftp://example.co.za' })).toThrow(
      /SITE_URL/,
    )
  })
})

describe('the CDN base URL', () => {
  test('is kept as configured', () => {
    // Criterion 20: everything the club serves statically hangs off this one value.
    const config = readSiteConfig({ ...validEnv, CDN_BASE_URL: 'https://cdn.example.invalid/club' })

    expect(config.cdnBaseUrl).toBe('https://cdn.example.invalid/club')
  })

  test('keeps its path, unlike the site URL, because it is a prefix on a shared host', () => {
    const config = readSiteConfig({
      ...validEnv,
      CDN_BASE_URL: 'https://cdn.example.invalid/one/two',
    })

    expect(config.cdnBaseUrl).toBe('https://cdn.example.invalid/one/two')
  })

  test('loses a trailing slash, so a joined path never doubles up', () => {
    // Criterion 18.
    const config = readSiteConfig({ ...validEnv, CDN_BASE_URL: 'https://cdn.example.invalid/club/' })

    expect(config.cdnBaseUrl).toBe('https://cdn.example.invalid/club')
  })

  test('may be served over plain http locally, where there is no CDN to speak of', () => {
    const config = readSiteConfig({
      ...validEnv,
      APP_ENV: 'local',
      CDN_BASE_URL: 'http://localhost:4000/static',
    })

    expect(config.cdnBaseUrl).toBe('http://localhost:4000/static')
  })
})

describe('readSiteConfig rejects a misconfigured CDN base URL', () => {
  test('throws naming CDN_BASE_URL when it is absent', () => {
    // Criterion 15.
    expect(() =>
      readSiteConfig({ APP_ENV: validEnv.APP_ENV, SITE_URL: validEnv.SITE_URL }),
    ).toThrow(/CDN_BASE_URL/)
  })

  test('throws naming CDN_BASE_URL when it is empty', () => {
    expect(() => readSiteConfig({ ...validEnv, CDN_BASE_URL: '' })).toThrow(/CDN_BASE_URL/)
  })

  test('throws naming CDN_BASE_URL when it is not an absolute URL', () => {
    // Criterion 16.
    expect(() => readSiteConfig({ ...validEnv, CDN_BASE_URL: '/collective' })).toThrow(
      /CDN_BASE_URL/,
    )
  })

  test('throws naming CDN_BASE_URL when the scheme is not http or https', () => {
    expect(() => readSiteConfig({ ...validEnv, CDN_BASE_URL: 'ftp://cdn.example.invalid' })).toThrow(
      /CDN_BASE_URL/,
    )
  })

  test.each(['https://cdn.example.invalid/club?v=2', 'https://cdn.example.invalid/club#top'])(
    'throws naming CDN_BASE_URL for %o, which carries more than a prefix',
    (value) => {
      // Criterion 16.
      expect(() => readSiteConfig({ ...validEnv, CDN_BASE_URL: value })).toThrow(/CDN_BASE_URL/)
    },
  )

  test.each(['qa', 'production'])(
    'throws for a plain http base in the %s environment',
    (appEnv) => {
      /*
       * Criterion 17. A document fetched over plain http is a document anything on the path can
       * rewrite, and these documents are what a member is agreeing to.
       */
      expect(() =>
        readSiteConfig({ ...validEnv, APP_ENV: appEnv, CDN_BASE_URL: 'http://cdn.example.invalid' }),
      ).toThrow(/CDN_BASE_URL/)
    },
  )
})

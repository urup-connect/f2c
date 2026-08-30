import { describe, expect, test } from 'vitest'
import { readSiteConfig } from './site'

/*
 * The store reads two variables where the club reads three. The last test in this file is the one
 * that matters: a CDN_BASE_URL required here would be a deployment setting nobody could give a
 * correct value to.
 */

const local = { APP_ENV: 'local', SITE_URL: 'http://localhost:3001' }

describe('readSiteConfig', () => {
  test('reads a local deployment', () => {
    const config = readSiteConfig(local)

    expect(config.appEnv).toBe('local')
    expect(config.siteUrl).toBe('http://localhost:3001')
    expect(config.isProduction).toBe(false)
  })

  test('only production is production', () => {
    expect(readSiteConfig({ ...local, APP_ENV: 'qa' }).isProduction).toBe(false)
    expect(
      readSiteConfig({ APP_ENV: 'production', SITE_URL: 'https://store.example.co.za' })
        .isProduction,
    ).toBe(true)
  })

  test('refuses an APP_ENV that is not one of the three', () => {
    expect(() => readSiteConfig({ ...local, APP_ENV: 'staging' })).toThrow(/APP_ENV/)
  })

  test('refuses a missing SITE_URL, naming it', () => {
    expect(() => readSiteConfig({ APP_ENV: 'local' })).toThrow(/SITE_URL is not set/)
  })

  test('refuses a SITE_URL that is not an absolute URL', () => {
    expect(() => readSiteConfig({ ...local, SITE_URL: 'localhost:3001' })).toThrow(/SITE_URL/)
  })

  test('refuses a scheme that is not http or https', () => {
    expect(() => readSiteConfig({ ...local, SITE_URL: 'ftp://example.co.za' })).toThrow(/SITE_URL/)
  })

  test('refuses more than an origin, because callers append their own path', () => {
    expect(() => readSiteConfig({ ...local, SITE_URL: 'https://example.co.za/store' })).toThrow(
      /more than an origin/,
    )
  })

  test('drops a trailing slash, so a caller can append a path', () => {
    expect(readSiteConfig({ ...local, SITE_URL: 'https://example.co.za/' }).siteUrl).toBe(
      'https://example.co.za',
    )
  })

  test('does not ask for a CDN_BASE_URL, which the club needs and the store does not', () => {
    // Nothing in the store is served from the static host: a document's address comes from Django,
    // because Django owns its revisions.
    expect(() => readSiteConfig(local)).not.toThrow()
  })
})

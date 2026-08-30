import { describe, expect, test } from 'vitest'
import { BRAND_FILM, brandFilmPoster, brandFilmSource } from './brand-film'
import type { SiteConfig } from './site'

/* design/features/landing.md section 3. */

const configWith = (cdnBaseUrl: string): SiteConfig => ({
  appEnv: 'qa',
  siteUrl: 'https://example.invalid',
  cdnBaseUrl,
  isProduction: false,
})

describe('the brand film manifest', () => {
  test('names a path beneath the CDN base rather than an absolute address', () => {
    // An absolute address here would defeat the point of CDN_BASE_URL: QA would serve
    // Production's file.
    expect(BRAND_FILM.path.startsWith('/')).toBe(true)
    expect(BRAND_FILM.path).not.toMatch(/^https?:/)
  })

  test('declares the file dimensions, so the page can reserve the box before it loads', () => {
    expect(BRAND_FILM.width).toBe(1920)
    expect(BRAND_FILM.height).toBe(1080)
  })

  test('names the poster separately rather than deriving it from the film path', () => {
    // Deriving it would turn a renamed asset on a host we do not control into a broken image.
    expect(BRAND_FILM.posterPath.startsWith('/')).toBe(true)
    expect(BRAND_FILM.posterPath).not.toBe(BRAND_FILM.path)
  })

  test('carries a poster shaped like the film, so the box letterboxes rather than crops', () => {
    const filmRatio = BRAND_FILM.width / BRAND_FILM.height
    const posterRatio = BRAND_FILM.posterWidth / BRAND_FILM.posterHeight

    expect(Math.abs(filmRatio - posterRatio)).toBeLessThan(0.01)
  })
})

describe('brandFilmSource', () => {
  test('appends the path to the deployment CDN base', () => {
    const source = brandFilmSource(configWith('https://static.example.invalid/collective'))

    expect(source).toBe(
      `https://static.example.invalid/collective${BRAND_FILM.path}`,
    )
  })

  test('produces one slash at the join, the base carrying none of its own', () => {
    // readSiteConfig strips a trailing slash, which is what this relies on.
    expect(brandFilmSource(configWith('http://localhost:3000/static'))).not.toMatch(/[^:]\/\//)
  })
})

describe('brandFilmPoster', () => {
  test('appends the poster path to the same deployment CDN base', () => {
    const config = configWith('https://static.example.invalid/collective')

    expect(brandFilmPoster(config)).toBe(
      `https://static.example.invalid/collective${BRAND_FILM.posterPath}`,
    )
  })

  test('serves the poster from the same host as the film', () => {
    const config = configWith('https://static.example.invalid/collective')

    expect(new URL(brandFilmPoster(config)).origin).toBe(new URL(brandFilmSource(config)).origin)
  })
})

import { describe, expect, test } from 'vitest'
import { readPublicApiBaseUrl } from './api-address'

/*
 * design/todo.md Block 0 P6, and design/conflict.md C31.
 *
 * The reader is pure and takes the environment as an argument, so these never mutate process.env
 * and never need a module reset between cases — the convention `site.test.ts` set.
 *
 * The case that matters most is `refuses a missing address`. The old code had
 * `?? 'http://localhost:8000'` in its place, which meant a deployment that forgot the variable
 * served pages that looked entirely correct and sent every browser request to the member's own
 * machine. A refusal is the only version of this that cannot ship.
 */

describe('readPublicApiBaseUrl', () => {
  test('accepts an absolute https address', () => {
    expect(readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: 'https://backend.example.co.za' })).toBe(
      'https://backend.example.co.za',
    )
  })

  test('accepts plain http, for local development', () => {
    expect(readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: 'http://localhost:8000' })).toBe(
      'http://localhost:8000',
    )
  })

  test('strips a trailing slash', () => {
    // `lib/api.ts` appends paths that already start with one, and Django resolves `//api/...`
    // as a different path.
    expect(readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: 'https://backend.example.co.za/' })).toBe(
      'https://backend.example.co.za',
    )
  })

  test('strips repeated trailing slashes', () => {
    expect(readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: 'https://backend.example.co.za///' })).toBe(
      'https://backend.example.co.za',
    )
  })

  test('refuses a missing address', () => {
    expect(() => readPublicApiBaseUrl({})).toThrow(/DJANGO_API_PUBLIC_URL is not set/)
  })

  test('refuses a blank address', () => {
    // A deployment template that renders an empty string has not set it.
    expect(() => readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: '   ' })).toThrow(
      /DJANGO_API_PUBLIC_URL is not set/,
    )
  })

  test('refuses a relative address', () => {
    expect(() => readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: '/api' })).toThrow(
      /not an absolute URL/,
    )
  })

  test('refuses a scheme that is not http or https', () => {
    expect(() => readPublicApiBaseUrl({ DJANGO_API_PUBLIC_URL: 'ftp://backend.example.co.za' })).toThrow(
      /not http or https/,
    )
  })

  test('names the variable and where to set it', () => {
    // Somebody reading a container log has to be able to act on this without the source.
    expect(() => readPublicApiBaseUrl({})).toThrow(/container environment/)
  })
})

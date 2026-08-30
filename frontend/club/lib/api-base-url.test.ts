import { afterEach, beforeEach, describe, expect, test } from 'vitest'
import { API_BASE_META_NAME, apiBaseUrl, resetApiBaseUrlCache } from './api'

/*
 * The browser half of design/todo.md Block 0 P6.
 *
 * `readPublicApiBaseUrl` in `api-address.test.ts` covers the server producing the value; this
 * covers the browser finding it. The two halves are tested apart because only this one needs a
 * document, and jsdom gives one.
 */

const writeTag = (content: string) => {
  const meta = document.createElement('meta')
  meta.setAttribute('name', API_BASE_META_NAME)
  meta.setAttribute('content', content)
  document.head.appendChild(meta)
}

// `vitest.setup.ts` writes the tag before every test, standing in for the root layout. These
// cases decide for themselves whether it is there, so they start from a clean document.
beforeEach(() => {
  document.head.querySelectorAll(`meta[name="${API_BASE_META_NAME}"]`).forEach((tag) => tag.remove())
  resetApiBaseUrlCache()
})

afterEach(() => {
  document.head.querySelectorAll(`meta[name="${API_BASE_META_NAME}"]`).forEach((tag) => tag.remove())
  resetApiBaseUrlCache()
})

describe('apiBaseUrl in the browser', () => {
  test('reads the address the server wrote into the document', () => {
    writeTag('https://backend.example.co.za')

    expect(apiBaseUrl()).toBe('https://backend.example.co.za')
  })

  test('a promoted build reads whatever the container was told', () => {
    // The point of the whole exercise: the same bundle, a different address, no rebuild.
    writeTag('https://backend.qa.example.co.za')
    expect(apiBaseUrl()).toBe('https://backend.qa.example.co.za')

    resetApiBaseUrlCache()
    document.head.querySelectorAll(`meta[name="${API_BASE_META_NAME}"]`).forEach((t) => t.remove())
    writeTag('https://backend.example.co.za')
    expect(apiBaseUrl()).toBe('https://backend.example.co.za')
  })

  test('trims surrounding whitespace', () => {
    writeTag('  https://backend.example.co.za  ')

    expect(apiBaseUrl()).toBe('https://backend.example.co.za')
  })

  test('throws when the tag is missing rather than defaulting to localhost', () => {
    // The old code defaulted here, which sent every deployed browser request to the member's own
    // machine while every page looked correct.
    expect(() => apiBaseUrl()).toThrow(/tag is missing/)
  })

  test('throws when the tag is present but empty', () => {
    writeTag('   ')

    expect(() => apiBaseUrl()).toThrow(/tag is missing/)
  })

  test('the failure names where the value comes from', () => {
    expect(() => apiBaseUrl()).toThrow(/DJANGO_API_PUBLIC_URL/)
  })
})

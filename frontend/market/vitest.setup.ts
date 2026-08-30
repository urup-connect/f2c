import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { API_BASE_META_NAME, resetApiBaseUrlCache } from './lib/api'
import { afterEach, beforeEach } from 'vitest'

afterEach(() => {
  cleanup()
})

/*
 * The API address, as the root layout would have rendered it.
 *
 * jsdom defines `window`, so `apiBaseUrl()` takes its browser branch even in tests of server-side
 * code — the route handler, and any component rendered without a layout above it. In a real
 * document the tag is always there because `app/layout.tsx` renders it; here nothing renders a
 * layout, so it is put in place instead. `localhost:8000` is what both halves of the old
 * `process.env` pair defaulted to, so no test's expectations move.
 *
 * Re-applied per test rather than once, because `resetApiBaseUrlCache` has to run between cases —
 * the reader memoises, and a test that changes the address would otherwise see the previous one.
 */
beforeEach(() => {
  if (typeof document === 'undefined') return

  resetApiBaseUrlCache()
  document.head
    .querySelectorAll(`meta[name="${API_BASE_META_NAME}"]`)
    .forEach((tag) => tag.remove())

  const meta = document.createElement('meta')
  meta.setAttribute('name', API_BASE_META_NAME)
  meta.setAttribute('content', 'http://localhost:8000')
  document.head.appendChild(meta)
})

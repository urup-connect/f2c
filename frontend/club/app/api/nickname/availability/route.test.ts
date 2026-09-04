import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { POST } from './route'

/*
 * design/features/sign-up.md section 7.
 *
 * This is the seam where a fault stops being describable to the browser and starts being a log
 * line. Most of what follows is about what the answer does *not* carry: Django's status code, its
 * `detail`, an exception, or the nickname that was asked about.
 */

const ask = (body: unknown) =>
  POST(
    new Request('http://localhost:3000/api/nickname/availability', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: typeof body === 'string' ? body : JSON.stringify(body),
    }),
  )

const django = (status: number, body: unknown) =>
  vi.fn(async () => ({ status, ok: status >= 200 && status < 300, json: async () => body }) as Response)

let logged: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  // The cause is written here rather than answered, so every failure test reads it from the log.
  logged = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const lines = () => logged.mock.calls.map((call: unknown[]) => String(call[0])).join('\n')

describe('an answer from Django', () => {
  test('a free nickname comes back as available', async () => {
    vi.stubGlobal('fetch', django(200, { available: true }))

    const response = await ask({ nickname: 'GreenThumb' })

    expect(response.status).toBe(200)
    expect(await response.json()).toEqual({ available: true })
  })

  test('a taken nickname comes back as unavailable', async () => {
    vi.stubGlobal('fetch', django(200, { available: false }))

    expect(await (await ask({ nickname: 'GreenThumb' })).json()).toEqual({ available: false })
  })

  test('is re-written rather than passed through', async () => {
    /*
     * A field added to Django's response later must not reach a browser through here without
     * somebody deciding it should.
     */
    vi.stubGlobal('fetch', django(200, { available: true, held_by: 'thandiwe@example.com' }))

    expect(await (await ask({ nickname: 'GreenThumb' })).json()).toEqual({ available: true })
  })

  test('is never cached', async () => {
    vi.stubGlobal('fetch', django(200, { available: true }))

    expect((await ask({ nickname: 'GreenThumb' })).headers.get('Cache-Control')).toBe('no-store')
  })
})

describe('what is sent to Django', () => {
  test('is the nickname, in the body of a POST', async () => {
    const fetcher = django(200, { available: true })
    vi.stubGlobal('fetch', fetcher)

    await ask({ nickname: 'GreenThumb' })

    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit]

    expect(url).toContain('/api/members/nickname/availability')
    // Never a query string: that is this application's access log, and the browser's history.
    expect(url).not.toContain('GreenThumb')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ nickname: 'GreenThumb' })
    expect(init.cache).toBe('no-store')
  })
})

describe('a failure', () => {
  const failures: readonly (readonly [string, () => void])[] = [
    ['the API is unreachable', () => vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('ECONNREFUSED')
    }))],
    ['the API answered 500', () => vi.stubGlobal('fetch', django(500, { detail: 'boom' }))],
    ['the API answered 503', () => vi.stubGlobal('fetch', django(503, { detail: 'no documents' }))],
    ['the API answered 429', () => vi.stubGlobal('fetch', django(429, { detail: 'too many' }))],
    ['the API refused the nickname', () => vi.stubGlobal('fetch', django(422, { detail: 'bad' }))],
    ['the API answered 200 with nothing usable', () => vi.stubGlobal('fetch', django(200, {}))],
  ]

  test('is a 502 carrying a reference and nothing else', async () => {
    for (const [name, arrange] of failures) {
      arrange()

      const response = await ask({ nickname: 'GreenThumb' })
      const body = await response.json()

      expect(response.status, name).toBe(502)
      expect(Object.keys(body), name).toEqual(['reference'])
      expect(body.reference, name).toMatch(/^[0-9a-f]{8}$/)
    }
  })

  /*
   * The whole answer, with the reference blanked out wherever it appears.
   *
   * The reference is eight random hex characters and `500`, `503`, `429`, `422` and `bad` are all
   * valid hex, so scanning the answer as it stands failed about one run in twenty-three — on a
   * reference that happened to spell one of the strings below (deploy.md 5.4). Blanked rather than
   * excused: whatever it spells it cannot be a leak, because it is minted on the way out of
   * `crypto.getRandomValues` and derived from nothing about the request or Django's reply. Its own
   * shape is asserted here, and every other byte of the answer still goes to the scan.
   */
  const scannable = async (body: unknown) => {
    const answer = await (await ask(body)).json()

    expect(answer.reference).toMatch(/^[0-9a-f]{8}$/)

    return JSON.stringify(answer).split(answer.reference).join('<reference>')
  }

  test('never tells the browser what went wrong', async () => {
    for (const [name, arrange] of failures) {
      arrange()

      const answer = await scannable({ nickname: 'GreenThumb' })

      for (const leak of ['boom', 'no documents', 'too many', 'bad', '500', '503', '429', '422']) {
        expect(answer, `${name} leaked ${leak}`).not.toContain(leak)
      }
    }
  })

  test('is logged against the reference the browser was given', async () => {
    vi.stubGlobal('fetch', django(500, { detail: 'boom' }))

    const { reference } = await (await ask({ nickname: 'GreenThumb' })).json()

    // An opaque reference with nothing behind it is worse than no reference at all.
    expect(lines()).toContain(reference)
    expect(lines()).toContain('500')
  })

  test('says in the log when Django and the browser rules disagree', async () => {
    /*
     * A 422 means the browser accepted a nickname Django would not. Nothing is wrong with the
     * member; the two implementations have drifted, and this line is the only warning anyone gets.
     */
    vi.stubGlobal('fetch', django(422, { detail: 'bad' }))

    await ask({ nickname: 'GreenThumb' })

    expect(lines()).toMatch(/malformed/i)
  })

  test('never logs the nickname', async () => {
    for (const [name, arrange] of failures) {
      logged.mockClear()
      arrange()

      await ask({ nickname: 'GreenThumb' })

      expect(lines(), name).not.toContain('GreenThumb')
    }
  })

  test('covers a request that carries no nickname', async () => {
    vi.stubGlobal('fetch', django(200, { available: true }))

    for (const body of ['not json', {}, { nickname: 42 }, { nickname: null }]) {
      const response = await ask(body)

      expect(response.status).toBe(502)
      expect((await response.json()).reference).toMatch(/^[0-9a-f]{8}$/)
    }

    // Nothing was asked of Django, because there was nothing to ask.
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  test('gives every failure its own reference', async () => {
    vi.stubGlobal('fetch', django(500, {}))

    const first = await (await ask({ nickname: 'GreenThumb' })).json()
    const second = await (await ask({ nickname: 'GreenThumb' })).json()

    expect(first.reference).not.toBe(second.reference)
  })
})

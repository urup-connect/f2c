import { afterEach, describe, expect, test, vi } from 'vitest'
import {
  NICKNAME_AVAILABILITY_PATH,
  readNicknameAvailability,
  requestNicknameAvailability,
} from './nickname-availability'

/*
 * design/features/sign-up.md section 7.
 *
 * The mapping is tested apart from the request for the reason `lib/registration.ts` is: an answer
 * this module stops recognising becomes a member being told something nobody established.
 */

const answered = (status: number, body: unknown) =>
  ({ status, json: async () => body }) as Response

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('reading the answer', () => {
  test('a free nickname is available', () => {
    expect(readNicknameAvailability(200, { available: true })).toEqual({ status: 'available' })
  })

  test('a nickname somebody holds is taken', () => {
    expect(readNicknameAvailability(200, { available: false })).toEqual({ status: 'taken' })
  })

  test('a failure carries the reference it was logged against', () => {
    expect(readNicknameAvailability(502, { reference: '3f9a1c04' })).toEqual({
      status: 'unusable',
      reference: '3f9a1c04',
    })
  })

  test('a reference that is not ours is dropped rather than shown', () => {
    // Rendered beside our own wording, so it is read as strictly here as anywhere else.
    expect(readNicknameAvailability(502, { reference: 'call us on 0800' })).toEqual({
      status: 'unusable',
      reference: null,
    })
  })

  test('a 200 that does not say is unusable, not a refusal', () => {
    /*
     * The point of the test. Reading a missing field as "taken" sends a member off to invent a
     * second nickname because of a bug; reading it as "available" promises them one that may be
     * somebody else's.
     */
    for (const body of [{}, null, { available: 'yes' }, { available: 1 }, 'ok']) {
      expect(readNicknameAvailability(200, body)).toEqual({ status: 'unusable', reference: null })
    }
  })

  test('any other status is unusable', () => {
    for (const status of [400, 404, 429, 500, 503]) {
      expect(readNicknameAvailability(status, {}).status).toBe('unusable')
    }
  })
})

describe('asking', () => {
  test('asks this application, not Django', () => {
    /*
     * The route handler is what keeps the API's address out of the browser bundle and the cause of
     * a failure out of the browser's network log. A direct call would undo both.
     */
    expect(NICKNAME_AVAILABILITY_PATH).toBe('/api/nickname/availability')
  })

  test('sends the nickname in the body of a POST, never in the URL', async () => {
    const fetcher = vi.fn(async () => answered(200, { available: true }))
    vi.stubGlobal('fetch', fetcher)

    await requestNicknameAvailability('GreenThumb')

    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit]

    expect(url).toBe(NICKNAME_AVAILABILITY_PATH)
    expect(url).not.toContain('GreenThumb')
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ nickname: 'GreenThumb' })
  })

  test('never lets the answer be cached', async () => {
    const fetcher = vi.fn(async () => answered(200, { available: true }))
    vi.stubGlobal('fetch', fetcher)

    await requestNicknameAvailability('GreenThumb')

    const [, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit]

    // It is a statement about somebody else's record a moment ago. A cached one is a wrong one.
    expect(init.cache).toBe('no-store')
  })

  test('returns the answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => answered(200, { available: false })))

    expect(await requestNicknameAvailability('GreenThumb')).toEqual({ status: 'taken' })
  })

  test('does not throw when the browser cannot reach this site at all', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('offline')
    }))

    // No reference: there is no log line on our side to hand anybody.
    expect(await requestNicknameAvailability('GreenThumb')).toEqual({
      status: 'unusable',
      reference: null,
    })
  })

  test('does not throw when the answer is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      status: 200,
      json: async () => {
        throw new Error('not JSON')
      },
    }) as unknown as Response))

    expect((await requestNicknameAvailability('GreenThumb')).status).toBe('unusable')
  })
})

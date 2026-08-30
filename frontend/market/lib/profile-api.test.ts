import { describe, expect, test, vi } from 'vitest'
import { ApiError } from './api'
import { refusalMessagesByField, saveProfile } from './profile-api'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, apiFetch: vi.fn() }
})

const { apiFetch } = await import('./api')
const mockedFetch = vi.mocked(apiFetch)

const submission = { first_name: 'Thandiwe', last_name: 'Mokoena', mobile: '+27821234567' }

describe('refusalMessagesByField', () => {
  test("renders the API's own wording, keyed by this form's field names", () => {
    // Django refuses things the form does not check, so its sentence is shown rather than translated
    // into one of our reasons — a mapping would have to invent a reason for anything unrecognised.
    expect(
      refusalMessagesByField({
        detail: 'Your details were refused.',
        fields: { first_name: ['That does not look like a name.'] },
      }),
    ).toEqual({ firstName: 'That does not look like a name.' })
  })

  test('takes the first sentence per field, because a field has one place to say something', () => {
    expect(
      refusalMessagesByField({ detail: 'x', fields: { mobile: ['First.', 'Second.'] } }),
    ).toEqual({ mobile: 'First.' })
  })

  test('ignores a field this form has no input for', () => {
    expect(refusalMessagesByField({ detail: 'x', fields: { nickname: ['Taken.'] } })).toEqual({})
  })

  test('ignores a refusal with no fields at all', () => {
    expect(refusalMessagesByField({ detail: 'Refused.' })).toEqual({})
  })

  test('ignores an empty sentence rather than rendering a blank message', () => {
    expect(refusalMessagesByField({ detail: 'x', fields: { mobile: [''] } })).toEqual({})
  })
})

describe('saveProfile', () => {
  test('reports what was stored, which is the API\'s record rather than the submission', () => {
    const profile = { first_name: 'Thandiwe' }
    mockedFetch.mockResolvedValueOnce(profile)

    return expect(saveProfile(submission)).resolves.toEqual({ status: 'saved', profile })
  })

  test('reports a refusal the customer can act on, with its body', async () => {
    const body = { detail: 'Refused.', fields: { mobile: ['Already in use.'] } }
    mockedFetch.mockRejectedValueOnce(new ApiError(422, 'Refused.', body))

    await expect(saveProfile(submission)).resolves.toEqual({ status: 'refused', refusal: body })
  })

  test('reports a 409 as a refusal too', async () => {
    const body = { detail: 'That number is on another account.', mobile_unavailable: true }
    mockedFetch.mockRejectedValueOnce(new ApiError(409, body.detail, body))

    await expect(saveProfile(submission)).resolves.toEqual({ status: 'refused', refusal: body })
  })

  test('keeps a refusal status whose body it does not recognise, as a sentence', async () => {
    // The status still says the customer can act on it, so the message is reported rather than
    // swallowed into "try again".
    mockedFetch.mockRejectedValueOnce(new ApiError(422, 'Something specific.', 'not an object'))

    await expect(saveProfile(submission)).resolves.toEqual({
      status: 'refused',
      refusal: { detail: 'Something specific.' },
    })
  })

  test('reports anything else as a failure, and never throws', async () => {
    mockedFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))

    const outcome = await saveProfile(submission)

    expect(outcome.status).toBe('failed')
  })

  test('reports a rejection that is not an Error as a failure', async () => {
    mockedFetch.mockRejectedValueOnce('a string')

    await expect(saveProfile(submission)).resolves.toEqual({
      status: 'failed',
      reason: 'The store could not be reached.',
    })
  })
})

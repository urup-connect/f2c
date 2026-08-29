import { render, screen, waitFor } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { PasskeyCard } from './PasskeyCard'
import { ApiError, type Passkey } from '@/lib/api'
import { PASSKEYS_CARD } from '@/lib/club-content'
import { SIGN_IN_PROBLEMS } from '@/lib/sign-in-content'

const api = vi.hoisted(() => ({
  deletePasskey: vi.fn(),
  listPasskeys: vi.fn(),
  passkeyRegistrationOptions: vi.fn(),
  registerPasskey: vi.fn(),
}))

const webauthn = vi.hoisted(() => ({
  browserSupportsWebAuthn: vi.fn(),
  startRegistration: vi.fn(),
}))

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...actual, ...api }
})

vi.mock('@simplewebauthn/browser', () => webauthn)

const LAPTOP: Passkey = {
  id: 1,
  name: 'Work laptop',
  backed_up: false,
  device_type: 'single_device',
  created_at: '2026-03-15T08:00:00Z',
  last_used_at: '2026-08-01T19:30:00Z',
}

const PHONE: Passkey = { ...LAPTOP, id: 2, name: 'iPhone', last_used_at: null }

const removeButton = (name: string) =>
  screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: ${name}` })

beforeEach(() => {
  webauthn.browserSupportsWebAuthn.mockReturnValue(true)
  webauthn.startRegistration.mockResolvedValue({ id: 'credential' })
  api.passkeyRegistrationOptions.mockResolvedValue({ options: {} })
  api.registerPasskey.mockResolvedValue(PHONE)
  api.listPasskeys.mockResolvedValue([LAPTOP, PHONE])
  api.deletePasskey.mockResolvedValue({ detail: 'Passkey removed.' })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('the first paint', () => {
  test('shows the list the server already read', () => {
    // A member with passkeys must never see "no passkey yet" for a frame. That reads
    // as though the club lost them.
    render(<PasskeyCard initial={[LAPTOP]} />)

    expect(screen.getByText('Work laptop')).toBeInTheDocument()
    expect(api.listPasskeys).not.toHaveBeenCalled()
  })

  test('says there are none when there are none', () => {
    render(<PasskeyCard initial={[]} />)

    expect(screen.getByText(PASSKEYS_CARD.empty)).toBeInTheDocument()
  })

  test('says the list could not be read rather than saying zero', () => {
    render(<PasskeyCard initial={[]} unavailable />)

    expect(screen.getByRole('alert')).toHaveTextContent(PASSKEYS_CARD.loadFailed)
  })
})

describe('enrolling', () => {
  test('runs the ceremony and stores what came back', async () => {
    render(<PasskeyCard initial={[LAPTOP]} />)

    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    await waitFor(() => expect(api.registerPasskey).toHaveBeenCalledOnce())
    expect(webauthn.startRegistration).toHaveBeenCalledWith({ optionsJSON: {} })
  })

  test('sends the name the member typed', async () => {
    render(<PasskeyCard initial={[]} />)

    await userEvent.type(screen.getByLabelText(PASSKEYS_CARD.addLabel), 'Work laptop')
    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    await waitFor(() =>
      expect(api.registerPasskey).toHaveBeenCalledWith(expect.anything(), 'Work laptop'),
    )
  })

  test('suggests a name when the member typed none', async () => {
    render(<PasskeyCard initial={[]} />)

    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    await waitFor(() => expect(api.registerPasskey).toHaveBeenCalled())
    expect(api.registerPasskey.mock.calls[0][1]).toBeTruthy()
  })

  test('re-reads the list rather than appending what it believes it made', async () => {
    // Django names the credential, truncates the name and stamps the dates. Appending
    // would show a row that differs from what was stored.
    render(<PasskeyCard initial={[LAPTOP]} />)

    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    await waitFor(() => expect(api.listPasskeys).toHaveBeenCalledOnce())
    expect(await screen.findByText('iPhone')).toBeInTheDocument()
  })

  test('says the device refused when the authenticator refused', async () => {
    const cancelled = new Error('irrelevant')
    cancelled.name = 'NotAllowedError'
    webauthn.startRegistration.mockRejectedValue(cancelled)

    render(<PasskeyCard initial={[]} />)

    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      SIGN_IN_PROBLEMS.passkeyNotAllowed,
    )
  })

  test('shows what Django said when Django refused', async () => {
    api.registerPasskey.mockRejectedValue(new ApiError(409, 'That passkey is already registered.'))

    render(<PasskeyCard initial={[]} />)

    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'That passkey is already registered.',
    )
  })

  test('recovers, so a second attempt is possible', async () => {
    api.passkeyRegistrationOptions.mockRejectedValueOnce(new ApiError(500, 'Something broke.'))

    render(<PasskeyCard initial={[]} />)

    await userEvent.click(screen.getByRole('button', { name: PASSKEYS_CARD.add }))

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: PASSKEYS_CARD.add })).toBeEnabled()
  })
})

describe('revoking', () => {
  test('removes the one that was asked for', async () => {
    render(<PasskeyCard initial={[LAPTOP, PHONE]} />)

    await userEvent.click(removeButton('iPhone'))

    await waitFor(() => expect(api.deletePasskey).toHaveBeenCalledWith(2))
    expect(screen.queryByText('iPhone')).not.toBeInTheDocument()
    expect(screen.getByText('Work laptop')).toBeInTheDocument()
  })

  test('keeps the passkey on screen when the API refused', async () => {
    api.deletePasskey.mockRejectedValue(new ApiError(404, 'No such passkey.'))

    render(<PasskeyCard initial={[LAPTOP]} />)

    await userEvent.click(removeButton('Work laptop'))

    expect(await screen.findByRole('alert')).toHaveTextContent('No such passkey.')
    expect(screen.getByText('Work laptop')).toBeInTheDocument()
  })
})

describe('a browser that cannot make passkeys', () => {
  beforeEach(() => {
    webauthn.browserSupportsWebAuthn.mockReturnValue(false)
  })

  test('is told what to do instead', async () => {
    render(<PasskeyCard initial={[]} />)

    expect(await screen.findByText(PASSKEYS_CARD.unsupported)).toBeInTheDocument()
  })

  test('is not shown a button that would fail', async () => {
    render(<PasskeyCard initial={[]} />)

    await screen.findByText(PASSKEYS_CARD.unsupported)
    expect(screen.queryByRole('button', { name: PASSKEYS_CARD.add })).not.toBeInTheDocument()
  })

  test('can still revoke a passkey enrolled elsewhere', async () => {
    render(<PasskeyCard initial={[LAPTOP]} />)

    await screen.findByText(PASSKEYS_CARD.unsupported)
    expect(removeButton('Work laptop')).toBeInTheDocument()
  })
})

describe('what the server renders', () => {
  /*
   * The defect these describe was real and shipped in `passkey-manager.tsx`:
   * `browserSupportsWebAuthn()` was read during render, and on the server there is no `navigator`
   * to ask — so the server HTML of a perfectly capable machine said "this browser cannot create
   * passkeys".
   *
   * What is asserted here is the **server snapshot**, which is what the club pages render first:
   * `renderToString` takes `useSyncExternalStore`'s server branch whatever the environment, so
   * these fix the optimistic answer in place. They would not, on their own, have caught the
   * original bug — under jsdom `window` exists, so the old `typeof window !== 'undefined'` guard
   * reads as a browser here and the wrong branch never runs. Catching that needed a real server,
   * which is where it was found.
   */
  test('offers the enrol control, whatever the browser turns out to be', () => {
    webauthn.browserSupportsWebAuthn.mockReturnValue(false)

    const html = renderToString(<PasskeyCard initial={[]} />)

    expect(html).toContain(PASSKEYS_CARD.add)
  })

  test('never claims a browser it has not met cannot make passkeys', () => {
    webauthn.browserSupportsWebAuthn.mockReturnValue(false)

    const html = renderToString(<PasskeyCard initial={[]} />)

    expect(html).not.toContain(PASSKEYS_CARD.unsupported)
  })

  test('still renders the passkeys the server read', () => {
    const html = renderToString(<PasskeyCard initial={[LAPTOP]} />)

    expect(html).toContain('Work laptop')
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { ApiError, type User } from '@/lib/api'
import { ACCOUNT_HOME_PATH } from '@/lib/sign-in'
import { SIGN_IN, SIGN_IN_PROBLEMS } from '@/lib/sign-in-content'
import { SignInForm } from './SignInForm'

const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }))
const params = vi.hoisted(() => ({ next: null as string | null }))

vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(params.next ? { next: params.next } : {}),
}))

const api = vi.hoisted(() => ({
  startLogin: vi.fn(),
  loginWithPasskey: vi.fn(),
  loginWithCode: vi.fn(),
  sendLoginCode: vi.fn(),
}))

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return { ...actual, ...api }
})

const webauthn = vi.hoisted(() => ({
  browserSupportsWebAuthn: vi.fn(),
  startAuthentication: vi.fn(),
}))

vi.mock('@simplewebauthn/browser', () => webauthn)

const ADDRESS = 'thandiwe@example.co.za'

/** A customer: no membership, no nickname, and none of it read by this screen. */
const customer = (): User => ({
  id: '2b0d3a2c-6e0f-4a3f-8f4b-9b6c1f0d1a11',
  email: ADDRESS,
  first_name: 'Thandiwe',
  last_name: 'Mokoena',
  nickname: '',
  mobile: '',
  display_name: 'Thandiwe Mokoena',
  date_of_birth: null,
  date_of_birth_verified_at: null,
  status: 'active',
  membership_status: null,
  role: 'member',
  permissions: [],
  is_staff: false,
})

const submitAddress = async () => {
  await userEvent.type(screen.getByLabelText(SIGN_IN.emailLabel), ADDRESS)
  await userEvent.click(screen.getByRole('button', { name: SIGN_IN.emailContinue }))
}

beforeEach(() => {
  params.next = null
  webauthn.browserSupportsWebAuthn.mockReturnValue(true)
  webauthn.startAuthentication.mockResolvedValue({ id: 'credential' })
  api.startLogin.mockResolvedValue({ method: 'otp', options: null })
  api.sendLoginCode.mockResolvedValue({ detail: 'ok' })
  api.loginWithPasskey.mockResolvedValue(customer())
  api.loginWithCode.mockResolvedValue(customer())
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('the address step', () => {
  test('asks Django which credential to collect', async () => {
    render(<SignInForm />)
    await submitAddress()

    expect(api.startLogin).toHaveBeenCalledWith(ADDRESS)
  })

  test('lands on the code step for an address Django answered "otp" for', async () => {
    // Which is also the answer for an address with no account, and is what keeps the two
    // indistinguishable from the outside.
    render(<SignInForm />)
    await submitAddress()

    expect(await screen.findByLabelText(SIGN_IN.codeLabel)).toBeInTheDocument()
    // login/start has already sent the code; asking again would send a second one.
    expect(api.sendLoginCode).not.toHaveBeenCalled()
  })

  test('words the notice conditionally, so it says nothing about the address', async () => {
    render(<SignInForm />)
    await submitAddress()

    const notice = await screen.findByRole('status')

    expect(notice).toHaveTextContent(ADDRESS)
    expect(notice.textContent?.toLowerCase()).toContain('if')
  })
})

describe('the passkey ceremony', () => {
  beforeEach(() => {
    api.startLogin.mockResolvedValue({ method: 'passkey', options: { challenge: 'x' } })
  })

  test('signs in and sends the customer to their account', async () => {
    render(<SignInForm />)
    await submitAddress()

    await waitFor(() => expect(router.push).toHaveBeenCalledWith(ACCOUNT_HOME_PATH))
    // The refresh has to come first: every signed-in screen is a Server Component that read the
    // session when it rendered.
    expect(router.refresh).toHaveBeenCalled()
  })

  test('follows a safe ?next= instead', async () => {
    params.next = '/account/security'

    render(<SignInForm />)
    await submitAddress()

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/account/security'))
  })

  test('refuses to follow an off-site ?next=', async () => {
    params.next = '//evil.example.com'

    render(<SignInForm />)
    await submitAddress()

    await waitFor(() => expect(router.push).toHaveBeenCalledWith(ACCOUNT_HOME_PATH))
  })

  test('offers a code as a fallback when the ceremony fails, and says so', async () => {
    const cancelled = new Error('developer-facing')
    cancelled.name = 'NotAllowedError'
    webauthn.startAuthentication.mockRejectedValue(cancelled)

    render(<SignInForm />)
    await submitAddress()

    expect(await screen.findByRole('alert')).toHaveTextContent(SIGN_IN_PROBLEMS.passkeyNotAllowed)
    // The offer rewords itself, so it reads as a fallback rather than as the same button again.
    expect(
      screen.getByRole('button', { name: SIGN_IN.requestCodeInstead }),
    ).toBeInTheDocument()
  })

  test('asks for a code when the browser cannot answer a challenge at all', async () => {
    // Django prepared a challenge and therefore sent no code. Without this the customer is stuck.
    webauthn.browserSupportsWebAuthn.mockReturnValue(false)

    render(<SignInForm />)
    await submitAddress()

    expect(await screen.findByLabelText(SIGN_IN.codeLabel)).toBeInTheDocument()
    expect(api.sendLoginCode).toHaveBeenCalledWith(ADDRESS)
  })
})

describe('the code step', () => {
  test('keeps only the digits, so a pasted code still works', async () => {
    render(<SignInForm />)
    await submitAddress()

    const code = await screen.findByLabelText(SIGN_IN.codeLabel)

    await userEvent.type(code, 'Your code is 12 34-56')

    expect(code).toHaveValue('123456')
  })

  test('signs in with the code', async () => {
    render(<SignInForm />)
    await submitAddress()

    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(api.loginWithCode).toHaveBeenCalledWith(ADDRESS, '123456'))
    expect(router.push).toHaveBeenCalledWith(ACCOUNT_HOME_PATH)
  })

  test("shows Django's own refusal for a wrong code, and stays on the step", async () => {
    api.loginWithCode.mockRejectedValue(new ApiError(400, 'That code is not valid.'))

    render(<SignInForm />)
    await submitAddress()

    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '000000')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    expect(await screen.findByRole('alert')).toHaveTextContent('That code is not valid.')
    expect(screen.getByLabelText(SIGN_IN.codeLabel)).toBeInTheDocument()
    expect(router.push).not.toHaveBeenCalled()
  })

  test('will not send another code immediately', async () => {
    render(<SignInForm />)
    await submitAddress()

    await screen.findByLabelText(SIGN_IN.codeLabel)

    expect(screen.getByRole('button', { name: /Send a new code in/ })).toBeDisabled()
  })

  test('goes back to the address, clearing what was typed', async () => {
    render(<SignInForm />)
    await submitAddress()

    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.startOver }))

    expect(screen.getByLabelText(SIGN_IN.emailLabel)).toBeInTheDocument()
  })
})

describe('when the store cannot be reached', () => {
  test('says so in our own words rather than the runtime\'s', async () => {
    api.startLogin.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<SignInForm />)
    await submitAddress()

    expect(await screen.findByRole('alert')).toHaveTextContent(SIGN_IN_PROBLEMS.unreachable)
  })
})

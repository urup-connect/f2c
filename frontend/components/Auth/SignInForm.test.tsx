import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { SignInForm } from './SignInForm'
import { ApiError, type User } from '@/lib/api'
import { SIGN_IN, SIGN_IN_PROBLEMS } from '@/lib/sign-in-content'

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

const ADDRESS = 'thandi@example.co.za'

const userWithRole = (role: User['role']): User => ({
  id: '2b0d3a2c-6e0f-4a3f-8f4b-9b6c1f0d1a11',
  email: ADDRESS,
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  mobile: '',
  display_name: 'greenfingers',
  date_of_birth: null,
  date_of_birth_verified_at: null,
  status: 'active',
  role,
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
  api.loginWithPasskey.mockResolvedValue(userWithRole('member'))
  api.loginWithCode.mockResolvedValue(userWithRole('member'))
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('the address step', () => {
  test('asks for an address and nothing else', () => {
    render(<SignInForm />)

    expect(screen.getByLabelText(SIGN_IN.emailLabel)).toBeInTheDocument()
    expect(screen.queryByLabelText(SIGN_IN.codeLabel)).not.toBeInTheDocument()
  })

  test('lets the browser offer a saved passkey inline', () => {
    render(<SignInForm />)

    expect(screen.getByLabelText(SIGN_IN.emailLabel)).toHaveAttribute(
      'autocomplete',
      'username webauthn',
    )
  })

  test('asks Django which credential to collect', async () => {
    render(<SignInForm />)

    await submitAddress()

    await waitFor(() => expect(api.startLogin).toHaveBeenCalledWith(ADDRESS))
  })

  test('cannot ask for a code before an address is typed', () => {
    render(<SignInForm />)

    expect(screen.getByRole('button', { name: SIGN_IN.requestCode })).toBeDisabled()
  })
})

describe('when Django asks for a code', () => {
  test('moves to the code step', async () => {
    render(<SignInForm />)

    await submitAddress()

    expect(await screen.findByLabelText(SIGN_IN.codeLabel)).toBeInTheDocument()
  })

  test('does not send a second code, because login/start already sent one', async () => {
    render(<SignInForm />)

    await submitAddress()

    await screen.findByLabelText(SIGN_IN.codeLabel)
    expect(api.sendLoginCode).not.toHaveBeenCalled()
  })

  test('says a code is on its way without saying the address belongs to anybody', async () => {
    // Four different situations produce this same answer from Django. Copy that said
    // "we have sent you a code" would give away what the API withholds.
    render(<SignInForm />)

    await submitAddress()

    const notice = await screen.findByRole('status')

    expect(notice).toHaveTextContent(/^If/)
    expect(notice).toHaveTextContent(/belongs to a member/)
  })
})

describe('when Django asks for a passkey', () => {
  beforeEach(() => {
    api.startLogin.mockResolvedValue({ method: 'passkey', options: { challenge: 'x' } })
  })

  test('runs the ceremony and signs in', async () => {
    render(<SignInForm />)

    await submitAddress()

    await waitFor(() => expect(webauthn.startAuthentication).toHaveBeenCalled())
    expect(api.loginWithPasskey).toHaveBeenCalledWith(ADDRESS, { id: 'credential' })
  })

  test('falls back to a code when this browser cannot answer the challenge', async () => {
    // Django prepared a challenge and therefore sent no code. Leaving the member here
    // would strand them.
    webauthn.browserSupportsWebAuthn.mockReturnValue(false)

    render(<SignInForm />)

    await submitAddress()

    expect(await screen.findByLabelText(SIGN_IN.codeLabel)).toBeInTheDocument()
    expect(api.sendLoginCode).toHaveBeenCalledWith(ADDRESS)
  })

  test('is not a dead end when the member cancels', async () => {
    const cancelled = new Error('irrelevant')
    cancelled.name = 'NotAllowedError'
    webauthn.startAuthentication.mockRejectedValue(cancelled)

    render(<SignInForm />)

    await submitAddress()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      SIGN_IN_PROBLEMS.passkeyNotAllowed,
    )
  })

  test('offers the code as a fallback, worded as one', async () => {
    // Rather than silently swapping the form out from under somebody who cancelled
    // by accident.
    const cancelled = new Error('irrelevant')
    cancelled.name = 'NotAllowedError'
    webauthn.startAuthentication.mockRejectedValue(cancelled)

    render(<SignInForm />)

    await submitAddress()

    expect(
      await screen.findByRole('button', { name: SIGN_IN.requestCodeInstead }),
    ).toBeInTheDocument()
  })

  test('stays on the address step after a cancelled passkey', async () => {
    const cancelled = new Error('irrelevant')
    cancelled.name = 'NotAllowedError'
    webauthn.startAuthentication.mockRejectedValue(cancelled)

    render(<SignInForm />)

    await submitAddress()

    await screen.findByRole('alert')
    expect(screen.getByLabelText(SIGN_IN.emailLabel)).toBeInTheDocument()
  })
})

describe('the code step', () => {
  const reachCodeStep = async () => {
    render(<SignInForm />)
    await submitAddress()
    return screen.findByLabelText(SIGN_IN.codeLabel)
  }

  test('keeps only the digits, so a pasted code still works', async () => {
    const field = await reachCodeStep()

    await userEvent.type(field, '12 34-56')

    expect(field).toHaveValue('123456')
  })

  test('exchanges the code for a session', async () => {
    const field = await reachCodeStep()

    await userEvent.type(field, '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(api.loginWithCode).toHaveBeenCalledWith(ADDRESS, '123456'))
  })

  test('shows what Django said when the code was wrong', async () => {
    api.loginWithCode.mockRejectedValue(
      new ApiError(401, 'That code is not valid. Request a new one.'),
    )

    const field = await reachCodeStep()

    await userEvent.type(field, '000000')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    expect(await screen.findByRole('alert')).toHaveTextContent('That code is not valid.')
  })

  test('lets the member try again after a wrong code', async () => {
    api.loginWithCode.mockRejectedValue(new ApiError(401, 'That code is not valid.'))

    const field = await reachCodeStep()

    await userEvent.type(field, '000000')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: SIGN_IN.codeSubmit })).toBeEnabled()
  })

  test('will not send another code immediately', async () => {
    await reachCodeStep()

    expect(screen.getByRole('button', { name: /^Send a new code in/ })).toBeDisabled()
  })

  test('offers a way back to the address step', async () => {
    await reachCodeStep()

    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.startOver }))

    expect(screen.getByLabelText(SIGN_IN.emailLabel)).toBeInTheDocument()
  })
})

describe('where a member lands', () => {
  test('a member goes to the member area', async () => {
    render(<SignInForm />)

    await submitAddress()
    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/member'))
  })

  test('a cultivator goes to the cultivation area', async () => {
    api.loginWithCode.mockResolvedValue(userWithRole('cultivator'))

    render(<SignInForm />)

    await submitAddress()
    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/cultivator'))
  })

  test('an administrator goes to the administration area', async () => {
    api.loginWithCode.mockResolvedValue(userWithRole('admin'))

    render(<SignInForm />)

    await submitAddress()
    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/admin'))
  })

  test('discards the signed-out render before navigating', async () => {
    // Club screens are Server Components that read the session when they render.
    render(<SignInForm />)

    await submitAddress()
    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(router.refresh).toHaveBeenCalled())
  })

  test('follows a safe next in preference to the role home', async () => {
    params.next = '/member/plants'

    render(<SignInForm />)

    await submitAddress()
    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/member/plants'))
  })

  test('ignores a next that would leave the site', async () => {
    params.next = '//evil.example.com'

    render(<SignInForm />)

    await submitAddress()
    await userEvent.type(await screen.findByLabelText(SIGN_IN.codeLabel), '123456')
    await userEvent.click(screen.getByRole('button', { name: SIGN_IN.codeSubmit }))

    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/member'))
  })
})

describe('when the API cannot be reached', () => {
  test('says so without showing what the runtime said', async () => {
    api.startLogin.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<SignInForm />)

    await submitAddress()

    expect(await screen.findByRole('alert')).toHaveTextContent(SIGN_IN_PROBLEMS.unreachable)
  })

  test('leaves the member able to try again', async () => {
    api.startLogin.mockRejectedValue(new TypeError('Failed to fetch'))

    render(<SignInForm />)

    await submitAddress()

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: SIGN_IN.emailContinue })).toBeEnabled()
  })
})

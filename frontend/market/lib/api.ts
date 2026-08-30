/**
 * The only module that knows how to reach the Django API from the store.
 *
 * Safe to import from both server and client components. Anything that needs request-scoped
 * cookies lives in `lib/server-api.ts` instead, because `next/headers` cannot be imported into a
 * client bundle.
 *
 * **This is the club's `lib/api.ts` less everything the club owns.** No membership, no checkout
 * token, no nickname availability, no strain catalogue. What is left is the platform spine — the
 * session, the two credentials, and the account — which is exactly the part `design/verticals.md`
 * section 3 lists as shared, and exactly the part that will move into `packages/` when the seam is
 * obvious. See `frontend/README.md`.
 */

import type {
  AuthenticationResponseJSON,
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
  RegistrationResponseJSON,
} from '@simplewebauthn/browser'

/** Base URL used by server components and route handlers (container network). */
const SERVER_BASE_URL = process.env.DJANGO_API_URL ?? 'http://localhost:8000'

/**
 * The tag the server writes the browser-facing API address into.
 *
 * **Read from the document rather than from `process.env`, and that is the whole point.** A
 * `NEXT_PUBLIC_` variable is inlined into the bundle by `next build`, which tied every image to one
 * environment and made a promoted artefact carry the wrong address — `design/todo.md` Block 0 P6.
 * A client component has no `process.env` at runtime, so the value has to arrive in the HTML. The
 * root layout renders it; `lib/api-address.ts` produces it.
 */
export const API_BASE_META_NAME = 'f2c-api-base'

/** Memoised: the tag is written once per document and cannot change under a loaded page. */
let browserBaseUrl: string | undefined

const readBrowserBaseUrl = (): string => {
  if (browserBaseUrl !== undefined) return browserBaseUrl

  const content = document
    .querySelector(`meta[name="${API_BASE_META_NAME}"]`)
    ?.getAttribute('content')
    ?.trim()

  // No silent default. A localhost fallback here is what the old `?? 'http://localhost:8000'`
  // was, and it sent every deployed browser request to the member's own machine while the page
  // looked fine. Failing loudly is the smaller harm: the tag is rendered by the root layout, so
  // its absence is a wiring fault that shows up on the first request rather than in production.
  if (!content) {
    throw new Error(
      `The <meta name="${API_BASE_META_NAME}"> tag is missing, so the API address is unknown. ` +
        'It is rendered by the root layout from DJANGO_API_PUBLIC_URL.',
    )
  }

  browserBaseUrl = content
  return content
}

/** Exposed for tests, which share one module instance across cases. */
export const resetApiBaseUrlCache = () => {
  browserBaseUrl = undefined
}

export const apiBaseUrl = () =>
  typeof window === 'undefined' ? SERVER_BASE_URL : readBrowserBaseUrl()

/**
 * The signed-in account, mirroring `UserOut` in `accounts/schemas.py`.
 *
 * One API, one shape, two storefronts — so this type carries fields the store never reads. They
 * are declared rather than omitted because the payload has them and a narrower type would be a
 * second, quieter contract that drifts from the first.
 *
 * `id` is a UUID string, not a number. `email` and the names are nullable or blank because an
 * erased account keeps its row; it can never sign in, so the shape will not appear in practice,
 * but the type has to admit it.
 */
export type User = {
  id: string
  email: string | null
  first_name: string
  last_name: string
  /**
   * The club's member-facing handle. **Blank for a store customer**, who has a name and needs no
   * pseudonym — `design/verticals.md` section 6. Nothing in the store renders it.
   */
  nickname: string
  /** `+27` and nine digits, or blank. A contact detail, not a credential. */
  mobile: string
  display_name: string
  /** ISO date, or null when none is on file. A store customer is never asked for one. */
  date_of_birth: string | null
  /** ISO datetime. Null until somebody checked the date against a document. */
  date_of_birth_verified_at: string | null
  /**
   * Whether this identity may sign in, and nothing else. Only `active` can.
   *
   * **This is the whole of the store's gate**, which is the point of the identity split: buying
   * produce requires an account and nothing else — no membership, no subscription, no identity
   * number, no consent record. See `lib/session.ts`.
   */
  status:
    | 'active'
    | 'suspended'
    | 'inactive'
    /**
     * An identity that holds records and authenticates nobody — today only a club sharing member,
     * which is a placeholder rather than a person. It cannot reach a signed-in session. The
     * contract admits it because the type describes the column, not only what a browser will see.
     */
    | 'non_authenticating'
  /**
   * Where a club membership stands, or `null` for an account that holds none.
   *
   * **`null` is the ordinary case here**, and the store must never read this to decide anything: a
   * customer owes the club nothing, and a store that consulted a club membership before selling a
   * kilogram of carrots would be the tenancy column `design/verticals.md` section 11 refuses.
   */
  membership_status:
    | 'pending'
    | 'pending_payment'
    | 'active'
    | 'suspended'
    | 'lapsed'
    | 'sharing'
    | null
  /**
   * Which club destination this account belongs on, most capable first. Derived, for the club's
   * routing. The store has one signed-in area and does not read it.
   */
  role: 'admin' | 'cultivator' | 'member'
  /**
   * Every `platform.*` action this account holds, sorted.
   *
   * For rendering, never for deciding — every endpoint checks the permission itself. The store
   * reads it for one thing today: whether to offer the market administration area, which does not
   * exist yet. See `lib/navigation.ts`.
   */
  permissions: string[]
  is_staff: boolean
}

export type Health = {
  status: string
  debug: boolean
}

/** One enrolled WebAuthn credential, as the API reports it. */
export type Passkey = {
  id: number
  name: string
  /** True for a synced passkey (iCloud Keychain, Google Password Manager). */
  backed_up: boolean
  device_type: string
  created_at: string
  last_used_at: string | null
}

/** What `startLogin` came back with: which credential to collect next. */
export type LoginStart = {
  method: 'passkey' | 'otp'
  options: PublicKeyCredentialRequestOptionsJSON | null
}

/**
 * A non-2xx response from Django, carrying its status, its message and its body.
 *
 * `body` is the parsed JSON, when there was any, and `null` otherwise. django-ninja error responses
 * are not all one shape: most carry only `{"detail": "..."}`, which `message` already holds, but
 * some carry a refusal per field. Typed as `unknown`, so a caller that wants it has to narrow it
 * deliberately.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body: unknown = null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Turn a Django response into data, or throw an `ApiError` describing it. */
export async function unwrap<T>(response: Response): Promise<T> {
  const body = await response.text()
  const parsed = body ? safeJsonParse(body) : null

  if (!response.ok) {
    // django-ninja reports errors as {"detail": "..."}.
    const detail =
      (parsed && typeof parsed === 'object' && 'detail' in parsed
        ? String((parsed as { detail: unknown }).detail)
        : null) ?? `Request failed with status ${response.status}`
    throw new ApiError(response.status, detail, parsed)
  }

  return parsed as T
}

function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

/* -------------------------------------------------------------------------- */
/* Browser-side calls                                                         */
/* -------------------------------------------------------------------------- */

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

/**
 * Return a CSRF token, asking Django to issue one if the cookie is missing.
 *
 * Django only sets `csrftoken` once something requests it, so a fresh visitor has no token until
 * this runs.
 */
export async function ensureCsrfToken(): Promise<string> {
  const existing = readCookie('csrftoken')
  if (existing) return existing

  await fetch(`${apiBaseUrl()}/api/auth/csrf`, { credentials: 'include' })

  const issued = readCookie('csrftoken')
  if (!issued) {
    throw new ApiError(
      500,
      'Django did not issue a CSRF cookie. Check that the API origin is listed in ' +
        'DJANGO_CORS_ALLOWED_ORIGINS and shares a hostname with this app.',
    )
  }
  return issued
}

/** `fetch` against the API from the browser, with cookies and CSRF handled. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    headers.set('X-CSRFToken', await ensureCsrfToken())
    if (init.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json')
    }
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    // Required: the session lives in a cookie on the Django origin.
    credentials: 'include',
  })

  return unwrap<T>(response)
}

export const logout = () => apiFetch<{ detail: string }>('/api/auth/logout', { method: 'POST' })

/* -------------------------------------------------------------------------- */
/* Sign-in                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Ask Django which credential this address should be challenged for.
 *
 * `passkey` carries the WebAuthn request options. `otp` means a code has been emailed — and is also
 * what an unrecognised address gets back, so nothing here tells the caller whether an account
 * exists.
 *
 * **The code is sent by the store's own mail server**, because Django resolves the storefront from
 * the host the request arrived on rather than from the account. A code requested at the store's
 * domain is signed by the store. See `app/core/storefronts/mail.py`.
 */
export const startLogin = (email: string) =>
  apiFetch<LoginStart>('/api/auth/login/start', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })

export const loginWithPasskey = (email: string, credential: AuthenticationResponseJSON) =>
  apiFetch<User>('/api/auth/login/passkey', {
    method: 'POST',
    body: JSON.stringify({ email, credential }),
  })

/** Send (or resend) an emailed sign-in code. Always resolves. */
export const sendLoginCode = (email: string) =>
  apiFetch<{ detail: string }>('/api/auth/otp/start', {
    method: 'POST',
    body: JSON.stringify({ email }),
  })

export const loginWithCode = (email: string, code: string) =>
  apiFetch<User>('/api/auth/otp/verify', {
    method: 'POST',
    body: JSON.stringify({ email, code }),
  })

/* -------------------------------------------------------------------------- */
/* Passkey management (requires a session)                                    */
/* -------------------------------------------------------------------------- */

/*
 * A passkey enrolled here is a passkey for the store and for nothing else. WebAuthn binds a
 * credential to a registrable domain, and the two storefronts sit on separate ones, so a customer
 * who is also a club member enrols twice and signs in twice. That is `design/verticals.md`
 * section 8 and risk 3, and it is not something this application can paper over.
 */

export const passkeyRegistrationOptions = () =>
  apiFetch<{ options: PublicKeyCredentialCreationOptionsJSON }>('/api/auth/passkeys/options', {
    method: 'POST',
  })

export const registerPasskey = (credential: RegistrationResponseJSON, name: string) =>
  apiFetch<Passkey>('/api/auth/passkeys', {
    method: 'POST',
    body: JSON.stringify({ credential, name }),
  })

export const listPasskeys = () => apiFetch<Passkey[]>('/api/auth/passkeys')

export const deletePasskey = (id: number) =>
  apiFetch<{ detail: string }>(`/api/auth/passkeys/${id}`, { method: 'DELETE' })

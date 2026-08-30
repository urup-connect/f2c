import 'server-only'

import { cookies } from 'next/headers'

import { ApiError, apiBaseUrl, unwrap, type Health, type Passkey, type User } from './api'
import type { PublishedDocument } from './documents'
import type { Profile } from './profile-api'

/**
 * Server-side calls to Django.
 *
 * A server component has no browser to attach cookies for it, so the incoming request's cookies
 * are forwarded by hand. Without this, every server-rendered page would look logged out.
 */
async function serverFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const cookieStore = await cookies()
  const headers = new Headers(init.headers)
  const cookieHeader = cookieStore.toString()
  if (cookieHeader) headers.set('Cookie', cookieHeader)

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    // Session-dependent responses must never be cached across users.
    cache: 'no-store',
  })

  return unwrap<T>(response)
}

/** The signed-in account, or null when there is no valid session. */
export async function getCurrentUser(): Promise<User | null> {
  try {
    return await serverFetch<User>('/api/auth/me')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** API liveness, or null when Django is unreachable. */
export async function getHealth(): Promise<Health | null> {
  try {
    return await serverFetch<Health>('/api/health')
  } catch {
    return null
  }
}

/**
 * The signed-in customer's own record, or null when there is no valid session.
 *
 * Read on the server so the whole screen is in the first paint. That matters more here than it
 * would elsewhere: a details form that arrives empty and fills in a moment later is a form somebody
 * can start typing into before their own details land on top of what they typed.
 *
 * A 401 answers null rather than throwing, matching `getCurrentUser`. It cannot happen past the
 * account layout's guard, and the branch exists so a caller cannot forget it.
 */
export async function getProfile(): Promise<Profile | null> {
  try {
    return await serverFetch<Profile>('/api/accounts/me/profile')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** The account's enrolled passkeys, or an empty list when signed out. */
export async function getPasskeys(): Promise<Passkey[]> {
  try {
    return await serverFetch<Passkey[]>('/api/auth/passkeys')
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return []
    throw error
  }
}

/**
 * The store's public legal pages, or null when they could not be read.
 *
 * **Unauthenticated, and scoped by the host Django saw** — not by anything this application sends.
 * There is no session on a legal page and there cannot be one, so `storefront_for_request` reads
 * the domain the request arrived on. Two consequences, and the second is a local-development trap
 * worth stating in the code that meets it:
 *
 * 1. In a deployment, `DJANGO_STOREFRONT_HOSTS` must map the store's API hostname to `market`, or
 *    these pages serve the club's documents on the store's domain.
 * 2. Locally both applications call the same Django on `localhost:8000`, which is an unmapped host
 *    and therefore falls back to `DJANGO_DEFAULT_STOREFRONT` — the club. Set that to `market` while
 *    working on the store, or expect the club's rules to appear here. `README.md` says so too.
 *
 * `null` rather than a throw for an unreachable API, because the index page renders a sentence
 * saying the documents could not be read. A legal page that 500s tells a shopper nothing and looks
 * like something to worry about.
 */
export async function getPublishedDocuments(): Promise<readonly PublishedDocument[] | null> {
  try {
    const payload = await serverFetch<{ documents: PublishedDocument[] }>(
      '/api/documents/published',
    )
    return payload.documents
  } catch {
    return null
  }
}

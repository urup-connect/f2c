/**
 * The API address the browser is told to use, read at request time.
 *
 * **This module exists to undo a build-time decision.** `NEXT_PUBLIC_DJANGO_API_URL` was inlined
 * into the browser bundle by `next build` — verified: it landed in two chunks under
 * `.next/static/chunks` — which made every image specific to one environment. A build could not be
 * promoted from QA to Production; it had to be rebuilt, and a promoted artefact would have carried
 * the wrong address while looking correct. That is `design/todo.md` Block 0 P6.
 *
 * The fix is not to drop the `NEXT_PUBLIC_` prefix. A client component has no `process.env` at
 * runtime, and there are twenty-five of them in this application — the sign-in form, the passkey
 * cards, the admin screens. So the value is read here, on the server, once per request, and written
 * into the document as a `<meta>` tag that `lib/api.ts` reads in the browser. The container is told
 * the address; the bundle no longer knows it.
 *
 * **Nothing here runs at module load.** `next build` imports this file to analyse the route tree,
 * and a validation that ran on import would put the variable back into the build's requirements —
 * the exact thing being removed. So the reader is a function, called during render.
 *
 * Server-only by construction: `lib/api.ts` holds the meta-tag name because it is imported into the
 * client bundle, and this module imports the name from there rather than the other way round.
 */

import { API_BASE_META_NAME } from './api'
import { type EnvRecord, misconfigured } from './env'

export { API_BASE_META_NAME }

/**
 * Validates the browser-facing API address. Pure.
 *
 * **The address must be publicly resolvable and must sit inside the same registrable domain the
 * browser uses for this application** — `backend.f2c-cannabis.co.za` with `f2c-cannabis.co.za`,
 * never `backend.f2c.co.za`. Otherwise the request is cross-site and the `SameSite=Lax` session
 * cookie is not sent. See design/conflict.md C30. That pairing cannot be checked here, because this
 * module is not told which host served the request; what can be checked is that somebody set the
 * variable at all, which is the failure that actually happens.
 */
export const readPublicApiBaseUrl = (env: EnvRecord): string => {
  const value = env.DJANGO_API_PUBLIC_URL?.trim()

  if (!value) {
    throw misconfigured(
      'DJANGO_API_PUBLIC_URL',
      'not set. It is the API address the member’s browser uses, and it is read at request ' +
        'time rather than baked into the bundle, so it must be set on the running container',
      'Set it in .env.local for local development, or in the container environment for QA and ' +
        'Production.',
    )
  }

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw misconfigured('DJANGO_API_PUBLIC_URL', `set to "${value}", which is not an absolute URL`)
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw misconfigured(
      'DJANGO_API_PUBLIC_URL',
      `set to the "${url.protocol}" scheme, which is not http or https`,
    )
  }

  // Trailing slashes are stripped because `lib/api.ts` appends paths that start with one, and
  // `https://host//api/...` is a different path to Django's URL resolver.
  return value.replace(/\/+$/, '')
}

/** The running deployment's browser-facing API address. Called during render, never on import. */
export const publicApiBaseUrl = (): string => readPublicApiBaseUrl(process.env)

import { NextResponse, type NextRequest } from 'next/server'
import { indexingHeaders } from '@/lib/seo'
import { siteConfig } from '@/lib/site'

/** The request header carrying the path being rendered. See below. */
export const PATHNAME_HEADER = 'x-pathname'

/*
 * Suppresses search engine indexing everywhere except Production, and tells the server components
 * beneath which path they are rendering.
 *
 * `proxy`, not `middleware`: the middleware convention is deprecated in Next.js 16 and renamed to
 * proxy.
 *
 * **`siteConfig()` is read here at request time, and that only works because proxy runs on Node.**
 * `SITE_URL` and `APP_ENV` are container settings now rather than build arguments (design/deploy.md
 * R-D4), and under the old edge default `process.env` was inlined at build — so a read here would
 * have quietly returned the build's value instead of erroring. Next 16 defaults proxy to the Node.js
 * runtime, where `process.env` is the container's. There is deliberately no `export const runtime`
 * below: the option is not available in a proxy file and setting it throws. See the bundled proxy
 * reference under `node_modules/next/dist/docs`, section "Runtime".
 *
 * The indexing rule is a response header rather than page metadata. That was originally because
 * `export const metadata` is evaluated when a static route is built, so a build promoted from QA to
 * Production would have carried the wrong value — no longer true, now that the root layout builds
 * its metadata in `generateMetadata` and nothing is prerendered. It stays a header because one
 * place here covers every response the matcher sees, rather than every page having to remember a
 * `robots` entry of its own.
 *
 * The pathname is a **request** header, added on the way in. A layout is not told which route it is
 * wrapping — that is by design, since a layout is meant to be reusable — but the account layout has
 * to send an unauthenticated visitor to /sign-in carrying where they were going, and it cannot say
 * where that was without this. Setting it here is the supported way to get a request-scoped value
 * to a Server Component; the alternative is dropping the session check into every page, which means
 * every future page has to remember to make it.
 *
 * Nothing trusts this header's value. It arrives from the client on every request and could say
 * anything; the account layout runs it through the same safety check the sign-in form applies to a
 * `?next=` before putting it in a URL. See `lib/sign-in.ts`.
 */
export function proxy(request: NextRequest) {
  const requestHeaders = new Headers(request.headers)
  requestHeaders.set(PATHNAME_HEADER, request.nextUrl.pathname)

  const response = NextResponse.next({ request: { headers: requestHeaders } })

  for (const [header, value] of Object.entries(indexingHeaders(siteConfig()))) {
    response.headers.set(header, value)
  }

  return response
}

export const config = {
  // Everything a crawler could reach, excluding Next's own internal asset routes.
  matcher: '/((?!_next/static|_next/image).*)',
}

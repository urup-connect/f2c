import { NextResponse, type NextRequest } from 'next/server'
import { indexingHeaders } from '@/lib/seo'
import { SITE_CONFIG } from '@/lib/site'

/** The request header carrying the path being rendered. See below. */
export const PATHNAME_HEADER = 'x-pathname'

/*
 * Suppresses search engine indexing everywhere except Production, and tells the server components
 * beneath which path they are rendering.
 *
 * `proxy`, not `middleware`: the middleware convention is deprecated in Next.js 16 and renamed to
 * proxy.
 *
 * The indexing rule is a response header rather than page metadata because `export const metadata`
 * is evaluated when a static route is built, so a build promoted from QA to Production would carry
 * the wrong value.
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

  for (const [header, value] of Object.entries(indexingHeaders(SITE_CONFIG))) {
    response.headers.set(header, value)
  }

  return response
}

export const config = {
  // Everything a crawler could reach, excluding Next's own internal asset routes.
  matcher: '/((?!_next/static|_next/image).*)',
}

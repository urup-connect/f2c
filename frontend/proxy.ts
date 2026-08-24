import { NextResponse } from 'next/server'
import { indexingHeaders } from '@/lib/seo'
import { SITE_CONFIG } from '@/lib/site'

/*
 * Suppresses search engine indexing everywhere except Production.
 *
 * `proxy`, not `middleware`: the middleware convention is deprecated in Next.js 16 and renamed
 * to proxy. See design/features/public-landing-and-auth-routing.md section 6.4.
 *
 * A response header rather than page metadata because `export const metadata` is evaluated
 * when a static route is built, so a build promoted from QA to Production would carry the
 * wrong value. See section 6.3.
 */
export function proxy() {
  const response = NextResponse.next()

  for (const [header, value] of Object.entries(indexingHeaders(SITE_CONFIG))) {
    response.headers.set(header, value)
  }

  return response
}

export const config = {
  // Everything a crawler could reach, excluding Next's own internal asset routes.
  matcher: '/((?!_next/static|_next/image).*)',
}

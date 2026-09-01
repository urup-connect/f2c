import { NextResponse, type NextRequest } from 'next/server'
import {
  CAMPAIGN_COOKIE,
  campaignCookieOptions,
  mergeCampaign,
  readCampaign,
  readTouch,
  serialiseCampaign,
} from '@/lib/campaign-cookie'
import { indexingHeaders } from '@/lib/seo'
import { SITE_CONFIG } from '@/lib/site'

/** The request header carrying the path being rendered. See below. */
export const PATHNAME_HEADER = 'x-pathname'

/*
 * Suppresses search engine indexing everywhere except Production, and tells the server components
 * beneath which path they are rendering.
 *
 * `proxy`, not `middleware`: the middleware convention is deprecated in Next.js 16 and renamed
 * to proxy. See design/features/public-landing-and-auth-routing.md section 6.4.
 *
 * The indexing rule is a response header rather than page metadata because `export const metadata`
 * is evaluated when a static route is built, so a build promoted from QA to Production would carry
 * the wrong value. See section 6.3.
 *
 * The pathname is a **request** header, added on the way in. A layout is not told which route it
 * is wrapping — that is by design, since a layout is meant to be reusable — but the club layout has
 * to send an unauthenticated visitor to /login carrying where they were going, and it cannot say
 * where that was without this. Setting it here is the supported way to get a request-scoped value
 * to a Server Component; the alternative is dropping the session check into every page, which
 * means every future club page has to remember to make it.
 *
 * Nothing trusts this header's value. It arrives from the client on every request and could say
 * anything; the club layout runs it through the same safety check the sign-in form applies to a
 * `?next=` before putting it in a URL. See `lib/sign-in.ts`.
 *
 * The campaign cookie is written here for the same reason the pathname header is: this is the only
 * place that sees every arrival. A visitor following `?utm_source=instagram` to the landing page is
 * three redirects away from the form that registers them — `/join` deliberately discards the age
 * pass and sends them to `/age-check`, and a redirect carries no query string — so a campaign not
 * captured on the way in is a campaign already lost. See `lib/campaign-cookie.ts`.
 */
export function proxy(request: NextRequest) {
  const requestHeaders = new Headers(request.headers)
  requestHeaders.set(PATHNAME_HEADER, request.nextUrl.pathname)

  const response = NextResponse.next({ request: { headers: requestHeaders } })

  for (const [header, value] of Object.entries(indexingHeaders(SITE_CONFIG))) {
    response.headers.set(header, value)
  }

  recordCampaign(request, response)

  return response
}

/**
 * Writes the campaign cookie where this request is a tagged arrival, and touches nothing otherwise.
 *
 * **Only on a `GET`.** A server action posts back to the URL the form was rendered on, so a
 * submission from `/signup?utm_source=instagram` carries the same parameters as the visit that
 * produced it — and recording it would invent a second arrival minutes after the first, differing
 * only in its timestamp. Django would faithfully store two touches for one visit.
 *
 * **Nothing is written for an untagged visit**, which is what keeps this off the hot path: no
 * campaign parameters, no ad click and no external referrer means no `Set-Cookie` header at all, so
 * an ordinary page view is unchanged and stays as cacheable as it was.
 *
 * The existing cookie is read to keep the first touch it already holds. The visitor arriving now is
 * always the last touch; they are the first only if there was nothing before them.
 */
function recordCampaign(request: NextRequest, response: NextResponse) {
  if (request.method !== 'GET') return

  const touch = readTouch(request.nextUrl, request.headers.get('referer'), new Date())
  if (!touch) return

  const existing = readCampaign(request.cookies.get(CAMPAIGN_COOKIE)?.value)
  const value = serialiseCampaign(mergeCampaign(existing, touch))

  // `null` means even the campaign itself would not fit in a cookie the browser will keep. Leaving
  // whatever is already there beats replacing it with a value that gets dropped.
  if (!value) return

  response.cookies.set(CAMPAIGN_COOKIE, value, campaignCookieOptions(SITE_CONFIG))
}

export const config = {
  // Everything a crawler could reach, excluding Next's own internal asset routes.
  matcher: '/((?!_next/static|_next/image).*)',
}

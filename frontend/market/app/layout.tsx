import type { Metadata, Viewport } from 'next'
import { Fraunces, Inter } from 'next/font/google'
import './globals.css'
import { STORE_BRAND } from '@/lib/brand'
import { SITE_CONFIG } from '@/lib/site'

/*
 * Store typefaces — still placeholders. The logo settled the palette, not the type; see
 * app/globals.css and lib/brand.ts.
 * next/font downloads and self-hosts these at build time, so nobody's browser contacts Google's font
 * hosts. That is a privacy property rather than a performance one, and it is the reason both
 * applications load fonts this way.
 */
const inter = Inter({
  variable: '--font-inter',
  subsets: ['latin'],
})

/*
 * Fraunces is a variable font with an optical-size axis; the default instance is what is wanted here
 * and no axis is pinned, because pinning one before a designer has an opinion is inventing a
 * decision. Weights are listed rather than left to the variable range so the payload is bounded.
 */
const fraunces = Fraunces({
  variable: '--font-fraunces',
  subsets: ['latin'],
  weight: ['400', '600'],
})

export const metadata: Metadata = {
  /*
   * Absolute origin for canonical and social URLs, so they never resolve against whichever host
   * served the request.
   */
  metadataBase: new URL(SITE_CONFIG.siteUrl),
  /*
   * Default deny. Only the public pages override this, so a route added later is kept out of search
   * results without anyone having to remember to exclude it — and `lib/seo.ts` is where the short list
   * of exceptions is written down.
   */
  robots: { index: false, follow: false },
  title: {
    default: STORE_BRAND.name,
    template: `%s | ${STORE_BRAND.name}`,
  },
  description: STORE_BRAND.standfirst,
  applicationName: STORE_BRAND.name,
}

/*
 * The tint a mobile browser paints its own chrome with. It is the green of `StoreHeader` and the
 * landing hero, so the chrome reads as a continuation of the header rather than a cream stripe
 * above it, and it repeats `app/manifest.ts` for the same reason that file gives: neither a meta
 * tag nor a JSON manifest can resolve a custom property out of `app/globals.css`.
 */
export const viewport: Viewport = {
  themeColor: '#0B3D1C',
}

export default function RootLayout({ children }: LayoutProps<'/'>) {
  return (
    <html
      lang="en-ZA"
      className={`${inter.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  )
}

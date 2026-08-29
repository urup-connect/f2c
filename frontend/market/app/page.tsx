import type { Metadata } from 'next'

import { Footer } from '@/components/Landing/Footer'
import { Hero } from '@/components/Landing/Hero'
import { NotOpenNotice } from '@/components/Landing/NotOpenNotice'
import { Steps } from '@/components/Landing/Steps'
import { LANDING } from '@/lib/landing-content'

/*
 * One of the two routes the product may index — see `lib/seo.ts`, which holds the list. Every other
 * route inherits `noindex, nofollow` from the root layout.
 *
 * Next merges metadata shallowly and a nested field such as `robots` is replaced wholesale by the
 * last segment to declare it, so declaring it here overrides the layout's default deny.
 */
export const metadata: Metadata = {
  robots: { index: true, follow: true },
}

/*
 * Read at request time so the copyright year is the year the page is served rather than the year it
 * was built. A statically rendered store front door would otherwise carry a stale year from the first
 * of January until the next deployment — and it is also what keeps the year out of the component, see
 * `Footer`.
 */
export const dynamic = 'force-dynamic'

/*
 * The footer sits outside `main` on purpose: nested inside it, a `footer` element is not exposed as
 * the page's `contentinfo` landmark.
 */
export default function Home() {
  return (
    <>
      <main className="flex flex-1 flex-col">
        <Hero />
        <NotOpenNotice />
        <Steps
          heading={LANDING.howItWorks.heading}
          steps={LANDING.howItWorks.steps}
          form="numbered"
        />
        <Steps heading={LANDING.why.heading} steps={LANDING.why.points} />
      </main>

      <Footer year={new Date().getFullYear()} />
    </>
  )
}

import type { Metadata } from 'next'
import { BrandStory } from '@/components/Landing/BrandStory'
import { BrandValues } from '@/components/Landing/BrandValues'
import { JoinBand } from '@/components/Landing/JoinBand'
import { LandingFooter } from '@/components/Landing/LandingFooter'
import { LandingHero } from '@/components/Landing/LandingHero'
import { StraplineRibbon } from '@/components/Landing/StraplineRibbon'

/*
 * The one route in the product that may be indexed. Every other route inherits
 * `noindex, nofollow` from the root layout — see
 * design/features/public-landing-and-auth-routing.md section 6.3.
 *
 * Next merges metadata shallowly and a nested field such as `robots` is replaced wholesale by
 * the last segment to declare it, so declaring it here overrides the layout's default deny.
 */
export const metadata: Metadata = {
  robots: { index: true, follow: true },
}

/*
 * The footer sits outside `main` on purpose: nested inside it, a `footer` element is not
 * exposed as the page's `contentinfo` landmark.
 * See design/features/landing-page-engagement.md section 6.5.
 */
export default function Home() {
  return (
    <>
      <main className="flex flex-1 flex-col">
        <LandingHero />
        <StraplineRibbon />
        <BrandValues />
        <BrandStory />
        <JoinBand />
      </main>

      <LandingFooter />
    </>
  )
}

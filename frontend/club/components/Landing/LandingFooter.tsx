import { Logo } from '@/components/Brand/Logo'
import { FOOTER } from '@/lib/landing-content'

/**
 * The page footer.
 *
 * No links: there is no privacy policy or terms page to point at yet, and a footer link to
 * nowhere is worse than no link. Added when the auth forms start collecting something.
 * See design/features/landing-page-engagement.md section 11.
 */
export const LandingFooter = () => (
  <footer className="bg-forest-green-deep">
    <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-6 py-10 text-center sm:flex-row sm:justify-between sm:text-left">
      <Logo variant="onForestGreen" width={56} className="rounded-control" />

      <p className="font-sans text-sm text-sage-green">{FOOTER.rights}</p>
    </div>
  </footer>
)

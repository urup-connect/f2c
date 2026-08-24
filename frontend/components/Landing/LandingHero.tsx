import { Logo } from '@/components/Brand/Logo'
import { ButtonLink } from '@/components/Ui/ButtonLink'
import { HERO } from '@/lib/landing-content'

/**
 * The public front door.
 *
 * Sized with `min-h` rather than `h-screen`, so the hero cannot clip its own content at 200%
 * zoom or in a short landscape viewport.
 *
 * The club's name stays inside the level-one heading as text while the tagline carries the page
 * visually, so the name is never left to the badge alone.
 * See design/features/landing-page-engagement.md criteria 1, 7 and 8.
 *
 * Sign Up points at `/join`, not `/signup`: arriving from here is a decision to begin, so the
 * age gate is always asked again and any earlier answer is discarded. See `app/(auth)/join`.
 */
export const LandingHero = () => (
  <section
    aria-labelledby="hero-heading"
    className="flex min-h-[85svh] items-center bg-forest-green-deep"
  >
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center gap-8 px-6 py-20 text-center">
      <Logo variant="onForestGreen" width={132} loading="eager" className="rounded-card" />

      <h1 id="hero-heading" className="flex flex-col gap-5">
        <span className="font-sans text-xs font-medium uppercase tracking-label text-sage-green sm:text-sm">
          {HERO.eyebrow}
        </span>
        <span className="font-display text-4xl leading-tight tracking-display text-cream-warm sm:text-5xl lg:text-6xl">
          {HERO.tagline}
        </span>
      </h1>

      <p className="max-w-xl text-base leading-relaxed text-sage-green sm:text-lg">
        {HERO.proposition}
      </p>

      <div className="flex w-full flex-col gap-4 sm:w-auto sm:flex-row">
        <ButtonLink href="/join" ground="green">
          {HERO.signUp}
        </ButtonLink>
        <ButtonLink href="/login" ground="green" tone="secondary">
          {HERO.logIn}
        </ButtonLink>
      </div>
    </div>
  </section>
)

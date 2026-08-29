import { ButtonLink } from '@/components/Ui/ButtonLink'
import { LANDING } from '@/lib/landing-content'

/**
 * The top of the front door.
 *
 * Leaf green, full width, with both controls on it — so the first thing a visitor sees is what this is
 * and the two things they can do about it. **Creating an account comes first and signing in second**,
 * which is the opposite of the club's hero: the club is a members' club whose visitors mostly have an
 * account, and a store's mostly do not.
 *
 * The kicker is a `p` rather than a heading. It reads as one line above the title but it is not a
 * level in the document outline, and marking it as one would put a rung on the ladder that leads
 * nowhere.
 */
export const Hero = () => (
  <section className="bg-leaf">
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-20">
      <p className="font-sans text-sm uppercase tracking-label text-leaf-pale">
        {LANDING.hero.kicker}
      </p>

      <h1 className="max-w-3xl font-display text-4xl leading-tight tracking-display text-paper sm:text-5xl">
        {LANDING.hero.heading}
      </h1>

      <p className="max-w-2xl font-sans text-lg leading-relaxed text-leaf-pale">
        {LANDING.hero.standfirst}
      </p>

      <div className="mt-2 flex flex-wrap gap-4">
        <ButtonLink href="/sign-up" ground="leaf">
          {LANDING.hero.primary}
        </ButtonLink>
        <ButtonLink href="/sign-in" ground="leaf" tone="secondary">
          {LANDING.hero.secondary}
        </ButtonLink>
      </div>
    </div>
  </section>
)

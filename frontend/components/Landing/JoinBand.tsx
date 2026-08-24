import { ButtonLink } from '@/components/Ui/ButtonLink'
import { JOIN } from '@/lib/landing-content'

/**
 * The closing call to action.
 *
 * Repeats both ways in for a reader who has scrolled the whole page, and says plainly that the
 * club is not yet open — sign-up cannot work until the access mechanism is decided, and a
 * better page only sends more people at that door.
 * See design/features/landing-page-engagement.md criterion 13 and risk 5.
 *
 * Sign Up points at `/join` for the same reason it does in the hero: a fresh age check every
 * time, whichever of the two buttons a reader reaches. See `app/(auth)/join`.
 */
export const JoinBand = () => (
  <section aria-labelledby="join-heading" className="bg-forest-green">
    <div className="mx-auto flex max-w-3xl flex-col items-center gap-6 px-6 py-20 text-center">
      <h2
        id="join-heading"
        className="font-display text-3xl tracking-display text-cream-warm sm:text-4xl"
      >
        {JOIN.heading}
      </h2>

      <p className="text-base leading-relaxed text-sage-green sm:text-lg">{JOIN.body}</p>

      <div className="flex w-full flex-col gap-4 sm:w-auto sm:flex-row">
        <ButtonLink href="/join" ground="green">
          {JOIN.signUp}
        </ButtonLink>
        <ButtonLink href="/login" ground="green" tone="secondary">
          {JOIN.logIn}
        </ButtonLink>
      </div>

      <p className="text-sm text-sage-green">{JOIN.note}</p>
    </div>
  </section>
)

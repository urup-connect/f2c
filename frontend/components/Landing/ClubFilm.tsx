import { BRAND_FILM, brandFilmPoster, brandFilmSource } from '@/lib/brand-film'
import { FILM } from '@/lib/landing-content'
import { SITE_CONFIG } from '@/lib/site'

/**
 * The club film.
 *
 * Nothing plays on its own. The film runs a minute, carries a soundtrack, and anything that
 * started by itself would need a pause control to satisfy WCAG 2.2.2 — the same reasoning that
 * keeps the strapline ribbon static. `controls` and a reader who chooses to press play cost
 * nothing and ask nobody to stop anything.
 * See design/features/landing.md sections 3 and 5.
 *
 * `preload="metadata"` fetches the header rather than the file. At seven megabytes, preloading
 * the whole thing would be most of the page's weight spent on something most readers never play,
 * and this is a South African audience on metered mobile data more often than not. The file is
 * laid out for streaming — its `moov` atom is 68 KB at the front rather than behind the media —
 * so the header costs one cheap range request and the reader gets a real duration in the scrubber
 * before deciding to spend the rest.
 *
 * The poster is what fills the box until then, so nothing here waits on the film to look finished.
 *
 * The film is labelled by the section heading rather than by an `aria-label` of its own, so the
 * name a screen reader announces is a line the compliance tests already hold.
 */

/*
 * The reserved box, from the manifest's own dimensions. Stated as a ratio rather than a height:
 * the film is a fixed 16:9 and the box is fluid, so the ratio is the thing that stays true.
 */
const FILM_ASPECT = `${BRAND_FILM.width} / ${BRAND_FILM.height}`

export const ClubFilm = () => (
  <section aria-labelledby="film-heading" className="bg-forest-green-deep">
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-20">
      <h2
        id="film-heading"
        className="font-display text-3xl tracking-display text-cream-warm sm:text-4xl"
      >
        {FILM.heading}
      </h2>

      <p className="max-w-2xl text-base leading-relaxed text-sage-green sm:text-lg">{FILM.body}</p>

      {/* The box holds the ratio and the film fills it, so the page does not reflow when the
          metadata arrives. The ink ground sits behind the poster, covering the moment before it
          loads and the letterbox edge where the still is a pixel off the film's own ratio. */}
      <div
        className="w-full overflow-hidden rounded-card bg-ink"
        style={{ aspectRatio: FILM_ASPECT }}
      >
        <video
          aria-labelledby="film-heading"
          className="h-full w-full"
          controls
          height={BRAND_FILM.height}
          playsInline
          poster={brandFilmPoster(SITE_CONFIG)}
          preload="metadata"
          src={brandFilmSource(SITE_CONFIG)}
          width={BRAND_FILM.width}
        />
      </div>
    </div>
  </section>
)

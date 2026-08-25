import { WHY_JOIN } from '@/lib/landing-content'

/**
 * What the club is, and what membership gives a member.
 *
 * One section rather than two: the benefits only mean anything after the paragraph that says
 * what the collective is, and a reader jumping between landmarks is better served by one
 * destination than by two that only make sense together.
 * See design/features/landing.md sections 2 and 4.
 *
 * The benefits are a list, marked up as one, so a screen reader announces how many there are
 * before reading the first.
 */
export const WhyJoin = () => (
  <section aria-labelledby="why-join-heading" className="bg-surface-muted">
    <div className="mx-auto flex max-w-4xl flex-col gap-10 px-6 py-20">
      <div className="flex flex-col gap-5">
        <h2
          id="why-join-heading"
          className="font-display text-3xl tracking-display text-forest-green sm:text-4xl"
        >
          {WHY_JOIN.heading}
        </h2>

        <p className="max-w-2xl text-base leading-relaxed text-foreground sm:text-lg">
          {WHY_JOIN.body}
        </p>
      </div>

      <div className="flex flex-col gap-5 border-t border-border pt-10">
        <h3 className="font-display text-xl text-forest-green sm:text-2xl">
          {WHY_JOIN.benefitsHeading}
        </h3>

        {/* A block list rather than a flex column: an `li` blockified by a flex parent loses its
            marker in some browsers, and the marker is what makes this read as a list on screen
            as well as to assistive technology. */}
        <ul className="max-w-2xl list-disc space-y-3 pl-5 text-base leading-relaxed text-foreground marker:text-olive-green sm:text-lg">
          {WHY_JOIN.benefits.map((benefit) => (
            <li key={benefit}>{benefit}</li>
          ))}
        </ul>
      </div>
    </div>
  </section>
)

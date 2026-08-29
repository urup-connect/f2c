import { LEGAL } from '@/lib/landing-content'

/**
 * The ground the club operates on, stated before the closing call to action rather than after
 * it, so a reader has it before they decide.
 *
 * Says nothing about who may join. That is the age gate's alone — it is the one surface exempt
 * from `ELIGIBILITY_CLAIM`, and a second exemption would empty the rule out. The first point
 * describes the check the product performs instead of the threshold it applies.
 * See design/features/landing.md section 4.
 *
 * This is a summary, not the club's terms. There is no terms page to link to yet; when there is,
 * it belongs here and in the footer. See design/features/landing.md risk 5.
 */
export const LegalNotice = () => (
  <section aria-labelledby="legal-heading" className="bg-background">
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-20">
      <h2
        id="legal-heading"
        className="font-display text-3xl tracking-display text-forest-green sm:text-4xl"
      >
        {LEGAL.heading}
      </h2>

      <ul className="max-w-2xl list-disc space-y-3 pl-5 text-base leading-relaxed text-foreground marker:text-olive-green sm:text-lg">
        {LEGAL.points.map((point) => (
          <li key={point}>{point}</li>
        ))}
      </ul>
    </div>
  </section>
)

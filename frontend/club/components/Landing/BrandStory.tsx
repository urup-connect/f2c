import { BrandImage } from '@/components/Brand/BrandImage'
import { STORY } from '@/lib/landing-content'
import { StoryStep } from './StoryStep'

/**
 * The box the section's main photograph is drawn into.
 *
 * The width is the manifest ceiling for `leafCanopy`, which is what keeps it above 2x. The
 * height is stated rather than derived: 1076x717 does not scale to a whole number of pixels at
 * this width, and a reserved box that is half a pixel out is a box the browser disagrees with.
 * See design/features/landing-page-engagement.md section 6.2.
 */
const STORY_IMAGE_WIDTH = 520
const STORY_IMAGE_HEIGHT = 347

/**
 * What the emblem means, and the three steps behind it.
 *
 * The photographs illustrate rather than inform: the section reads in full without them, which
 * matters because their licence for web use is not confirmed.
 * See design/features/landing-page-engagement.md criterion 12 and risk 1.
 */
export const BrandStory = () => (
  <section aria-labelledby="story-heading" className="bg-surface-muted">
    <div className="mx-auto flex max-w-6xl flex-col gap-14 px-6 py-20">
      <div className="flex flex-col gap-10 lg:flex-row lg:items-center lg:gap-16">
        <div className="flex flex-col gap-5 lg:flex-1">
          <h2
            id="story-heading"
            className="font-display text-3xl tracking-display text-forest-green sm:text-4xl"
          >
            {STORY.heading}
          </h2>

          {STORY.paragraphs.map((paragraph) => (
            <p key={paragraph} className="text-base leading-relaxed text-foreground sm:text-lg">
              {paragraph}
            </p>
          ))}
        </div>

        {/* The box carries the aspect ratio and the image fills it. `h-auto` would not do:
            once the file has loaded, a replaced element with an automatic height takes its
            intrinsic ratio back and ignores the declared one, which is half a pixel out here. */}
        <div className="aspect-[520/347] w-full max-w-[520px] shrink-0 self-center">
          <BrandImage
            imageKey={STORY.imageKey}
            width={STORY_IMAGE_WIDTH}
            height={STORY_IMAGE_HEIGHT}
            className="h-full w-full rounded-card object-cover"
          />
        </div>
      </div>

      {/* Capped narrower than the section: the step photographs can only be thumbnails, and
          three of them spread across a full-width row reads as empty space. */}
      <ol className="grid max-w-3xl gap-8 border-t border-border pt-12 sm:grid-cols-3">
        {STORY.steps.map((step) => (
          <StoryStep
            key={step.label}
            imageKey={step.imageKey}
            label={step.label}
            description={step.description}
          />
        ))}
      </ol>
    </div>
  </section>
)

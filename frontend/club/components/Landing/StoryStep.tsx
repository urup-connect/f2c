import { BrandImage } from '@/components/Brand/BrandImage'
import type { BrandImageKey } from '@/lib/brand'

type StoryStepProps = {
  imageKey: BrandImageKey
  label: string
  description: string
}

/**
 * The width every step photograph is drawn at.
 *
 * Uniform across the three steps so their labels sit on one line, and kept in step with the
 * `w-[140px]` box below. It is at or below every step image's ceiling in the imagery manifest,
 * which is what keeps each file above 2x — the smallest of them, at 288 pixels wide, is the one
 * that sets this number.
 * See design/features/landing-page-engagement.md sections 6.2 and 6.4.
 */
export const STEP_IMAGE_WIDTH = 140
export const STEP_IMAGE_HEIGHT = 105

/**
 * One step in the club's story.
 *
 * The photographs are the guidelines deck's own, and three of the four can only ever be
 * thumbnails, so the step is designed around a thumbnail rather than fighting it. The fixed box
 * crops each one to a common shape instead of letting three different aspect ratios push the
 * labels out of line.
 */
export const StoryStep = ({ imageKey, label, description }: StoryStepProps) => (
  <li className="flex flex-col gap-4">
    <div className="h-[105px] w-[140px] overflow-hidden rounded-card">
      <BrandImage
        imageKey={imageKey}
        width={STEP_IMAGE_WIDTH}
        height={STEP_IMAGE_HEIGHT}
        className="h-full w-full object-cover"
      />
    </div>

    <div className="flex flex-col gap-1.5">
      <h3 className="font-display text-lg text-forest-green">{label}</h3>
      <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">{description}</p>
    </div>
  </li>
)

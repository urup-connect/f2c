import { Fragment } from 'react'
import { STRAPLINE_SEGMENTS } from '@/lib/landing-content'

/**
 * The strapline the guidelines deck repeats along the foot of every slide.
 *
 * Static. A scrolling marquee would need a pause control to satisfy WCAG 2.2.2, and
 * hover-to-pause serves neither a keyboard nor a screen reader user.
 * See design/features/landing-page-engagement.md section 6.6.
 *
 * The separators are hidden from assistive technology so the strapline is announced as three
 * phrases rather than as punctuation.
 */
export const StraplineRibbon = () => (
  <div className="bg-sage-green">
    <p className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-4 gap-y-1 px-6 py-4 text-center font-sans text-xs font-medium uppercase tracking-label text-forest-green sm:text-sm">
      {STRAPLINE_SEGMENTS.map((segment, index) => (
        <Fragment key={segment}>
          {index > 0 && <span aria-hidden="true">&bull;</span>}
          <span>{segment}</span>
        </Fragment>
      ))}
    </p>
  </div>
)

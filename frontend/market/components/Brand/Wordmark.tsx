import { Mark } from '@/components/Brand/Mark'
import { STORE_BRAND } from '@/lib/brand'

type WordmarkProps = {
  /** The ground it sits on. Decides the palette and nothing else. */
  ground?: 'paper' | 'leaf'
  /** `full` spells the name. `short` is the mark alone, for a bar or a badge. */
  form?: 'full' | 'short'
}

/*
 * The mark is four fixed brand colours, three of which vanish on the green header, so on that
 * ground it keeps a cream tile under it. That is the logo's own construction rather than an
 * invention: every version of it that exists sits on cream.
 */
const TONES = {
  paper: { tile: '', name: 'text-leaf' },
  leaf: { tile: 'rounded-control bg-paper px-2 py-1.5', name: 'text-paper' },
} as const

/**
 * The store's name: the logo, and the name in text beside it.
 *
 * The mark is `aria-hidden` and the name carries the accessible text, so a screen reader hears
 * "Farm to Consumer" once rather than "F 2 C Farm to Consumer" - and it hears it even in `short`
 * form, where the name is present but visually hidden. "F 2 C" read out is not the name of
 * anything.
 */
export const Wordmark = ({ ground = 'paper', form = 'full' }: WordmarkProps) => {
  const tone = TONES[ground]

  return (
    <span className="inline-flex items-center gap-2">
      <span className={`inline-flex items-center ${tone.tile}`}>
        {/* Height only: the viewBox supplies the aspect ratio, so the width follows the logo's. */}
        <Mark className="h-8 w-auto" />
      </span>

      <span
        className={
          form === 'full'
            ? `font-display text-lg tracking-display ${tone.name}`
            : 'sr-only'
        }
      >
        {STORE_BRAND.name}
      </span>
    </span>
  )
}

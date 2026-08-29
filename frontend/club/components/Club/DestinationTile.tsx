import Link from 'next/link'
import { DESTINATIONS } from '@/lib/club-content'
import type { ClubDestination } from '@/lib/club-navigation'

type DestinationTileProps = {
  destination: ClubDestination
}

const TILE = 'flex h-full flex-col gap-1 rounded-control border-2 p-4 text-left'

/**
 * One thing this account may do, whether or not it exists yet.
 *
 * **A planned destination is not a link.** It renders as a `div` with no interactive role at all,
 * rather than a disabled button or an anchor to `#`: a control that looks operable and does nothing
 * costs a member a click and a screen-reader user considerably more, and an anchor to a route that
 * answers 404 is worse than both. What it does carry is the badge, and an `aria-describedby`
 * pointing at a full sentence — "Not built yet" alone is too terse to be read out of context.
 *
 * The tiles exist at all because the roles catalogue describes far more than the platform has
 * built. Showing what the club intends a cultivator to be able to do is worth more than an empty
 * page, and it puts the eventual screen's own name in front of whoever builds it. See
 * design/features/roles-and-permissions.md section 13.
 */
export const DestinationTile = ({ destination }: DestinationTileProps) => {
  const body = (
    <>
      <span className="font-sans text-base font-medium text-forest-green">
        {destination.label}
      </span>
      <span className="font-sans text-sm leading-relaxed text-muted-foreground">
        {destination.description}
      </span>
    </>
  )

  if (destination.state === 'ready' && destination.href !== null) {
    return (
      <Link
        href={destination.href}
        className={`${TILE} border-border bg-surface transition-colors hover:border-olive-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green`}
      >
        {body}
      </Link>
    )
  }

  const noticeId = `destination-${destination.key}-planned`

  return (
    <div
      aria-describedby={noticeId}
      className={`${TILE} border-dashed border-border bg-surface-muted`}
    >
      {body}

      <span className="mt-2 inline-flex w-fit rounded-pill bg-sage-green px-3 py-0.5 font-sans text-xs uppercase tracking-label text-forest-green">
        {DESTINATIONS.planned}
      </span>

      {/* The badge in full, for anyone who reaches it without seeing where it sits. */}
      <span id={noticeId} className="sr-only">
        {DESTINATIONS.plannedDescription}
      </span>
    </div>
  )
}

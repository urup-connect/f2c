import Link from 'next/link'

import type { AccountDestination } from '@/lib/navigation'

type DestinationTileProps = {
  destination: AccountDestination
}

/** What a planned tile says, and the full sentence behind the badge. */
export const PLANNED_BADGE = 'Not built yet'
export const PLANNED_DESCRIPTION =
  'This is described but not built yet, so there is nowhere to go from here.'

const TILE = 'flex h-full flex-col gap-1 rounded-control border-2 p-4 text-left'

/**
 * One thing this account may do, whether or not it exists yet.
 *
 * **A planned destination is not a link.** It renders as a `div` with no interactive role at all,
 * rather than a disabled button or an anchor to `#`: a control that looks operable and does nothing
 * costs a sighted person a click and a screen-reader user considerably more, and an anchor to a route
 * that answers 404 is worse than both. What it does carry is the badge, and an `aria-describedby`
 * pointing at a full sentence — "Not built yet" alone is too terse to be read out of context.
 *
 * The copy for the badge lives here rather than in `store-content.ts`, which is the one place this
 * application departs from that rule: the two strings are about the state of the *build* rather than
 * about the store, and the day nothing is planned any more they are deleted with this branch.
 */
export const DestinationTile = ({ destination }: DestinationTileProps) => {
  const body = (
    <>
      <span className="font-sans text-base font-medium text-leaf">{destination.title}</span>
      <span className="font-sans text-sm leading-relaxed text-muted-foreground">
        {destination.description}
      </span>
    </>
  )

  if (destination.state === 'ready' && destination.href !== null) {
    return (
      <Link
        href={destination.href}
        className={`${TILE} border-border bg-surface transition-colors hover:border-leaf-bright focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf`}
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

      <span className="mt-2 inline-flex w-fit rounded-pill bg-leaf-pale px-3 py-0.5 font-sans text-xs uppercase tracking-label text-leaf">
        {PLANNED_BADGE}
      </span>

      {/* The badge in full, for anyone who reaches it without seeing where it sits. */}
      <span id={noticeId} className="sr-only">
        {PLANNED_DESCRIPTION}
      </span>
    </div>
  )
}

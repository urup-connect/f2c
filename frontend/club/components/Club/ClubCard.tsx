import type { ReactNode } from 'react'

type ClubCardProps = {
  heading: string
  /** A line under the heading, when the card needs explaining before it is read. */
  standfirst?: string
  /** A line under the contents, for something true about the card rather than about its data. */
  note?: string
  children: ReactNode
}

/**
 * The id a card's heading is given, so the region can point at it.
 *
 * Derived from the heading rather than counted or generated: this renders on the server and is
 * never hydrated, so a generated id would be one more thing that could differ between two renders
 * of the same page for no benefit. Two cards sharing a heading on one screen would collide, and
 * that is a content mistake worth failing on rather than papering over.
 */
export const cardHeadingId = (heading: string): string =>
  `club-${heading.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`

/**
 * One card on a signed-in screen.
 *
 * A `section` with its heading named through `aria-labelledby`, so a screen reader's landmark list
 * reads as the page's own contents rather than as a run of unlabelled regions. That wiring is the
 * reason this is a component rather than a `div` with a class: it is easy to leave out and
 * impossible to notice with a mouse.
 *
 * `AuthCard` is its signed-out counterpart and is deliberately separate — that one centres a single
 * card in a viewport, this one is a tile in a column of them.
 */
export const ClubCard = ({ heading, standfirst, note, children }: ClubCardProps) => {
  const id = cardHeadingId(heading)

  return (
    <section aria-labelledby={id} className="rounded-card bg-surface p-6 shadow-sm sm:p-8">
      <h2 id={id} className="font-display text-2xl tracking-display text-forest-green">
        {heading}
      </h2>

      {standfirst ? (
        <p className="mt-2 font-sans text-sm leading-relaxed text-muted-foreground">
          {standfirst}
        </p>
      ) : null}

      <div className="mt-6">{children}</div>

      {note ? (
        <p className="mt-6 font-sans text-sm leading-relaxed text-muted-foreground">{note}</p>
      ) : null}
    </section>
  )
}

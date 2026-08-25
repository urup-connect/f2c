import type { DetailRow } from '@/lib/club-account'
import { DETAILS_CARD } from '@/lib/club-content'

type DetailListProps = {
  rows: readonly DetailRow[]
}

/**
 * What the club holds about this account, as labelled lines.
 *
 * A description list, because that is what this is: each line is a term and its value, and a
 * screen reader announces the pair. A table would claim a relationship between rows that does not
 * exist, and a run of paragraphs would lose the pairing altogether.
 *
 * A value the club does not hold is **said to be absent** rather than left blank. An empty line
 * reads as a page that failed to draw; "Not on file" reads as a fact, which is what it is. The
 * absent value is also given a muted, italic treatment so the two are distinguishable at a glance
 * and not only by reading.
 */
export const DetailList = ({ rows }: DetailListProps) => (
  <dl className="grid gap-4 sm:grid-cols-2">
    {rows.map((row) => (
      <div key={row.key} className="flex flex-col gap-1">
        <dt className="font-sans text-xs uppercase tracking-label text-muted-foreground">
          {row.label}
        </dt>
        <dd
          className={
            row.value === null
              ? 'font-sans text-base italic text-muted-foreground'
              : 'font-sans text-base text-foreground'
          }
        >
          {row.value ?? DETAILS_CARD.blank}
        </dd>
      </div>
    ))}
  </dl>
)

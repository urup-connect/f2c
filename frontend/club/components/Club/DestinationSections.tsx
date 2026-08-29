import { DESTINATIONS } from '@/lib/club-content'
import type { ClubSectionContent } from '@/lib/club-navigation'
import { ClubCard } from './ClubCard'
import { DestinationTile } from './DestinationTile'

type DestinationSectionsProps = {
  sections: readonly ClubSectionContent[]
}

/**
 * Everything this account may do, banded by subject.
 *
 * One component for all three homes, because there is nothing role-specific about it: the bands
 * come from the account's permissions, and a band nobody holds anything under has already been
 * dropped before it arrives here. A member sees plants, the swap zone and their account; an
 * administrator sees the collective's records. Neither page knows which.
 *
 * The whole lot sits inside one card with one `h2`, and each band takes an `h3`. The alternative —
 * a card per band — put six headings of equal weight on an administrator's screen and made the
 * page read as six unrelated things rather than one list of what they may do.
 */
export const DestinationSections = ({ sections }: DestinationSectionsProps) => (
  <ClubCard heading={DESTINATIONS.heading}>
    {sections.length === 0 ? (
      <p className="font-sans text-base text-muted-foreground">{DESTINATIONS.empty}</p>
    ) : (
      <div className="flex flex-col gap-8">
        {sections.map((band) => (
          <div key={band.section}>
            <h3 className="font-sans text-xs uppercase tracking-label text-muted-foreground">
              {band.heading}
            </h3>

            <ul className="mt-3 grid list-none gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {band.destinations.map((destination) => (
                <li key={destination.key}>
                  <DestinationTile destination={destination} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    )}
  </ClubCard>
)

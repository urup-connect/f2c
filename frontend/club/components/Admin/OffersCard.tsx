import { ClubCard } from '@/components/Club/ClubCard'
import { LISTING_STATUSES, labelFor, type StrainListing } from '@/lib/strain-catalogue'
import { OFFERS_CARD } from '@/lib/strain-catalogue-content'

type OffersCardProps = {
  listings: readonly StrainListing[]
}

const HEAD = 'px-3 py-2 text-left font-sans text-xs uppercase tracking-label text-muted-foreground'
const CELL = 'px-3 py-3 align-top font-sans text-sm text-foreground'

/**
 * Who offers this strain, on the strain's own page. Read-only.
 *
 * The Django admin's `CultivatorStrainListingInline` in one card, and read-only
 * for the reason that inline gives: a listing's commercial terms are not
 * something to edit in passing while curating botanical facts. An administrator
 * who does need to change one has the Django admin, and Block 9's cultivator
 * screens will have it properly.
 *
 * **What the card is actually for** is the question that has to be answered
 * before a strain is retired or reserved: is anybody selling this, and does
 * anybody own a plant grown against it. The plant column is the one that
 * matters — `Plant.listing` is `PROTECT`, so any figure above zero means the
 * listing is permanent and the strain behind it is too.
 *
 * A real `table`, unlike `PairField`. This is tabular data being read rather
 * than a form being filled in, so row-and-column navigation is exactly what a
 * screen reader user wants, and `scope` on the headers is what makes it work.
 *
 * The money is rendered as the string the API sent, never parsed. `DECIMAL`
 * columns; see `lib/strain-catalogue.ts`.
 */
export const OffersCard = ({ listings }: OffersCardProps) => (
  <ClubCard heading={OFFERS_CARD.heading} standfirst={OFFERS_CARD.standfirst}>
    {listings.length === 0 ? (
      <p className="font-sans text-sm text-muted-foreground">{OFFERS_CARD.empty}</p>
    ) : (
      /*
       * The wrapper scrolls, not the page. Six columns on a phone is wider than
       * the viewport, and a page that scrolls sideways as a whole loses the
       * header and the navigation with it.
       */
      <div className="overflow-x-auto">
        <table className="w-full min-w-[44rem] border-collapse">
          <thead>
            <tr className="border-b-2 border-border">
              <th scope="col" className={HEAD}>
                {OFFERS_CARD.columnCultivator}
              </th>
              <th scope="col" className={HEAD}>
                {OFFERS_CARD.columnStatus}
              </th>
              <th scope="col" className={HEAD}>
                {OFFERS_CARD.columnPrice}
              </th>
              <th scope="col" className={HEAD}>
                {OFFERS_CARD.columnYield}
              </th>
              <th scope="col" className={HEAD}>
                {OFFERS_CARD.columnTypes}
              </th>
              <th scope="col" className={HEAD}>
                {OFFERS_CARD.columnPlants}
              </th>
            </tr>
          </thead>

          <tbody>
            {listings.map((listing) => (
              <tr key={listing.id} className="border-b border-border last:border-b-0">
                {/*
                  * `scope="row"`: the cultivator's name is what identifies the
                  * row, so a screen reader announces it with each cell that
                  * follows rather than reading six unattributed values.
                  */}
                <th scope="row" className={`${CELL} font-medium`}>
                  {listing.cultivator}
                </th>

                <td className={CELL}>{labelFor(LISTING_STATUSES, listing.status)}</td>

                <td className={`${CELL} tabular-nums`}>{listing.default_grow_price}</td>

                <td className={`${CELL} tabular-nums`}>
                  {listing.minimum_yield_grams}
                  {OFFERS_CARD.yieldUnit}
                </td>

                <td className={CELL}>
                  {listing.finished_product_types.length === 0 ? (
                    <span className="italic text-muted-foreground">
                      {OFFERS_CARD.noTypes}
                    </span>
                  ) : (
                    listing.finished_product_types.join(', ')
                  )}
                </td>

                <td className={`${CELL} tabular-nums`}>{listing.plant_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </ClubCard>
)

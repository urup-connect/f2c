import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { OFFERS_CARD } from '@/lib/strain-catalogue-content'
import type { StrainListing } from '@/lib/strain-catalogue'
import { OffersCard } from './OffersCard'

/*
 * Who offers this strain. Read-only, and the tests say so in two ways.
 *
 * The substantive assertions are about **the money and the plant count**. The
 * money must be rendered as the string the API sent, because these are DECIMAL
 * columns and a number that went through a float would disagree with the
 * database. The plant count must be visible, because `Plant.listing` is PROTECT
 * -- any figure above zero means the listing is permanent, and an administrator
 * about to retire the strain should be told before rather than after.
 */

const listing = (overrides: Partial<StrainListing> = {}): StrainListing => ({
  id: 'listing-1',
  cultivator: 'Kloof',
  status: 'listed',
  default_grow_price: '950.00',
  minimum_yield_grams: '30.00',
  short_description: 'Grown slow, under glass.',
  finished_product_types: ['Pre-rolls'],
  plant_count: 0,
  updated_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

describe('with no offers', () => {
  test('says so rather than drawing an empty table', () => {
    render(<OffersCard listings={[]} />)

    expect(screen.getByText(OFFERS_CARD.empty)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})

describe('with offers', () => {
  test('draws a real table, so it can be navigated by row and column', () => {
    render(<OffersCard listings={[listing()]} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
  })

  test('labels every column', () => {
    render(<OffersCard listings={[listing()]} />)

    for (const label of [
      OFFERS_CARD.columnCultivator,
      OFFERS_CARD.columnStatus,
      OFFERS_CARD.columnPrice,
      OFFERS_CARD.columnYield,
      OFFERS_CARD.columnTypes,
      OFFERS_CARD.columnPlants,
    ]) {
      expect(screen.getByRole('columnheader', { name: label })).toBeInTheDocument()
    }
  })

  test('makes the cultivator the row header', () => {
    // So a screen reader announces the grower's name with each cell that follows
    // rather than reading six unattributed values.
    render(<OffersCard listings={[listing()]} />)

    expect(screen.getByRole('rowheader', { name: 'Kloof' })).toBeInTheDocument()
  })

  test('names the cultivator by display name', () => {
    // Section 6.6 of `roles-and-permissions.md`: never a legal name or an email
    // address, in any payload -- and a table cell is no different.
    render(<OffersCard listings={[listing({ cultivator: 'Kloof' })]} />)

    expect(screen.getByText('Kloof')).toBeInTheDocument()
  })

  test('shows the price exactly as the API sent it', () => {
    // A DECIMAL column. `Number('12.35')` is not 12.35, so nothing here parses.
    render(<OffersCard listings={[listing({ default_grow_price: '1250.05' })]} />)

    expect(screen.getByText('1250.05')).toBeInTheDocument()
  })

  test('shows the yield with its unit', () => {
    // Grams, because that is the unit the statutory limits and the courier both
    // use -- and a bare number in a table is a number nobody can act on.
    render(<OffersCard listings={[listing({ minimum_yield_grams: '30.00' })]} />)

    expect(screen.getByText(`30.00${OFFERS_CARD.yieldUnit}`)).toBeInTheDocument()
  })

  test('shows the plant count', () => {
    render(<OffersCard listings={[listing({ plant_count: 4 })]} />)

    expect(screen.getByText('4')).toBeInTheDocument()
  })

  test('translates the listing status into words', () => {
    render(<OffersCard listings={[listing({ status: 'withdrawn' })]} />)

    expect(screen.getByText('Withdrawn')).toBeInTheDocument()
  })

  test('falls back to the raw status this build does not know', () => {
    // A value the API has and this bundle does not. A blank cell would read as a
    // listing with no status at all.
    render(<OffersCard listings={[listing({ status: 'embargoed' })]} />)

    expect(screen.getByText('embargoed')).toBeInTheDocument()
  })

  test('lists the product types', () => {
    render(
      <OffersCard
        listings={[listing({ finished_product_types: ['Pre-rolls', 'Loose'] })]}
      />,
    )

    expect(screen.getByText('Pre-rolls, Loose')).toBeInTheDocument()
  })

  test('says when an offer has no product types', () => {
    // The failure this column exists to make visible: a listed offer with none
    // means the member buys a plant and has nothing to choose at harvest.
    render(<OffersCard listings={[listing({ finished_product_types: [] })]} />)

    expect(screen.getByText(OFFERS_CARD.noTypes)).toBeInTheDocument()
  })

  test('draws a row per offer', () => {
    render(
      <OffersCard
        listings={[
          listing({ id: 'a', cultivator: 'Kloof' }),
          listing({ id: 'b', cultivator: 'Dale' }),
        ]}
      />,
    )

    // Two data rows plus the header row.
    expect(screen.getAllByRole('row')).toHaveLength(3)
  })
})

describe('read-only', () => {
  test('offers no control that would change anything', () => {
    // A listing's commercial terms are the grower's, not an administrator's to
    // edit in passing while curating botanical facts.
    render(<OffersCard listings={[listing()]} />)

    expect(screen.queryAllByRole('button')).toEqual([])
    expect(screen.queryAllByRole('textbox')).toEqual([])
  })

  test('says why it cannot be edited', () => {
    render(<OffersCard listings={[listing()]} />)

    expect(screen.getByText(OFFERS_CARD.standfirst)).toBeInTheDocument()
  })
})

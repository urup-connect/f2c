import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { RETIRE_CARD } from '@/lib/strain-catalogue-content'
import type { Strain, StrainListing } from '@/lib/strain-catalogue'
import { RetireCard } from './RetireCard'

/*
 * Retirement: what stands in for a delete.
 *
 * `retireStrain` is mocked. What is under test is what the card does with each
 * outcome and what it says before acting -- not the fetch, which
 * `lib/strain-catalogue-api.ts` owns.
 *
 * The assertions cluster on two properties.
 *
 * **Nothing happens on one click.** The act is reversible, but its blast radius
 * is invisible from the button: one click can take several growers' offers off
 * the shelf, and an administrator tidying up a duplicate entry has no way to know
 * that from the strain's own row. So the confirmation exists to state the
 * numbers, and it must state them.
 *
 * **A refusal never leaves the card looking as though it worked.** The worst
 * outcome here is an administrator walking away believing a strain is retired
 * when it is not, because the members' catalogue would still be offering it.
 */

const { retireStrain } = vi.hoisted(() => ({ retireStrain: vi.fn() }))

vi.mock('@/lib/strain-catalogue-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/strain-catalogue-api')>()),
  retireStrain,
}))

const listing = (overrides: Partial<StrainListing> = {}): StrainListing => ({
  id: 'listing-1',
  cultivator: 'Kloof',
  status: 'listed',
  default_grow_price: '950.00',
  minimum_yield_grams: '30.00',
  short_description: '',
  finished_product_types: [],
  plant_count: 0,
  updated_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

const strain = (overrides: Partial<Strain> = {}): Strain => ({
  id: 'strain-1',
  name: 'OG Kush',
  slug: 'og-kush',
  status: 'active',
  strain_type: 'hybrid',
  exclusive_to: null,
  reserved_to: null,
  genetic_lineage: '',
  breeder_origin: '',
  description: '',
  thc_content: null,
  cbd_content: null,
  other_cannabinoids: {},
  terpene_profile: {},
  disease_resistance: {},
  aromas: [],
  effects: [],
  flowering_time_weeks: null,
  preferred_growing_environment: '',
  difficulty_level: '',
  listings: [],
  created_at: '2026-08-01T09:00:00Z',
  updated_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

const setup = (subject = strain()) => {
  const onRetired = vi.fn()
  render(<RetireCard strain={subject} onRetired={onRetired} />)
  return { onRetired }
}

beforeEach(() => {
  retireStrain.mockReset()
})

describe('before anything is pressed', () => {
  test('offers the action and calls nothing', () => {
    setup()

    expect(screen.getByRole('button', { name: RETIRE_CARD.action })).toBeInTheDocument()
    expect(retireStrain).not.toHaveBeenCalled()
  })

  test('says outright that nothing is deleted, and why', () => {
    setup()

    expect(screen.getByText(RETIRE_CARD.standfirst)).toBeInTheDocument()
  })
})

describe('the confirmation', () => {
  test('one click confirms rather than acts', async () => {
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))

    expect(screen.getByText(RETIRE_CARD.confirmHeading)).toBeInTheDocument()
    expect(retireStrain).not.toHaveBeenCalled()
  })

  test('states how many live offers come off the shelf', async () => {
    setup(
      strain({
        listings: [
          listing({ id: 'a', status: 'listed' }),
          listing({ id: 'b', status: 'listed' }),
          listing({ id: 'c', status: 'withdrawn' }),
        ],
      }),
    )

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))

    // Two, not three. A withdrawn offer is already off the shelf, and saying it
    // came down would overstate the consequence.
    expect(screen.getByText(`2 ${RETIRE_CARD.offersWarning}`)).toBeInTheDocument()
  })

  test('says nothing else changes when nobody offers the strain', async () => {
    // "0 live offers come off the shelf" is a sentence somebody reads twice to
    // learn nothing.
    setup(strain({ listings: [] }))

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))

    expect(screen.getByText(RETIRE_CARD.noOffers)).toBeInTheDocument()
  })

  test('answers the question about the plants before it is asked', async () => {
    setup(strain({ listings: [listing({ plant_count: 4 })] }))

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))

    expect(screen.getByText(`4 ${RETIRE_CARD.plantsWarning}`)).toBeInTheDocument()
  })

  test('does not mention plants when there are none', async () => {
    setup(strain({ listings: [listing({ plant_count: 0 })] }))

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))

    expect(screen.queryByText(/plants are already growing/i)).not.toBeInTheDocument()
  })

  test('says how to undo it', async () => {
    // There is no undo endpoint, because the status is a field on the form above.
    // That is only obvious to whoever wrote it.
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))

    expect(screen.getByText(RETIRE_CARD.reinstate)).toBeInTheDocument()
  })

  test('offers a way out that does not act', async () => {
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmCancel }),
    )

    expect(retireStrain).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: RETIRE_CARD.action })).toBeInTheDocument()
  })
})

describe('retiring', () => {
  test('calls the endpoint once confirmed', async () => {
    retireStrain.mockResolvedValue({
      status: 'saved',
      record: { strain: strain({ status: 'inactive' }), listings_taken_down: 1 },
    })
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    await waitFor(() => expect(retireStrain).toHaveBeenCalledWith('strain-1'))
  })

  test('hands the whole record back, so the screen follows', async () => {
    // The form's status select has to change too. Handing back a flag rather than
    // the record would leave it saying Active.
    const retired = strain({ status: 'inactive' })
    retireStrain.mockResolvedValue({
      status: 'saved',
      record: { strain: retired, listings_taken_down: 0 },
    })
    const { onRetired } = setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    await waitFor(() => expect(onRetired).toHaveBeenCalledWith(retired))
  })

  test('reports that it was retired', async () => {
    retireStrain.mockResolvedValue({
      status: 'saved',
      record: { strain: strain({ status: 'inactive' }), listings_taken_down: 0 },
    })
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    expect(await screen.findByText(RETIRE_CARD.retired)).toBeInTheDocument()
  })
})

describe('when it does not work', () => {
  test('a failure says so and tells nobody it worked', async () => {
    retireStrain.mockResolvedValue({ status: 'failed', reason: 'Network down.' })
    const { onRetired } = setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    expect(await screen.findByText(RETIRE_CARD.failed)).toBeInTheDocument()
    expect(onRetired).not.toHaveBeenCalled()
  })

  test('a refusal shows what the API said', async () => {
    // Not swallowed into "could not be retired": the API's sentence is the only
    // thing that says why.
    retireStrain.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'This account may not manage the strain catalogue.' },
    })
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    expect(
      await screen.findByText('This account may not manage the strain catalogue.'),
    ).toBeInTheDocument()
  })

  test('leaves the action reachable so it can be tried again', async () => {
    retireStrain.mockResolvedValue({ status: 'failed', reason: 'Network down.' })
    setup()

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    expect(
      await screen.findByRole('button', { name: RETIRE_CARD.action }),
    ).toBeInTheDocument()
  })
})

describe('a strain that is already retired', () => {
  test('offers no action', async () => {
    setup(strain({ status: 'inactive' }))

    expect(
      screen.queryByRole('button', { name: RETIRE_CARD.action }),
    ).not.toBeInTheDocument()
  })

  test('says so, and says how to bring it back', () => {
    setup(strain({ status: 'inactive' }))

    expect(screen.getByText(RETIRE_CARD.alreadyRetired)).toBeInTheDocument()
    expect(screen.getByText(RETIRE_CARD.reinstate)).toBeInTheDocument()
  })
})

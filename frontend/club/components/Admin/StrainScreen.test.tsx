import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import {
  OFFERS_CARD,
  RETIRE_CARD,
  STRAIN_FORM,
} from '@/lib/strain-catalogue-content'
import type { Strain, Vocabularies } from '@/lib/strain-catalogue'
import { StrainScreen } from './StrainScreen'

/*
 * A strain's own screen: the form, who offers it, and how to retire it.
 *
 * The client module is mocked, because what is under test is the screen's one
 * job -- holding which record is current, and passing it to three cards that all
 * write it.
 *
 * Two properties carry most of the assertions.
 *
 * **The add screen becomes the edit screen without navigating.** Sending an
 * administrator to a different URL after a create would lose the "Saved." they
 * just earned and make a second edit a second page load. So the same component
 * grows two cards, and the second save has to be a PUT rather than a second POST
 * -- which is the bug worth a test.
 *
 * **Retiring a strain moves the form.** The status select has to follow, because
 * one owner of the record is the whole reason this component exists.
 */

const { createStrain, saveStrain, retireStrain } = vi.hoisted(() => ({
  createStrain: vi.fn(),
  saveStrain: vi.fn(),
  retireStrain: vi.fn(),
}))

vi.mock('@/lib/strain-catalogue-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/strain-catalogue-api')>()),
  createStrain,
  saveStrain,
  retireStrain,
}))

const VOCABULARIES: Vocabularies = { aromas: [], effects: [] }

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

const setup = (initial: Strain | null) => {
  render(
    <StrainScreen
      initial={initial}
      vocabularies={VOCABULARIES}
      cultivators={[]}
      catalogueHref="/admin/strains"
      termsHref="/admin/strains/terms"
    />,
  )
}

/** Fill in the two required fields, so a submit gets past `checkStrain`. */
const fillRequired = async (name: string) => {
  await userEvent.type(
    screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel }),
    name,
  )
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: STRAIN_FORM.typeLabel }),
    'sativa',
  )
}

beforeEach(() => {
  createStrain.mockReset()
  saveStrain.mockReset()
  retireStrain.mockReset()
})

describe('the add screen', () => {
  test('shows the form and neither of the other two cards', () => {
    // There are no offers against a strain that does not exist, and nothing to
    // retire. Rendering either with a placeholder would be two cards saying "not
    // yet".
    setup(null)

    expect(screen.getByRole('button', { name: STRAIN_FORM.create })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: OFFERS_CARD.heading })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: RETIRE_CARD.heading })).not.toBeInTheDocument()
  })

  test('writes through the create endpoint', async () => {
    createStrain.mockResolvedValue({ status: 'saved', record: strain() })
    setup(null)

    await fillRequired('Durban Poison')
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.create }))

    await waitFor(() => expect(createStrain).toHaveBeenCalled())
    expect(saveStrain).not.toHaveBeenCalled()
  })

  test('grows the other two cards once the strain exists', async () => {
    createStrain.mockResolvedValue({ status: 'saved', record: strain() })
    setup(null)

    await fillRequired('Durban Poison')
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.create }))

    expect(await screen.findByRole('heading', { name: OFFERS_CARD.heading })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: RETIRE_CARD.heading })).toBeInTheDocument()
  })

  test('does not navigate away, so a second edit is not a second page load', async () => {
    createStrain.mockResolvedValue({ status: 'saved', record: strain() })
    setup(null)

    await fillRequired('Durban Poison')
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.create }))

    expect(await screen.findByText(STRAIN_FORM.saved)).toBeInTheDocument()
  })

  test('a second save is a PUT rather than a second create', async () => {
    // The bug worth the test: writing to `createStrain` again would add a second
    // strain wearing the same name, which the API then refuses -- and the
    // administrator would be looking at a duplicate-name refusal for a strain
    // they had just successfully created.
    createStrain.mockResolvedValue({ status: 'saved', record: strain() })
    saveStrain.mockResolvedValue({
      status: 'saved',
      record: strain({ description: 'Edited.' }),
    })
    setup(null)

    await fillRequired('Durban Poison')
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.create }))
    await screen.findByText(STRAIN_FORM.saved)

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'Edited.',
    )
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.save }))

    await waitFor(() =>
      expect(saveStrain).toHaveBeenCalledWith('strain-1', expect.anything()),
    )
    expect(createStrain).toHaveBeenCalledTimes(1)
  })

  test('a refused create leaves the screen on the add form', async () => {
    createStrain.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'A strain with that name already exists.', fields: {} },
    })
    setup(null)

    await fillRequired('Durban Poison')
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.create }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: OFFERS_CARD.heading })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: STRAIN_FORM.create })).toBeInTheDocument()
  })
})

describe('the edit screen', () => {
  test('names the strain above the form', () => {
    setup(strain({ name: 'OG Kush' }))

    expect(screen.getByText('OG Kush')).toBeInTheDocument()
  })

  test('shows all three cards', () => {
    setup(strain())

    expect(screen.getByRole('button', { name: STRAIN_FORM.save })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: OFFERS_CARD.heading })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: RETIRE_CARD.heading })).toBeInTheDocument()
  })

  test('writes through the save endpoint, carrying the id', async () => {
    saveStrain.mockResolvedValue({
      status: 'saved',
      record: strain({ description: 'Edited.' }),
    })
    setup(strain())

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'Edited.',
    )
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.save }))

    await waitFor(() =>
      expect(saveStrain).toHaveBeenCalledWith('strain-1', expect.anything()),
    )
    expect(createStrain).not.toHaveBeenCalled()
  })

  test('the offers card follows a save', async () => {
    // One owner of the record: without it, a save would leave the offers card
    // holding the listings it was mounted with.
    saveStrain.mockResolvedValue({
      status: 'saved',
      record: strain({
        listings: [
          {
            id: 'listing-1',
            cultivator: 'Kloof',
            status: 'listed',
            default_grow_price: '950.00',
            minimum_yield_grams: '30.00',
            short_description: '',
            finished_product_types: [],
            plant_count: 0,
            updated_at: '2026-08-01T09:00:00Z',
          },
        ],
      }),
    })
    setup(strain())

    expect(screen.getByText(OFFERS_CARD.empty)).toBeInTheDocument()

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'x',
    )
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.save }))

    expect(await screen.findByRole('rowheader', { name: 'Kloof' })).toBeInTheDocument()
  })
})

describe('retiring from this screen', () => {
  test('moves the form’s status select', async () => {
    // The reason the record has one owner. Handing back a flag rather than the
    // whole strain would leave the select saying Active.
    retireStrain.mockResolvedValue({
      status: 'saved',
      record: { strain: strain({ status: 'inactive' }), listings_taken_down: 0 },
    })
    setup(strain({ status: 'active' }))

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )

    await waitFor(() =>
      expect(
        screen.getByRole('combobox', { name: STRAIN_FORM.statusLabel }),
      ).toHaveValue('inactive'),
    )
  })

  test('leaves the form usable, so the strain can be reinstated', async () => {
    retireStrain.mockResolvedValue({
      status: 'saved',
      record: { strain: strain({ status: 'inactive' }), listings_taken_down: 0 },
    })
    saveStrain.mockResolvedValue({
      status: 'saved',
      record: strain({ status: 'active' }),
    })
    setup(strain())

    await userEvent.click(screen.getByRole('button', { name: RETIRE_CARD.action }))
    await userEvent.click(
      screen.getByRole('button', { name: RETIRE_CARD.confirmAction }),
    )
    await waitFor(() => expect(retireStrain).toHaveBeenCalled())

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: STRAIN_FORM.statusLabel }),
      'active',
    )
    await userEvent.click(screen.getByRole('button', { name: STRAIN_FORM.save }))

    await waitFor(() =>
      expect(saveStrain).toHaveBeenCalledWith(
        'strain-1',
        expect.objectContaining({ status: 'active' }),
      ),
    )
  })
})

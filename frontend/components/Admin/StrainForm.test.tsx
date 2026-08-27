import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { STRAIN_FORM } from '@/lib/strain-catalogue-content'
import type { Cultivator, Strain, Vocabularies } from '@/lib/strain-catalogue'
import { StrainForm } from './StrainForm'

/*
 * The strain form, shared by the add screen and the edit screen.
 *
 * `onSubmit` is a prop rather than a mocked module, which is the whole reason the
 * component takes it: the two screens differ in which endpoint they write to, so
 * a test can supply either without mocking a client.
 *
 * The assertions cluster on three properties.
 *
 * **The save button does nothing while nothing has changed.** A button that saves
 * an identical record reports success for having done nothing, and an
 * administrator who pressed it learns nothing about whether their edit took.
 *
 * **A refusal never leaves the form looking saved.** The worst outcome is walking
 * away believing a strain was published when it was not.
 *
 * **The API's own refusals are rendered against their fields.** This is the
 * difference from `ProfileDetailsForm`: three refusals here are not answerable in
 * a browser, so they are the normal path rather than evidence of drift, and they
 * must reach the field they belong to.
 */

const VOCABULARIES: Vocabularies = {
  aromas: [
    { id: 'aroma-1', name: 'Citrus', slug: 'citrus', is_available: true, strain_count: 2 },
  ],
  effects: [
    {
      id: 'effect-1',
      name: 'Relaxing',
      slug: 'relaxing',
      is_available: true,
      strain_count: 0,
    },
  ],
}

const CULTIVATORS: readonly Cultivator[] = [{ id: 'user-7', display_name: 'Kloof' }]

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

const setup = (
  subject: Strain | null,
  outcome: unknown = { status: 'saved', record: strain() },
) => {
  const onSubmit = vi.fn().mockResolvedValue(outcome)
  const onSaved = vi.fn()

  render(
    <StrainForm
      strain={subject}
      vocabularies={VOCABULARIES}
      cultivators={CULTIVATORS}
      termsHref="/admin/strains/terms"
      catalogueHref="/admin/strains"
      onSubmit={onSubmit}
      onSaved={onSaved}
    />,
  )

  return { onSubmit, onSaved }
}

/** The submit button, whose label differs between create and edit. */
const submitButton = (creating: boolean) =>
  screen.getByRole('button', {
    name: creating ? STRAIN_FORM.create : STRAIN_FORM.save,
  })

describe('the add screen', () => {
  test('starts a strain as pending rather than active', async () => {
    // `member-roles.md`: the botanical facts are checked before the strain is
    // published. The field is on the form, so publishing in one step is still one
    // click away -- the default just is not that.
    setup(null)

    expect(
      screen.getByRole('combobox', { name: STRAIN_FORM.statusLabel }),
    ).toHaveValue('pending')
  })

  test('chooses no type, so the administrator has to', () => {
    setup(null)

    expect(screen.getByRole('combobox', { name: STRAIN_FORM.typeLabel })).toHaveValue('')
  })

  test('offers the create verb rather than the save verb', () => {
    // Two acts: one adds a row to the catalogue and the other changes one.
    setup(null)

    expect(submitButton(true)).toBeInTheDocument()
  })

  test('is submittable from the start, because everything in it is new', () => {
    setup(null)

    expect(submitButton(true)).toBeEnabled()
  })

  test('refuses a blank name without calling the API', async () => {
    const { onSubmit } = setup(null)

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: STRAIN_FORM.typeLabel }),
      'hybrid',
    )
    await userEvent.click(submitButton(true))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(await screen.findByText('A strain needs a name.')).toBeInTheDocument()
  })

  test('sends a complete submission', async () => {
    const { onSubmit } = setup(null)

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel }),
      'Durban Poison',
    )
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: STRAIN_FORM.typeLabel }),
      'sativa',
    )
    await userEvent.click(submitButton(true))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Durban Poison',
          strain_type: 'sativa',
          status: 'pending',
          exclusive_to: null,
        }),
      ),
    )
  })
})

describe('the edit screen', () => {
  test('is inert until something changes', async () => {
    // A save that stores an identical record reports success for having done
    // nothing.
    setup(strain())

    expect(submitButton(false)).toBeDisabled()
    expect(screen.getByText(STRAIN_FORM.unchanged)).toBeInTheDocument()
  })

  test('becomes live once a field changes', async () => {
    setup(strain())

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'A tall, quick sativa.',
    )

    expect(submitButton(false)).toBeEnabled()
  })

  test('a trailing empty JSON row is not a change', async () => {
    // `strainInputFrom` adds one so there is somewhere to type, and `mappingFrom`
    // drops it again. A form opened and not touched has to read as unchanged.
    setup(strain({ terpene_profile: { myrcene: 0.5 } }))

    expect(submitButton(false)).toBeDisabled()
  })

  test('loads the stored record into the fields', () => {
    setup(
      strain({
        name: 'Cheese',
        thc_content: '18.50',
        exclusive_to: 'user-7',
        flowering_time_weeks: 9,
      }),
    )

    expect(screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel })).toHaveValue(
      'Cheese',
    )
    expect(screen.getByRole('textbox', { name: STRAIN_FORM.thcLabel })).toHaveValue(
      '18.50',
    )
    expect(
      screen.getByRole('combobox', { name: STRAIN_FORM.exclusiveLabel }),
    ).toHaveValue('user-7')
    expect(
      screen.getByRole('textbox', { name: STRAIN_FORM.floweringLabel }),
    ).toHaveValue('9')
  })

  test('shows an unmeasured percentage as blank, not as zero', () => {
    // A zero would be a statement about the plant.
    setup(strain({ thc_content: null }))

    expect(screen.getByRole('textbox', { name: STRAIN_FORM.thcLabel })).toHaveValue('')
  })

  test('reports the save and says so', async () => {
    const saved = strain({ description: 'Rewritten.' })
    const { onSubmit, onSaved } = setup(strain(), { status: 'saved', record: saved })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'Rewritten.',
    )
    await userEvent.click(submitButton(false))

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSaved).toHaveBeenCalledWith(saved)
    expect(await screen.findByText(STRAIN_FORM.saved)).toBeInTheDocument()
  })

  test('is inert again after a save, against the record that was stored', async () => {
    // Not against what was typed. The service trims a name, so the form has to
    // settle on what came back.
    const { onSubmit } = setup(strain(), {
      status: 'saved',
      record: strain({ name: 'Cheese' }),
    })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel }),
      '  Cheese  ',
    )
    await userEvent.click(submitButton(false))

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    await waitFor(() => expect(submitButton(false)).toBeDisabled())
    expect(screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel })).toHaveValue(
      'Cheese',
    )
  })

  test('clears the saved message as soon as anything is retyped', async () => {
    // Leaving "Saved." on screen beside a field being edited would claim the new
    // value is stored.
    setup(strain(), { status: 'saved', record: strain() })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'One.',
    )
    await userEvent.click(submitButton(false))
    expect(await screen.findByText(STRAIN_FORM.saved)).toBeInTheDocument()

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'Two.',
    )

    expect(screen.queryByText(STRAIN_FORM.saved)).not.toBeInTheDocument()
  })
})

describe('a strain reserved to a cultivator who has left', () => {
  /*
   * `reservable_cultivators` excludes an account that has left, and
   * `Strain.exclusive_to` is PROTECT so the reservation survives them --
   * deliberately, because clearing it is what releases the strain back to the
   * club. The failure mode without the branch this tests is silent data loss:
   * the select holds an id matching no option, renders as its placeholder, and
   * the next save makes "open to all" true having never said so.
   */
  const reserved = strain({ exclusive_to: 'user-99', reserved_to: 'Departed Farm' })

  test('still shows the reservation', () => {
    setup(reserved)

    expect(
      screen.getByRole('combobox', { name: STRAIN_FORM.exclusiveLabel }),
    ).toHaveValue('user-99')
  })

  test('names them, and says they are no longer a cultivator', () => {
    setup(reserved)

    expect(
      screen.getByRole('option', {
        name: `Departed Farm ${STRAIN_FORM.exclusiveDeparted}`,
      }),
    ).toBeInTheDocument()
  })

  test('does not read as unreserved', () => {
    setup(reserved)

    expect(
      screen.getByRole('combobox', { name: STRAIN_FORM.exclusiveLabel }),
    ).not.toHaveValue('')
  })

  test('the reservation can be cleared, which is the point', async () => {
    const { onSubmit } = setup(reserved)

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: STRAIN_FORM.exclusiveLabel }),
      '',
    )
    await userEvent.click(submitButton(false))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ exclusive_to: null }),
      ),
    )
  })

  test('an offerable cultivator gets no marker', () => {
    setup(strain({ exclusive_to: 'user-7', reserved_to: 'Kloof' }))

    expect(screen.getByRole('option', { name: 'Kloof' })).toBeInTheDocument()
  })
})

describe('the browser’s own refusals', () => {
  test('a percentage that is not a number never leaves the browser', async () => {
    const { onSubmit } = setup(strain())

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.thcLabel }),
      'lots',
    )
    await userEvent.click(submitButton(false))

    expect(onSubmit).not.toHaveBeenCalled()
    expect(await screen.findByText(/has to be a number/i)).toBeInTheDocument()
  })

  test('a percentage over a hundred is refused', async () => {
    const { onSubmit } = setup(strain())

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.thcLabel }),
      '220',
    )
    await userEvent.click(submitButton(false))

    expect(onSubmit).not.toHaveBeenCalled()
  })

  test('a refused form says so at the bottom as well as at the field', async () => {
    // The field message can be off-screen on a form this long.
    setup(strain())

    await userEvent.clear(screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel }))
    await userEvent.tab()
    await userEvent.click(submitButton(false))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      STRAIN_FORM.refusedSummary,
    )
  })
})

describe('the API’s refusals', () => {
  test('are rendered against the field they name', async () => {
    // Whether the name is already in the catalogue is not a question a browser
    // can answer, so this is the normal path rather than a drift.
    setup(strain(), {
      status: 'refused',
      refusal: {
        detail: 'A strain with that name already exists.',
        fields: { name: ['A strain with that name already exists.'] },
      },
    })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel }),
      'Cheese',
    )
    await userEvent.click(submitButton(false))

    /*
     * The message appears twice on purpose -- once against the field and once in
     * the summary at the foot of the form -- so this asserts on the field being
     * marked and on the text being present, rather than on a single node. A form
     * this long can have the field it refused off-screen, which is what the
     * summary is for.
     */
    await waitFor(() =>
      expect(
        screen.getByRole('textbox', { name: STRAIN_FORM.nameLabel }),
      ).toBeInvalid(),
    )
    expect(
      screen.getAllByText('A strain with that name already exists.').length,
    ).toBeGreaterThan(0)
  })

  test('reach a picker, not only a text field', async () => {
    setup(strain(), {
      status: 'refused',
      refusal: {
        detail: 'Refused.',
        fields: {
          exclusive_to: ['A strain can only be reserved to an active cultivator.'],
        },
      },
    })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'x',
    )
    await userEvent.click(submitButton(false))

    await waitFor(() =>
      expect(
        screen.getByRole('combobox', { name: STRAIN_FORM.exclusiveLabel }),
      ).toBeInvalid(),
    )
  })

  test('reach the term pickers', async () => {
    // The withdrawn-aroma rule, which the browser deliberately does not check.
    setup(strain(), {
      status: 'refused',
      refusal: {
        detail: 'Refused.',
        fields: { aromas: ['These terms are no longer offered on new strains: Gassy.'] },
      },
    })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'x',
    )
    await userEvent.click(submitButton(false))

    expect(await screen.findByText(/Gassy/)).toBeInTheDocument()
  })

  test('never leave the form claiming a save', async () => {
    const { onSaved } = setup(strain(), {
      status: 'refused',
      refusal: { detail: 'Refused.', fields: {} },
    })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'x',
    )
    await userEvent.click(submitButton(false))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(onSaved).not.toHaveBeenCalled()
    expect(screen.queryByText(STRAIN_FORM.saved)).not.toBeInTheDocument()
  })

  test('show the sentence even when the field is one this build does not know', async () => {
    // Otherwise the form will not save and will not say why.
    setup(strain(), {
      status: 'refused',
      refusal: { detail: 'Something is wrong.', fields: { invented: ['Nope.'] } },
    })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'x',
    )
    await userEvent.click(submitButton(false))

    expect(await screen.findByRole('alert')).toHaveTextContent('Something is wrong.')
  })

  test('a failure is reported as one', async () => {
    setup(strain(), { status: 'failed', reason: 'The club could not be reached.' })

    await userEvent.type(
      screen.getByRole('textbox', { name: STRAIN_FORM.descriptionLabel }),
      'x',
    )
    await userEvent.click(submitButton(false))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The club could not be reached.',
    )
  })
})

describe('the way out', () => {
  test('offers a link back to the catalogue that is not a submit', () => {
    // A "cancel" button inside a form is a submit button waiting to happen.
    setup(strain())

    expect(screen.getByRole('link', { name: STRAIN_FORM.cancel })).toHaveAttribute(
      'href',
      '/admin/strains',
    )
  })

  test('offers a way to the vocabularies, which is why most forms stall', () => {
    setup(strain())

    expect(
      screen.getByRole('link', { name: STRAIN_FORM.termsLinkLabel }),
    ).toHaveAttribute('href', '/admin/strains/terms')
  })
})

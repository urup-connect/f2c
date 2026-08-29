import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { TERMS_SCREEN } from '@/lib/strain-catalogue-content'
import type { Term, Vocabularies } from '@/lib/strain-catalogue'
import { TermsScreen } from './TermsScreen'

/*
 * The aroma and effect vocabularies.
 *
 * The two properties worth the tests are both about withdrawal, because it is
 * standing in for a delete and has to be visibly reversible.
 *
 * **A withdrawal is not a rename.** An administrator who has typed a new name
 * into a row and then presses Withdraw meant to withdraw. Sending the edited name
 * would commit a rename they never saved -- and the rename takes the slug with
 * it, so every strain carrying the term now reads differently.
 *
 * **A withdrawn term keeps its row and its way back.** A withdrawal that could
 * not be reversed from the screen that made it is a delete with extra steps.
 */

const { createTerm, saveTerm } = vi.hoisted(() => ({
  createTerm: vi.fn(),
  saveTerm: vi.fn(),
}))

vi.mock('@/lib/strain-catalogue-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/strain-catalogue-api')>()),
  createTerm,
  saveTerm,
}))

const term = (overrides: Partial<Term> = {}): Term => ({
  id: 'aroma-1',
  name: 'Citrus',
  slug: 'citrus',
  is_available: true,
  strain_count: 0,
  ...overrides,
})

const vocabularies = (overrides: Partial<Vocabularies> = {}): Vocabularies => ({
  aromas: [],
  effects: [],
  ...overrides,
})

const setup = (initial = vocabularies(), unavailable = false) => {
  render(
    <TermsScreen
      initial={initial}
      unavailable={unavailable}
      catalogueHref="/admin/strains"
    />,
  )
}

/** The rename field on a term's row. Each row's field is labelled by its id. */
const nameField = (id: string) => screen.getByLabelText(TERMS_SCREEN.nameLabel, {
  selector: `#term-${id}`,
})

beforeEach(() => {
  createTerm.mockReset()
  saveTerm.mockReset()
})

describe('the two lists', () => {
  test('are drawn as two cards', () => {
    setup()

    expect(
      screen.getByRole('heading', { name: TERMS_SCREEN.aromasHeading }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: TERMS_SCREEN.effectsHeading }),
    ).toBeInTheDocument()
  })

  test('each says when it is empty', () => {
    setup()

    expect(screen.getAllByText(TERMS_SCREEN.empty)).toHaveLength(2)
  })

  test('draw their own terms and not each other’s', () => {
    setup(
      vocabularies({
        aromas: [term({ id: 'a', name: 'Citrus' })],
        effects: [term({ id: 'b', name: 'Relaxing' })],
      }),
    )

    expect(nameField('a')).toHaveValue('Citrus')
    expect(nameField('b')).toHaveValue('Relaxing')
  })

  test('offer a way back to the catalogue', () => {
    setup()

    expect(
      screen.getByRole('link', { name: TERMS_SCREEN.backLabel }),
    ).toHaveAttribute('href', '/admin/strains')
  })

  test('say what a withdrawal does, before anybody does one', () => {
    setup()

    expect(screen.getByText(TERMS_SCREEN.standfirst)).toBeInTheDocument()
  })
})

describe('adding a term', () => {
  test('the button is inert until something is typed', async () => {
    setup()

    const [addButton] = screen.getAllByRole('button', { name: TERMS_SCREEN.addLabel })
    expect(addButton).toBeDisabled()
  })

  test('sends the name to the right vocabulary', async () => {
    createTerm.mockResolvedValue({ status: 'saved', record: term({ name: 'Gassy' }) })
    setup()

    await userEvent.type(screen.getByLabelText(TERMS_SCREEN.newLabel, {
      selector: '#term-new-aromas',
    }), 'Gassy')
    await userEvent.click(
      screen.getAllByRole('button', { name: TERMS_SCREEN.addLabel })[0],
    )

    await waitFor(() => expect(createTerm).toHaveBeenCalledWith('aromas', 'Gassy'))
  })

  test('sends to the effects list from the effects card', async () => {
    createTerm.mockResolvedValue({ status: 'saved', record: term({ name: 'Uplifting' }) })
    setup()

    await userEvent.type(screen.getByLabelText(TERMS_SCREEN.newLabel, {
      selector: '#term-new-effects',
    }), 'Uplifting')
    await userEvent.click(
      screen.getAllByRole('button', { name: TERMS_SCREEN.addLabel })[1],
    )

    await waitFor(() => expect(createTerm).toHaveBeenCalledWith('effects', 'Uplifting'))
  })

  test('adds the term in the list’s own order rather than at the bottom', async () => {
    // The API orders these by name. Appending would leave the new term at the
    // bottom until the next page load and then move it, which reads as the screen
    // having got it wrong the first time.
    createTerm.mockResolvedValue({
      status: 'saved',
      record: term({ id: 'new', name: 'Berry' }),
    })
    setup(vocabularies({ aromas: [term({ id: 'a', name: 'Citrus' })] }))

    await userEvent.type(screen.getByLabelText(TERMS_SCREEN.newLabel, {
      selector: '#term-new-aromas',
    }), 'Berry')
    await userEvent.click(
      screen.getAllByRole('button', { name: TERMS_SCREEN.addLabel })[0],
    )

    await waitFor(() => expect(nameField('new')).toBeInTheDocument())
    const fields = screen
      .getAllByRole('textbox')
      .map((field) => (field as HTMLInputElement).value)

    expect(fields.indexOf('Berry')).toBeLessThan(fields.indexOf('Citrus'))
  })

  test('clears the field after a success, ready for the next one', async () => {
    createTerm.mockResolvedValue({ status: 'saved', record: term({ name: 'Gassy' }) })
    setup()

    const field = screen.getByLabelText(TERMS_SCREEN.newLabel, {
      selector: '#term-new-aromas',
    })
    await userEvent.type(field, 'Gassy')
    await userEvent.click(
      screen.getAllByRole('button', { name: TERMS_SCREEN.addLabel })[0],
    )

    await waitFor(() => expect(field).toHaveValue(''))
  })

  test('shows a refusal and keeps what was typed', async () => {
    // A duplicate name is the common refusal, and clearing the field would make
    // an administrator retype a name to find out what was wrong with it.
    createTerm.mockResolvedValue({
      status: 'refused',
      refusal: { detail: '“Citrus” is already in the list.' },
    })
    setup()

    const field = screen.getByLabelText(TERMS_SCREEN.newLabel, {
      selector: '#term-new-aromas',
    })
    await userEvent.type(field, 'Citrus')
    await userEvent.click(
      screen.getAllByRole('button', { name: TERMS_SCREEN.addLabel })[0],
    )

    expect(
      await screen.findByText('“Citrus” is already in the list.'),
    ).toBeInTheDocument()
    expect(field).toHaveValue('Citrus')
  })
})

describe('renaming a term', () => {
  test('the save button is inert until the name changes', () => {
    setup(vocabularies({ aromas: [term({ id: 'a' })] }))

    expect(
      screen.getByRole('button', { name: TERMS_SCREEN.saveLabel }),
    ).toBeDisabled()
  })

  test('sends the new name', async () => {
    saveTerm.mockResolvedValue({ status: 'saved', record: term({ id: 'a', name: 'Citrusy' }) })
    setup(vocabularies({ aromas: [term({ id: 'a', name: 'Citrus' })] }))

    await userEvent.type(nameField('a'), 'y')
    await userEvent.click(screen.getByRole('button', { name: TERMS_SCREEN.saveLabel }))

    await waitFor(() =>
      expect(saveTerm).toHaveBeenCalledWith('aromas', 'a', 'Citrusy', true),
    )
  })

  test('settles on the name that was stored', async () => {
    saveTerm.mockResolvedValue({ status: 'saved', record: term({ id: 'a', name: 'Citrusy' }) })
    setup(vocabularies({ aromas: [term({ id: 'a', name: 'Citrus' })] }))

    await userEvent.type(nameField('a'), 'y')
    await userEvent.click(screen.getByRole('button', { name: TERMS_SCREEN.saveLabel }))

    await waitFor(() => expect(nameField('a')).toHaveValue('Citrusy'))
  })

  test('shows a refusal against the row it belongs to', async () => {
    saveTerm.mockResolvedValue({
      status: 'refused',
      refusal: { detail: '“Citrusy” is already in the list.' },
    })
    setup(vocabularies({ aromas: [term({ id: 'a', name: 'Citrus' })] }))

    await userEvent.type(nameField('a'), 'y')
    await userEvent.click(screen.getByRole('button', { name: TERMS_SCREEN.saveLabel }))

    expect(
      await screen.findByText('“Citrusy” is already in the list.'),
    ).toBeInTheDocument()
  })
})

describe('withdrawing a term', () => {
  test('sends the stored name, not the edited one', async () => {
    /*
     * The property this whole card is arranged around. An administrator who typed
     * a new name and then pressed Withdraw meant to withdraw -- and a rename
     * takes the slug with it, so committing one by accident changes how every
     * strain carrying the term reads.
     */
    saveTerm.mockResolvedValue({
      status: 'saved',
      record: term({ id: 'a', is_available: false }),
    })
    setup(vocabularies({ aromas: [term({ id: 'a', name: 'Citrus' })] }))

    await userEvent.type(nameField('a'), 'y')
    await userEvent.click(
      screen.getByRole('button', { name: TERMS_SCREEN.withdrawLabel }),
    )

    await waitFor(() =>
      expect(saveTerm).toHaveBeenCalledWith('aromas', 'a', 'Citrus', false),
    )
  })

  test('marks the term and offers the way back', async () => {
    setup(vocabularies({ aromas: [term({ id: 'a', is_available: false })] }))

    expect(screen.getByText(TERMS_SCREEN.withdrawnBadge)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: TERMS_SCREEN.restoreLabel }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: TERMS_SCREEN.withdrawLabel }),
    ).not.toBeInTheDocument()
  })

  test('restoring offers it again', async () => {
    saveTerm.mockResolvedValue({
      status: 'saved',
      record: term({ id: 'a', is_available: true }),
    })
    setup(vocabularies({ aromas: [term({ id: 'a', is_available: false })] }))

    await userEvent.click(
      screen.getByRole('button', { name: TERMS_SCREEN.restoreLabel }),
    )

    await waitFor(() =>
      expect(saveTerm).toHaveBeenCalledWith('aromas', 'a', 'Citrus', true),
    )
    expect(
      await screen.findByRole('button', { name: TERMS_SCREEN.withdrawLabel }),
    ).toBeInTheDocument()
  })

  test('keeps the row, which is the whole point', async () => {
    setup(vocabularies({ aromas: [term({ id: 'a', is_available: false })] }))

    expect(nameField('a')).toBeInTheDocument()
  })
})

describe('the usage count', () => {
  test('says a term is unused rather than showing a zero', () => {
    setup(vocabularies({ aromas: [term({ id: 'a', strain_count: 0 })] }))

    expect(screen.getByText(TERMS_SCREEN.unused)).toBeInTheDocument()
  })

  test('uses the singular for one strain', () => {
    setup(vocabularies({ aromas: [term({ id: 'a', strain_count: 1 })] }))

    expect(screen.getByText(`1 ${TERMS_SCREEN.usedByOne}`)).toBeInTheDocument()
  })

  test('uses the plural for several', () => {
    // "1 strains" is the kind of thing that makes a screen look unfinished.
    setup(vocabularies({ aromas: [term({ id: 'a', strain_count: 12 })] }))

    expect(screen.getByText(`12 ${TERMS_SCREEN.usedBy}`)).toBeInTheDocument()
  })
})

describe('when the read failed', () => {
  test('says so rather than showing two empty lists', () => {
    setup(vocabularies(), true)

    expect(screen.getByRole('alert')).toHaveTextContent(TERMS_SCREEN.loadFailed)
  })
})

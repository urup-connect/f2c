import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { STRAIN_FORM, TERMS_SCREEN } from '@/lib/strain-catalogue-content'
import type { Term } from '@/lib/strain-catalogue'
import { TermPicker } from './TermPicker'

/*
 * The aroma and effect picker.
 *
 * Almost every assertion here is about the three-state rule that `is_available`
 * creates, because getting it wrong is silent in both directions.
 *
 * A withdrawn term that this strain does not have must not be offered: ticking it
 * produces a save the API refuses, for a reason the form never explained.
 *
 * A withdrawn term that this strain *does* have must be offered, and the failure
 * mode if it is not is the bad one -- the screen would show a strain whose terms
 * are not the terms it has, and the next save would silently strip the withdrawn
 * one. The field's help text promises exactly the opposite: "Existing strains
 * keep it."
 */

const term = (overrides: Partial<Term> = {}): Term => ({
  id: 'aroma-1',
  name: 'Citrus',
  slug: 'citrus',
  is_available: true,
  strain_count: 0,
  ...overrides,
})

const setup = (props: Partial<Parameters<typeof TermPicker>[0]> = {}) => {
  const onSelected = vi.fn()
  render(
    <TermPicker
      name="aromas"
      label="Aromas"
      terms={[term()]}
      selected={[]}
      onSelected={onSelected}
      {...props}
    />,
  )
  return { onSelected }
}

describe('the checkboxes', () => {
  test('one per term, named by the term', () => {
    setup()

    expect(screen.getByRole('checkbox', { name: /Citrus/ })).toBeInTheDocument()
  })

  test('a term on the strain is ticked', () => {
    setup({ selected: ['aroma-1'] })

    expect(screen.getByRole('checkbox', { name: /Citrus/ })).toBeChecked()
  })

  test('a term not on the strain is not ticked', () => {
    setup({ selected: [] })

    expect(screen.getByRole('checkbox', { name: /Citrus/ })).not.toBeChecked()
  })

  test('ticking one reports it', async () => {
    const { onSelected } = setup()

    await userEvent.click(screen.getByRole('checkbox', { name: /Citrus/ }))

    expect(onSelected).toHaveBeenCalledWith(['aroma-1'])
  })

  test('unticking one reports its absence', async () => {
    const { onSelected } = setup({ selected: ['aroma-1'] })

    await userEvent.click(screen.getByRole('checkbox', { name: /Citrus/ }))

    expect(onSelected).toHaveBeenCalledWith([])
  })

  test('reports the ids in the club’s own order, not the order they were ticked', async () => {
    // So two administrators who pick the same terms send the same payload.
    const terms = [
      term({ id: 'a', name: 'Citrus' }),
      term({ id: 'b', name: 'Earthy' }),
    ]
    const { onSelected } = setup({ terms, selected: ['b'] })

    await userEvent.click(screen.getByRole('checkbox', { name: /Citrus/ }))

    expect(onSelected).toHaveBeenCalledWith(['a', 'b'])
  })
})

describe('a withdrawn term', () => {
  test('is not offered when the strain does not have it', async () => {
    // Ticking it would produce a save the API refuses for a reason the form
    // never explained.
    setup({ terms: [term({ is_available: false })], selected: [] })

    expect(screen.queryByRole('checkbox', { name: /Citrus/ })).not.toBeInTheDocument()
  })

  test('is offered when the strain already has it', () => {
    // The bad failure mode if it were not: the screen would show terms that are
    // not the strain's terms, and the next save would strip this one.
    setup({ terms: [term({ is_available: false })], selected: ['aroma-1'] })

    expect(screen.getByRole('checkbox', { name: /Citrus/ })).toBeChecked()
  })

  test('is marked as withdrawn where it is shown', () => {
    setup({ terms: [term({ is_available: false })], selected: ['aroma-1'] })

    expect(screen.getByText(TERMS_SCREEN.withdrawnBadge)).toBeInTheDocument()
  })

  test('can be taken off the strain', async () => {
    // "Existing strains keep it" is a promise about a save, not a lock: an
    // administrator who wants it gone must be able to remove it.
    const { onSelected } = setup({
      terms: [term({ is_available: false })],
      selected: ['aroma-1'],
    })

    await userEvent.click(screen.getByRole('checkbox', { name: /Citrus/ }))

    expect(onSelected).toHaveBeenCalledWith([])
  })

  test('an available term is not marked', () => {
    setup({ terms: [term({ is_available: true })] })

    expect(screen.queryByText(TERMS_SCREEN.withdrawnBadge)).not.toBeInTheDocument()
  })
})

describe('the usage count', () => {
  test('says a term is unused rather than showing a zero', () => {
    setup({ terms: [term({ strain_count: 0 })] })

    expect(screen.getByText(TERMS_SCREEN.unused)).toBeInTheDocument()
  })

  test('uses the singular for one strain', () => {
    setup({ terms: [term({ strain_count: 1 })] })

    expect(screen.getByText(`1 ${TERMS_SCREEN.usedByOne}`)).toBeInTheDocument()
  })

  test('uses the plural for several', () => {
    setup({ terms: [term({ strain_count: 12 })] })

    expect(screen.getByText(`12 ${TERMS_SCREEN.usedBy}`)).toBeInTheDocument()
  })
})

describe('an empty vocabulary', () => {
  test('says so, and says what to do about it', () => {
    // A fieldset with no checkboxes reads as a section that failed to render.
    setup({ terms: [] })

    expect(screen.getByText(STRAIN_FORM.noTerms)).toBeInTheDocument()
  })

  test('is what a list of only withdrawn terms looks like', () => {
    setup({ terms: [term({ is_available: false })], selected: [] })

    expect(screen.getByText(STRAIN_FORM.noTerms)).toBeInTheDocument()
  })
})

describe('the group', () => {
  test('is labelled by its legend', () => {
    setup()

    expect(screen.getByRole('group', { name: 'Aromas' })).toBeInTheDocument()
  })

  test('announces a refusal for the whole group', () => {
    setup({ error: 'These terms are no longer offered on new strains: Gassy.' })

    expect(screen.getByRole('alert')).toHaveTextContent('Gassy')
  })
})

import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import { PAIR_EDITOR } from '@/lib/strain-catalogue-content'
import { newPair, type Pair } from '@/lib/strain-catalogue'
import { PairField } from './PairField'

/*
 * The editor that stands between an administrator and a textarea full of braces.
 *
 * Three properties are worth the tests, and each is a bug that was easy to write.
 *
 * **A row is never removed to nothing.** Removing the only row would leave a
 * labelled section with no fields, which reads as a section that failed to
 * render rather than one that is empty.
 *
 * **The trailing empty row appears when the last row is filled, and only then.**
 * Appending on any edit would grow the list by one every time an existing entry
 * was corrected.
 *
 * **Every control has an accessible name that identifies its row.** Eleven
 * buttons all called "Remove" tell a screen reader user nothing about which one
 * they are on, and this is a destructive control.
 */

/**
 * A controlled harness, because the component is controlled.
 *
 * Rendering it with a static `pairs` prop and asserting on `onPairs` would test
 * one interaction at a time and could not test a sequence -- and a sequence is
 * where the trailing-row logic lives.
 */
const Harness = ({
  initial,
  onPairs,
  error,
}: {
  initial: readonly Pair[]
  onPairs?: (pairs: readonly Pair[]) => void
  error?: string
}) => {
  const [pairs, setPairs] = useState<readonly Pair[]>(initial)

  return (
    <PairField
      name="terpene-profile"
      label="Terpenes"
      pairs={pairs}
      error={error}
      onPairs={(next) => {
        setPairs(next)
        onPairs?.(next)
      }}
    />
  )
}

const nameCells = () =>
  screen.getAllByRole('textbox', { name: new RegExp(`^${PAIR_EDITOR.nameColumn},`) })

const valueCells = () =>
  screen.getAllByRole('textbox', { name: new RegExp(`^${PAIR_EDITOR.valueColumn},`) })

describe('the rows', () => {
  test('draws a name and a value field for each', () => {
    render(<Harness initial={[newPair('myrcene', '0.5')]} />)

    expect(nameCells()).toHaveLength(1)
    expect(valueCells()).toHaveLength(1)
    expect(nameCells()[0]).toHaveValue('myrcene')
    expect(valueCells()[0]).toHaveValue('0.5')
  })

  test('names each field by its column and its row', () => {
    // "Name, myrcene" rather than "row 3, column 1". A screen reader filling in a
    // form needs the entry's own name, not its coordinates.
    render(<Harness initial={[newPair('myrcene', '0.5')]} />)

    expect(
      screen.getByRole('textbox', { name: `${PAIR_EDITOR.nameColumn}, myrcene` }),
    ).toBeInTheDocument()
  })

  test('names an unnamed row by its position, so it is still reachable', () => {
    render(<Harness initial={[newPair()]} />)

    expect(
      screen.getByRole('textbox', { name: `${PAIR_EDITOR.nameColumn}, entry 1` }),
    ).toBeInTheDocument()
  })
})

describe('the trailing empty row', () => {
  test('appears when the last row gains a name', async () => {
    render(<Harness initial={[newPair()]} />)

    await userEvent.type(nameCells()[0], 'myrcene')

    expect(nameCells()).toHaveLength(2)
  })

  test('appears when the last row gains only a value', async () => {
    // A value with no name is dropped on submit, but somebody typing the value
    // first should still get somewhere to put the next entry.
    render(<Harness initial={[newPair()]} />)

    await userEvent.type(valueCells()[0], '0.5')

    expect(nameCells()).toHaveLength(2)
  })

  test('does not appear again when an earlier row is corrected', async () => {
    // The bug this guards: appending on any edit grows the list by one every
    // time an existing entry is retyped.
    render(<Harness initial={[newPair('myrcene', '0.5'), newPair()]} />)

    await userEvent.type(nameCells()[0], 'x')

    expect(nameCells()).toHaveLength(2)
  })

  test('stops being added once the last row is empty', async () => {
    /*
     * Emptying a filled row leaves the spare row that filling it produced, and
     * that is deliberate rather than tidy-up the editor declines to do. Clearing
     * `myrcene`'s name still leaves its value, so the row is non-empty and one
     * spare is appended; clearing the value then makes the last row empty and no
     * further row appears.
     *
     * The editor never shrinks on its own, and it should not: an administrator
     * who pressed "Add another" and then changed their mind would watch the row
     * they asked for vanish. Empty rows cost nothing -- `mappingFrom` drops them
     * on submit -- so the invariant worth holding is that the list stops growing,
     * not that it shrinks back.
     */
    render(<Harness initial={[newPair('myrcene', '0.5')]} />)

    await userEvent.clear(nameCells()[0])
    expect(nameCells()).toHaveLength(2)

    await userEvent.clear(valueCells()[0])
    expect(nameCells()).toHaveLength(2)
  })
})

describe('removing a row', () => {
  test('removes the row it names', async () => {
    render(
      <Harness initial={[newPair('myrcene', '0.5'), newPair('limonene', '0.2')]} />,
    )

    await userEvent.click(
      screen.getByRole('button', {
        name: `${PAIR_EDITOR.removeDescription}: myrcene`,
      }),
    )

    expect(nameCells().map((cell) => (cell as HTMLInputElement).value)).toEqual([
      'limonene',
    ])
  })

  test('never leaves the editor with no rows', async () => {
    // A labelled section with no fields reads as a section that failed to render.
    render(<Harness initial={[newPair('myrcene', '0.5')]} />)

    await userEvent.click(
      screen.getByRole('button', {
        name: `${PAIR_EDITOR.removeDescription}: myrcene`,
      }),
    )

    expect(nameCells()).toHaveLength(1)
    expect(nameCells()[0]).toHaveValue('')
  })

  test('gives every remove button an accessible name of its own', () => {
    // The bug: eleven buttons all called "Remove", on a destructive control.
    render(
      <Harness initial={[newPair('myrcene', '0.5'), newPair('limonene', '0.2')]} />,
    )

    const names = screen
      .getAllByRole('button')
      .map((button) => button.getAttribute('aria-label'))
      .filter((name): name is string => name !== null)

    expect(new Set(names).size).toBe(names.length)
  })
})

describe('adding a row', () => {
  test('the button appends one', async () => {
    render(<Harness initial={[newPair()]} />)

    await userEvent.click(screen.getByRole('button', { name: PAIR_EDITOR.addLabel }))

    expect(nameCells()).toHaveLength(2)
  })
})

describe('the group', () => {
  test('is labelled by its legend', () => {
    render(<Harness initial={[newPair()]} />)

    expect(screen.getByRole('group', { name: 'Terpenes' })).toBeInTheDocument()
  })

  test('announces a refusal for the whole group', () => {
    // The refusals here are about the set rather than about one field -- two rows
    // sharing a name, or too many entries -- so they belong on the fieldset.
    render(<Harness initial={[newPair()]} error="“myrcene” is entered twice." />)

    expect(screen.getByRole('alert')).toHaveTextContent('“myrcene” is entered twice.')
  })

  test('reports what the caller typed, unaltered', async () => {
    const onPairs = vi.fn()
    render(<Harness initial={[newPair()]} onPairs={onPairs} />)

    await userEvent.type(valueCells()[0], ' 0.5 ')

    // Trimming happens in `mappingFrom` on submit, not here: a field that edits
    // what somebody typed while they are typing it is a field that fights them.
    const last = onPairs.mock.calls.at(-1)?.[0] as readonly Pair[]
    expect(last[0].value).toBe(' 0.5 ')
  })
})

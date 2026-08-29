import { PAIR_EDITOR } from '@/lib/strain-catalogue-content'
import { newPair, type Pair } from '@/lib/strain-catalogue'

type PairFieldProps = {
  /** The form field name. Also the basis of every id in the group. */
  name: string
  label: string
  hint?: string
  /** The refusal for the whole group -- a duplicate name, or too many entries. */
  error?: string
  pairs: readonly Pair[]
  onPairs: (pairs: readonly Pair[]) => void
}

const CELL =
  'w-full rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * The editor for a JSON column: a list of name/value rows.
 *
 * This is what stands between an administrator and a `textarea` full of braces.
 * `Strain.other_cannabinoids`, `terpene_profile` and `disease_resistance` are
 * free-form JSON objects by design -- they are shown to members and never
 * searched, so they need no fixed set of keys -- and the Django admin edits them
 * as raw JSON. Nobody outside this repository should have to type `{"CBG": 0.8}`
 * to record a cannabinoid.
 *
 * ## Three decisions worth reading
 *
 * **The rows are the state, not a view of the object.** An object cannot hold
 * two rows that momentarily share a name while one is being retyped, and it has
 * no stable order -- so re-deriving rows from it would reorder the fields under
 * the cursor. `lib/strain-catalogue.ts` owns both crossings and explains them at
 * length.
 *
 * **A row is keyed by its own id, never by its index.** Deleting the second of
 * four rows shifts every index below it, so React reuses row 3's DOM node for
 * what is now row 2 -- which moves focus into a different field mid-sentence.
 * `Pair.id` is assigned once and survives every insertion and deletion.
 *
 * **There is always one empty row.** Typing into the last row appends another,
 * so the common case -- entering several terpenes -- never involves pressing
 * "add". The button stays for whoever wants it and for a keyboard user who would
 * rather not tab through a field to get a new one. Empty rows are dropped on
 * submit by `mappingFrom`, so the trailing one costs nothing.
 *
 * ## Accessibility
 *
 * Not a `table`, despite looking like one. The two columns are a *form*, and a
 * table would announce "row 3, column 1" where what a screen reader needs is
 * "myrcene, name". Each cell carries its own `aria-label` naming the column and
 * the row's current name, which is also why the remove button's accessible name
 * is built from the row rather than being the bare word "Remove" eleven times
 * over.
 */
export const PairField = ({
  name,
  label,
  hint,
  error,
  pairs,
  onPairs,
}: PairFieldProps) => {
  const groupId = `catalogue-${name}`
  const hintId = `${groupId}-hint`
  const errorId = `${groupId}-error`

  const describedBy = [hint ? hintId : null, error ? errorId : null]
    .filter(Boolean)
    .join(' ')

  /**
   * Replace one row, and keep a trailing empty row available.
   *
   * The append happens when the *last* row gains a name, not on any edit: doing
   * it whenever any row is non-empty would grow the list by one every time an
   * existing entry was corrected.
   */
  const edit = (id: string, field: 'key' | 'value', value: string) => {
    const edited = pairs.map((pair) =>
      pair.id === id ? { ...pair, [field]: value } : pair,
    )

    const last = edited[edited.length - 1]
    const needsRoom = last === undefined || last.key.trim() !== '' || last.value.trim() !== ''

    onPairs(needsRoom ? [...edited, newPair()] : edited)
  }

  /**
   * Drop a row, never leaving the editor with none.
   *
   * Removing the only row would leave a labelled section with no fields in it,
   * which reads as a section that failed to render rather than one that is
   * empty.
   */
  const remove = (id: string) => {
    const kept = pairs.filter((pair) => pair.id !== id)
    onPairs(kept.length > 0 ? kept : [newPair()])
  }

  /** What a row is called, for a screen reader, before it has a name. */
  const rowName = (pair: Pair, index: number) =>
    pair.key.trim() === '' ? `entry ${index + 1}` : pair.key.trim()

  return (
    <fieldset
      className="flex flex-col gap-2"
      aria-describedby={describedBy.length > 0 ? describedBy : undefined}
    >
      <legend className="font-sans text-base font-medium text-foreground">{label}</legend>

      {hint ? (
        <p id={hintId} className="font-sans text-sm leading-relaxed text-muted-foreground">
          {hint}
        </p>
      ) : null}

      <div className="flex flex-col gap-2">
        {pairs.map((pair, index) => (
          <div key={pair.id} className="flex items-start gap-2">
            <input
              type="text"
              value={pair.key}
              aria-label={`${PAIR_EDITOR.nameColumn}, ${rowName(pair, index)}`}
              onChange={(event) => edit(pair.id, 'key', event.currentTarget.value)}
              className={`${CELL} basis-1/2`}
            />

            <input
              type="text"
              value={pair.value}
              aria-label={`${PAIR_EDITOR.valueColumn}, ${rowName(pair, index)}`}
              onChange={(event) => edit(pair.id, 'value', event.currentTarget.value)}
              className={`${CELL} basis-1/2`}
            />

            <button
              type="button"
              onClick={() => remove(pair.id)}
              /*
               * The accessible name names the row. Eleven buttons all called
               * "Remove" tell a screen reader user nothing about which one they
               * are on, and this is a destructive control.
               */
              aria-label={`${PAIR_EDITOR.removeDescription}: ${rowName(pair, index)}`}
              className="inline-flex h-11 shrink-0 items-center rounded-control border-2 border-border px-3 font-sans text-sm text-muted-foreground transition-colors hover:border-error hover:text-error focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            >
              {PAIR_EDITOR.removeLabel}
            </button>
          </div>
        ))}
      </div>

      <div>
        <button
          type="button"
          onClick={() => onPairs([...pairs, newPair()])}
          className="inline-flex h-10 items-center rounded-pill border-2 border-border px-4 font-sans text-sm font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
        >
          {PAIR_EDITOR.addLabel}
        </button>
      </div>

      {error ? (
        <p id={errorId} role="alert" className="font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </fieldset>
  )
}

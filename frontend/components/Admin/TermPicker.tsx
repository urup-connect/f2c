import { STRAIN_FORM, TERMS_SCREEN } from '@/lib/strain-catalogue-content'
import type { Term } from '@/lib/strain-catalogue'

type TermPickerProps = {
  /** The form field name. Also the basis of every id in the group. */
  name: string
  label: string
  /** Every term in the club's list, withdrawn ones included. */
  terms: readonly Term[]
  /** The ids currently on the strain. */
  selected: readonly string[]
  error?: string
  onSelected: (selected: readonly string[]) => void
}

/**
 * The aroma or effect picker: a checkbox for each term in the club's list.
 *
 * Checkboxes rather than a multiple `select`, and that is the whole design
 * decision here. A `<select multiple>` needs ctrl-click to add a second value,
 * silently drops the rest of the selection when somebody clicks without it, and
 * on a phone opens a picker that shows four rows of a twenty-term list.
 * `member-roles.md` has cultivators asking for additions to these vocabularies,
 * so the list is expected to grow -- and it grows into something a multi-select
 * gets worse at.
 *
 * ## Withdrawn terms
 *
 * `is_available` is cleared to stop a term being offered on *new* strains while
 * every strain already carrying it keeps it -- the field's own help text says so,
 * and `strains.services` enforces it. That makes three states, not two, and this
 * component draws all three:
 *
 * * available -- an ordinary checkbox;
 * * withdrawn and **not** on this strain -- not rendered at all, because ticking
 *   it would produce a save the API refuses;
 * * withdrawn and **on** this strain -- rendered, marked, and unticking it is
 *   allowed. That last one is the case worth the code: hiding it would show an
 *   administrator a strain whose terms are not the terms it has, and a save from
 *   that screen would silently strip the withdrawn one.
 *
 * The count beside each term is what makes withdrawal a considered act on the
 * vocabularies screen; it is shown here too so the same fact does not need
 * looking up in two places.
 */
export const TermPicker = ({
  name,
  label,
  terms,
  selected,
  error,
  onSelected,
}: TermPickerProps) => {
  const groupId = `catalogue-${name}`
  const errorId = `${groupId}-error`
  const held = new Set(selected)

  /*
   * A withdrawn term is offered only if the strain already has it. Filtering
   * here rather than in the caller so that every picker behaves the same way and
   * the rule sits beside the comment explaining it.
   */
  const offered = terms.filter((term) => term.is_available || held.has(term.id))

  const toggle = (id: string) => {
    const next = new Set(held)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    // An array, not a Set, because it becomes a JSON body. Ordered by the club's
    // list rather than by the order they were ticked, so two administrators who
    // pick the same terms send the same payload.
    onSelected(terms.filter((term) => next.has(term.id)).map((term) => term.id))
  }

  return (
    <fieldset
      className="flex flex-col gap-2"
      aria-describedby={error ? errorId : undefined}
    >
      <legend className="font-sans text-base font-medium text-foreground">{label}</legend>

      {offered.length === 0 ? (
        <p className="font-sans text-sm leading-relaxed text-muted-foreground">
          {STRAIN_FORM.noTerms}
        </p>
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {offered.map((term) => {
            const id = `${groupId}-${term.id}`

            return (
              <li key={term.id}>
                <label
                  htmlFor={id}
                  className="flex items-start gap-2 rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-sm text-foreground has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-forest-green"
                >
                  <input
                    id={id}
                    type="checkbox"
                    checked={held.has(term.id)}
                    onChange={() => toggle(term.id)}
                    className="mt-1 size-4 shrink-0 accent-forest-green"
                  />

                  <span className="flex flex-col gap-0.5">
                    <span className="font-medium">{term.name}</span>

                    {/*
                      * Two facts under the name, and both are shown rather than
                      * one: a withdrawn term still in use has to say both that
                      * it is withdrawn and how many strains would be affected
                      * if it were renamed.
                      */}
                    {term.is_available ? null : (
                      <span className="text-xs uppercase tracking-label text-error">
                        {TERMS_SCREEN.withdrawnBadge}
                      </span>
                    )}

                    <span className="text-xs text-muted-foreground">
                      {term.strain_count === 0
                        ? TERMS_SCREEN.unused
                        : `${term.strain_count} ${
                            term.strain_count === 1
                              ? TERMS_SCREEN.usedByOne
                              : TERMS_SCREEN.usedBy
                          }`}
                    </span>
                  </span>
                </label>
              </li>
            )
          })}
        </ul>
      )}

      {error ? (
        <p id={errorId} role="alert" className="font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </fieldset>
  )
}

type TextAreaFieldProps = {
  /** The form field name. Also the basis of every id on the group. */
  name: string
  label: string
  hint?: string
  error?: string
  value: string
  /** Visible rows. Prose gets more than a lineage does. */
  rows?: number
  onValue: (value: string) => void
}

const TEXTAREA =
  'w-full rounded-control border-2 bg-surface px-3 py-2 font-sans text-base leading-relaxed text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * One labelled `textarea`, for the fields that hold prose.
 *
 * A third sibling to `TextField` and `SelectField`, matching both. Not a
 * `TextField` with a `multiline` flag, because the two differ in the way that
 * matters: `TextField` is uncontrolled and reports on blur, and this reports on
 * every keystroke.
 *
 * **Controlled, and told on every change rather than on blur.** `TextField`
 * waits for blur because it formats and filters, and doing either under the
 * caret has a screen reader re-announce the value on every keystroke. Nothing
 * here formats anything, and the form's "nothing has changed yet" state has to
 * notice a description being typed -- which on blur it would not, until the
 * administrator clicked somewhere else. A save button that stays inert while
 * somebody types into the field beneath it reads as a broken form.
 *
 * No character counter and no `maxLength`. `Strain.description` is a `TextField`
 * in Django terms -- a `TextField` model field, which is unbounded -- so there
 * is no limit to count towards, and inventing one here would be this component
 * enforcing a rule the column does not have.
 */
export const TextAreaField = ({
  name,
  label,
  hint,
  error,
  value,
  rows = 4,
  onValue,
}: TextAreaFieldProps) => {
  const id = `catalogue-${name}`
  const hintId = `${id}-hint`
  const errorId = `${id}-error`

  const describedBy = [hint ? hintId : null, error ? errorId : null]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-sans text-base font-medium text-foreground">
        {label}
      </label>

      {hint ? (
        <p id={hintId} className="font-sans text-sm leading-relaxed text-muted-foreground">
          {hint}
        </p>
      ) : null}

      <textarea
        id={id}
        name={name}
        rows={rows}
        value={value}
        onChange={(event) => onValue(event.currentTarget.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy.length > 0 ? describedBy : undefined}
        className={`${TEXTAREA} ${error ? 'border-error' : 'border-border'}`}
      />

      {error ? (
        <p id={errorId} className="font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}

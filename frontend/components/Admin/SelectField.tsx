type Choice = {
  value: string
  label: string
}

type SelectFieldProps = {
  /** The form field name. Also the basis of every id on the group. */
  name: string
  label: string
  /** What the field wants, in the page's own words. Omitted when the label says enough. */
  hint?: string
  /** The refusal message, when this field has one. */
  error?: string
  value: string
  choices: readonly Choice[]
  /**
   * The label on the empty option.
   *
   * Present on every select, because a `select` with no empty option shows its
   * first choice as though somebody had picked it. On an optional field the text
   * is what "unset" means -- "Not stated" -- and on a required one it is an
   * instruction: "Choose one". The caller knows which; this component does not.
   */
  placeholder: string
  onValue: (value: string) => void
}

const SELECT =
  'w-full appearance-none rounded-control border-2 bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * One labelled `select`, its hint and its refusal.
 *
 * `TextField`'s sibling, and written to match it: same wrapper, same label
 * styling, same `aria-describedby` wiring, same refusal treatment. Two files
 * rather than one component with a `type` prop, because almost nothing they do
 * is shared -- `TextField` filters and formats an uncontrolled input on blur,
 * and this is a controlled element with a fixed set of values and none of that
 * machinery.
 *
 * **Controlled, unlike `TextField`.** A `select` has no caret to lose and no
 * paste to clean, so the reasons `TextField` stays uncontrolled do not apply --
 * and a controlled value is what lets the form reset a field to what the server
 * actually stored without remounting it.
 *
 * **The empty option is always rendered.** A `select` whose first option is
 * `indica` opens showing "Indica" with nothing chosen, and an administrator who
 * agrees with what they see submits a value nobody selected. The empty option
 * makes "not chosen" visible and lets `checkStrain` refuse it where the field is
 * required.
 *
 * No `required` attribute, for the reason `TextField` gives: it would hand a
 * browser-worded bubble to whoever has JavaScript and our own wording to whoever
 * does not, so the two would not behave alike.
 */
export const SelectField = ({
  name,
  label,
  hint,
  error,
  value,
  choices,
  placeholder,
  onValue,
}: SelectFieldProps) => {
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

      <select
        id={id}
        name={name}
        value={value}
        onChange={(event) => onValue(event.currentTarget.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy.length > 0 ? describedBy : undefined}
        className={`${SELECT} ${error ? 'border-error' : 'border-border'}`}
      >
        <option value="">{placeholder}</option>
        {choices.map((choice) => (
          <option key={choice.value} value={choice.value}>
            {choice.label}
          </option>
        ))}
      </select>

      {error ? (
        <p id={errorId} className="font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}

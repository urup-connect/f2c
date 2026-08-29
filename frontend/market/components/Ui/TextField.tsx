import type { ChangeEvent } from 'react'

type TextFieldProps = {
  /** The form field name. Also the basis of every id on the group. */
  name: string
  label: string
  /** What the field wants, in the page's own words. Omitted when the label says enough. */
  hint?: string
  /** The refusal message, when this field has one. */
  error?: string
  /** Only ever a value the server sent back, never something the visitor did not type. */
  defaultValue?: string
  autoComplete?: string
  inputMode?: 'numeric' | 'email' | 'tel'
  maxLength?: number
  /**
   * Rewrites the field's value once it loses focus. Only the mobile number uses it.
   *
   * Named for its moment, as is `filterOnInput` below: the two fire at different times and doing
   * either at the other's moment would be wrong.
   */
  formatOnBlur?: (value: string) => string
  /**
   * Drops characters the field will never accept, as they are typed or pasted.
   *
   * Deciding *what* is acceptable belongs to the caller; the field applies it and puts the caret
   * back where it was.
   */
  filterOnInput?: (value: string) => string
  /** Told what the field holds once it loses focus, after `formatOnBlur` has tidied it. */
  onBlurValue?: (value: string) => void
}

const INPUT =
  'w-full rounded-control border-2 bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf'

/**
 * One labelled text field, its hint and its refusal.
 *
 * Uncontrolled: the DOM holds the value, so both forms in this application submit without
 * JavaScript and neither re-renders on every keystroke.
 *
 * Always `type="text"`, never `type="number"`: a number input strips a leading zero, which is fatal
 * for a mobile number written `082…`. `inputMode` gives a phone the right keypad without any of that.
 *
 * No `placeholder`, ever. A placeholder disappears as soon as somebody types and is not a label.
 *
 * No `required` attribute. It would hand a browser-worded bubble to a visitor with JavaScript and
 * our own wording to one without, so the two would not behave alike. The rules refuse an empty field
 * and say so in the page's own words.
 *
 * A near-copy of the club's `SignUp/TextField`, and one of the components `packages/ui` is for. It
 * differs in two respects, both deliberate: the notice slot is gone, because nothing in the store
 * makes a check that can fail without refusing, and `inputMode` admits `email` and `tel`, because
 * the store asks for both on a phone.
 */
export const TextField = ({
  name,
  label,
  hint,
  error,
  defaultValue,
  autoComplete,
  inputMode,
  maxLength,
  formatOnBlur,
  filterOnInput,
  onBlurValue,
}: TextFieldProps) => {
  const id = `field-${name}`
  const hintId = `${id}-hint`
  const errorId = `${id}-error`

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')

  /*
   * Filtering happens on input rather than by blocking a keypress, because a paste has to be cleaned
   * too and a keypress handler never sees one. The cost is that cleaning a value moves the caret to
   * the end, so it is put back: the new position is however many characters survived from in front
   * of the old one. A dropped keystroke then leaves the caret exactly where it was, which is what
   * makes the character appear to have done nothing at all.
   */
  const filter = filterOnInput
    ? (event: ChangeEvent<HTMLInputElement>) => {
        const input = event.currentTarget
        const typed = input.value
        const filtered = filterOnInput(typed)

        if (filtered === typed) return

        const caret = input.selectionStart ?? typed.length
        const kept = filterOnInput(typed.slice(0, caret)).length

        input.value = filtered
        input.setSelectionRange(kept, kept)
      }
    : undefined

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

      <input
        id={id}
        name={name}
        type="text"
        defaultValue={defaultValue}
        autoComplete={autoComplete}
        inputMode={inputMode}
        maxLength={maxLength}
        onChange={filter}
        /*
         * Grouping happens on blur, never on change. Inserting separators under the caret has a
         * screen reader re-announce the whole value on every keystroke, fights a paste, and turns
         * backspace into a guess.
         */
        onBlur={
          formatOnBlur || onBlurValue
            ? (event) => {
                const input = event.currentTarget

                if (formatOnBlur) input.value = formatOnBlur(input.value)

                // After the formatting, never before it: what leaves this field is what the visitor
                // can now see in it.
                onBlurValue?.(input.value)
              }
            : undefined
        }
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy.length > 0 ? describedBy : undefined}
        className={`${INPUT} ${error ? 'border-error' : 'border-border'}`}
      />

      {error ? (
        <p id={errorId} className="font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}

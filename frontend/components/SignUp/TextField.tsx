import type { ChangeEvent } from 'react'

type TextFieldProps = {
  /** The form field name. Also the basis of every id on the group. */
  name: string
  label: string
  /** What the field wants, in the page's own words. Omitted when the label says enough. */
  hint?: string
  /** The refusal message, when this field has one. */
  error?: string
  /**
   * Something true about the field that is not a refusal — today, that a check the club wanted to
   * make could not be made.
   *
   * Separate from `error` rather than another wording of it, because the two must not look or
   * behave alike: a notice leaves the field valid, does not mark it `aria-invalid`, does not put a
   * red border on it, and does not appear in the error summary. It is announced when it appears,
   * because it arrives after the visitor has moved on and they would otherwise never learn of it.
   */
  notice?: string
  /** Only ever a value the server sent back, never something the visitor did not type. */
  defaultValue?: string
  autoComplete?: string
  inputMode?: 'numeric'
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
  /**
   * Told what the field holds, once it loses focus and after `formatOnBlur` has tidied it.
   *
   * The moment a value is finished with, which is the only moment worth asking anyone else about
   * it. Given the formatted value rather than the raw one, so a caller sends the API the same
   * string the member is now looking at.
   */
  onBlurValue?: (value: string) => void
}

const INPUT =
  'w-full rounded-control border-2 bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * One labelled text field, its hint and its refusal.
 *
 * Always `type="text"`, never `type="number"`: a number input strips a leading zero, which is
 * fatal for a mobile number written `082…` and for an ID number that begins `0`. `inputMode`
 * gives a phone its keypad without any of that.
 *
 * No `placeholder`, ever. A placeholder disappears as soon as someone types and is not a label.
 *
 * No `required` attribute, for the same reason the age check has none: it would hand a
 * browser-worded bubble to a visitor with JavaScript and our own wording to one without, so the
 * two would not behave alike. The rules refuse an empty field and say so in the page's own words.
 *
 * A candidate for the shared form primitives on the todo list; built local first so that folding
 * it in later is a move rather than a rewrite. See
 * design/features/member-details-at-sign-up.md section 5.
 */
export const TextField = ({
  name,
  label,
  hint,
  error,
  notice,
  defaultValue,
  autoComplete,
  inputMode,
  maxLength,
  formatOnBlur,
  filterOnInput,
  onBlurValue,
}: TextFieldProps) => {
  const id = `member-${name}`
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const noticeId = `${id}-notice`

  const describedBy = [hint ? hintId : null, error ? errorId : null, notice ? noticeId : null]
    .filter(Boolean)
    .join(' ')

  /*
   * Filtering happens on input rather than by blocking a keypress, because a paste has to be
   * cleaned too and a keypress handler never sees one. The cost is that cleaning a value moves the
   * caret to the end, so it is put back: the new position is however many characters survived from
   * in front of the old one. A dropped keystroke then leaves the caret exactly where it was, which
   * is what makes the character appear to have done nothing at all.
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
         * backspace into a guess. Dropping a character the field never accepts is a different
         * thing: nothing is inserted and the caret does not move.
         *
         * The input is uncontrolled, so the DOM holds the value and both of these write to it.
         */
        onBlur={
          formatOnBlur || onBlurValue
            ? (event) => {
                const input = event.currentTarget

                if (formatOnBlur) input.value = formatOnBlur(input.value)

                // After the formatting, never before it: what leaves this field is what the
                // visitor can now see in it.
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

      {/*
        * `role="status"` rather than `role="alert"`: it is not urgent and it interrupts nothing.
        * The visitor has already moved to the next field by the time this appears, so it is
        * announced politely and left on screen for them to come back to.
        */}
      {notice ? (
        <p id={noticeId} role="status" className="font-sans text-sm text-muted-foreground">
          {notice}
        </p>
      ) : null}
    </div>
  )
}

import { AGE_CHECK } from '@/lib/age-gate-content'

type DateOfBirthFieldsProps = {
  /** Ids of the elements describing the group: the hint, and any refusal message. */
  describedBy?: readonly string[]
  /** Marks the fields invalid after a refusal. The message itself belongs to the form. */
  invalid?: boolean
}

const FIELDS = [
  { name: 'day', label: AGE_CHECK.fields.day, autoComplete: 'bday-day', length: 2, width: 'w-16' },
  {
    name: 'month',
    label: AGE_CHECK.fields.month,
    autoComplete: 'bday-month',
    length: 2,
    width: 'w-16',
  },
  {
    name: 'year',
    label: AGE_CHECK.fields.year,
    autoComplete: 'bday-year',
    length: 4,
    width: 'w-24',
  },
] as const

const FIELD =
  'rounded-control border-2 bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * Date of birth as three numbered fields, the pattern government services settled on.
 *
 * Not `<input type="date">`: its picker opens on the current month, so a birth year is a long
 * way away, and the format it expects is the browser's locale rather than the page's — a South
 * African member has no way to know whether it wants 04/21/1994 or 21/04/1994. Three labelled
 * fields say what they want and need no picker.
 *
 * Text fields rather than `type="number"`: a spinner, a scroll-wheel hazard and inconsistent
 * screen-reader announcement, for no gain on a fixed-length number.
 *
 * No `required` attribute, deliberately. It would hand a browser-worded bubble to a visitor with
 * JavaScript and our own wording to one without, so the two would not behave alike. The server
 * refuses an incomplete date and says so in the page's own words.
 *
 * See design/features/age-gate-before-sign-up.md sections 6.4 and 8.
 */
export const DateOfBirthFields = ({ describedBy, invalid }: DateOfBirthFieldsProps) => (
  <fieldset
    aria-describedby={describedBy?.length ? describedBy.join(' ') : undefined}
    className="border-0 p-0"
  >
    <legend className="font-sans text-base font-medium text-foreground">
      {AGE_CHECK.legend}
    </legend>

    <div className="mt-3 flex gap-3">
      {FIELDS.map(({ name, label, autoComplete, length, width }, index) => (
        <div key={name} className="flex flex-col gap-1">
          <label htmlFor={`dob-${name}`} className="font-sans text-sm text-muted-foreground">
            {label}
          </label>
          <input
            id={`dob-${name}`}
            name={name}
            type="text"
            inputMode="numeric"
            autoComplete={autoComplete}
            maxLength={length}
            aria-invalid={invalid ? true : undefined}
            /*
             * A refusal arrives as a fresh page render, and a live region that is already in the
             * document at load is not reliably announced. Sending focus to the first field is
             * plain HTML, so it behaves the same with JavaScript off, and it takes the group's
             * description — hint and refusal — with it.
             */
            autoFocus={invalid && index === 0}
            className={`${FIELD} ${width} ${invalid ? 'border-error' : 'border-border'}`}
          />
        </div>
      ))}
    </div>
  </fieldset>
)

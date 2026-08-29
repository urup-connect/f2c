import { DateOfBirthFields } from './DateOfBirthFields'
import { AGE_CHECK } from '@/lib/age-gate-content'
import type { AgeCheckRefusal } from '@/lib/age-gate'

type AgeCheckFormProps = {
  /** Where the submission goes. A server action at the route; a spy in tests. */
  action: (formData: FormData) => void | Promise<void>
  /** Why the last attempt was refused, if it was. */
  refusal?: AgeCheckRefusal
}

const HINT_ID = 'age-check-hint'
const ERROR_ID = 'age-check-error'

/*
 * The same shape and palette as ButtonLink's primary tone on cream, written out rather than
 * shared: ButtonLink is an anchor because it navigates, and this submits. A shared Button
 * primitive is its own piece of work on the todo list and is not invented here for one caller.
 */
const SUBMIT =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * The age check itself: why we ask, the three fields, and one control.
 *
 * A plain form posting to a server action, with no client-side state anywhere, so the outcome is
 * identical with JavaScript and without it. That is also why the refusal arrives as a prop rather
 * than from `useActionState`: the server re-renders the page, so there is nothing to hold.
 *
 * See design/features/age-gate-before-sign-up.md sections 6.1 and 6.2.
 */
export const AgeCheckForm = ({ action, refusal }: AgeCheckFormProps) => (
  <form action={action} className="flex flex-col items-start gap-5 text-left">
    <p id={HINT_ID} className="text-sm leading-relaxed text-muted-foreground">
      {AGE_CHECK.hint}
    </p>

    {refusal ? (
      <p id={ERROR_ID} role="alert" className="text-sm font-medium text-error">
        {AGE_CHECK.refusals[refusal]}
      </p>
    ) : null}

    <DateOfBirthFields
      describedBy={refusal ? [HINT_ID, ERROR_ID] : [HINT_ID]}
      invalid={Boolean(refusal)}
    />

    <button type="submit" className={SUBMIT}>
      {AGE_CHECK.submit}
    </button>
  </form>
)

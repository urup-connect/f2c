type FeedbackProps = {
  /** Something went wrong and the customer has to act. */
  problem?: string | null
  /** Something happened and the customer should know. Not a refusal. */
  notice?: string | null
}

/**
 * What a screen has to say between one step and the next.
 *
 * Two roles, and they are not interchangeable. A refusal is an `alert` — it interrupts, because
 * nothing proceeds until somebody does something about it. A notice is a `status` — it is announced
 * politely, because nothing is wrong, and interrupting somebody who is about to type six digits is
 * worse than telling them a moment later.
 *
 * They render in that order and both can be on screen at once: a passkey that failed leaves a
 * refusal, and asking for a code then adds a notice beneath it without clearing the explanation of
 * why the fallback is being offered.
 */
export const Feedback = ({ problem, notice }: FeedbackProps) => (
  <>
    {problem ? (
      <p
        role="alert"
        className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
      >
        {problem}
      </p>
    ) : null}

    {notice ? (
      <p
        role="status"
        className="rounded-control bg-surface-muted px-4 py-3 font-sans text-sm text-foreground"
      >
        {notice}
      </p>
    ) : null}
  </>
)

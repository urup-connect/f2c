type Step = {
  readonly key: string
  readonly title: string
  readonly body: string
}

type StepsProps = {
  heading: string
  steps: readonly Step[]
  /** `numbered` shows the position, for a sequence. `plain` does not, for a set of reasons. */
  form?: 'numbered' | 'plain'
}

/**
 * A heading and three short blocks under it.
 *
 * One component for both bands on the front door, because they are the same shape and differ only in
 * whether order means anything. "How it will work" is a sequence and is numbered; "Why buy this way"
 * is a set of reasons and is not — numbering it would imply a first and a third.
 *
 * An `ol` for the numbered form and a `ul` for the plain one, so the distinction is in the markup a
 * screen reader reads rather than only in the digits a sighted visitor sees. The numeral itself is
 * `aria-hidden`, because the list already announces its own positions.
 */
export const Steps = ({ heading, steps, form = 'plain' }: StepsProps) => {
  const headingId = `band-${heading
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')}`

  const items = steps.map((step, index) => (
    <li key={step.key} className="flex flex-col gap-2 rounded-card bg-surface p-6 shadow-sm">
      {form === 'numbered' ? (
        <span
          aria-hidden="true"
          className="inline-flex h-8 w-8 items-center justify-center rounded-pill bg-leaf-pale font-display text-sm text-leaf"
        >
          {index + 1}
        </span>
      ) : null}

      <h3 className="font-display text-xl tracking-display text-leaf">{step.title}</h3>
      <p className="font-sans text-base leading-relaxed text-muted-foreground">{step.body}</p>
    </li>
  ))

  return (
    <section aria-labelledby={headingId} className="mx-auto max-w-5xl px-6 py-16">
      <h2 id={headingId} className="font-display text-3xl tracking-display text-leaf">
        {heading}
      </h2>

      {form === 'numbered' ? (
        <ol className="mt-8 grid list-none gap-6 sm:grid-cols-3">{items}</ol>
      ) : (
        <ul className="mt-8 grid list-none gap-6 sm:grid-cols-3">{items}</ul>
      )}
    </section>
  )
}

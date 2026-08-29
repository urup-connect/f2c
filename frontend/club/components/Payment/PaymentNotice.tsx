import Link from 'next/link'
import { PAYMENT_COPY } from '@/lib/payment-content'

type Notice = {
  readonly heading: string
  readonly body: readonly string[]
}

/**
 * A heading, a paragraph or two, and a way back — for the four payment screens that are exactly
 * that: the link that is no longer valid, the failure that is ours, the return from a completed
 * payment, and the return from a cancelled one.
 *
 * One component rather than four near-identical pages, because the difference between them is the
 * wording and nothing else, and four copies of the same markup is four places for the heading level
 * or the focus ring to drift.
 *
 * A Server Component with no state. The heading is the first thing in the document, so it is
 * reached without a focus script — the same reason `SubmissionOutcome` is built this way — and the
 * whole screen works with JavaScript switched off.
 */
export const PaymentNotice = ({
  notice,
  reference,
}: {
  notice: Notice
  /** The eight-character error reference, when there is a fault of ours to quote. */
  reference?: string
}) => (
  <>
    <h1 className="font-display text-3xl tracking-display text-forest-green">{notice.heading}</h1>

    {notice.body.map((line) => (
      <p key={line} className="mt-4 font-sans text-base leading-relaxed text-foreground">
        {line}
      </p>
    ))}

    {reference ? (
      <p className="mt-4 font-sans text-sm text-foreground">
        {PAYMENT_COPY.unusable.reference}: <code>{reference}</code>
      </p>
    ) : null}

    <Link
      href="/"
      className="mt-6 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
    >
      {PAYMENT_COPY.back}
    </Link>
  </>
)

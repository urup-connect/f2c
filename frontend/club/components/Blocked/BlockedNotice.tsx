import Link from 'next/link'

import { BLOCKED_SHELL, type BlockedNotice as Notice } from '@/lib/blocked-content'

/**
 * A heading, two or three sentences, and — where there is something to ask for — a way to ask.
 *
 * A Server Component with no state. The heading is the first thing in the document, so the screen
 * is reached without a focus script, and it works with JavaScript switched off. The same reasoning
 * as `PaymentNotice`, which this deliberately does not reuse: that one always renders a link home
 * and always reads `PAYMENT_COPY` for its label, and both are wrong here.
 *
 * The mailto carries a subject and nothing else. **No account identifier, no membership status and
 * no reason.** A `mailto:` is assembled by the browser and handed to whatever mail client the
 * device has; putting a member's standing into it would leak a fact about them into a URL, a
 * clipboard and possibly a shared machine, to save them typing one line. The copy asks them to
 * quote their sign-up address instead, which is a thing they know and the club can match.
 */
export const BlockedNotice = ({
  notice,
  supportEmail,
}: {
  notice: Notice
  supportEmail: string
}) => (
  <>
    <h1 className="font-display text-3xl tracking-display text-forest-green">{notice.heading}</h1>

    {notice.body.map((line) => (
      <p key={line} className="mt-4 font-sans text-base leading-relaxed text-foreground">
        {line}
      </p>
    ))}

    {notice.contact ? (
      <a
        href={`mailto:${supportEmail}?subject=${encodeURIComponent(BLOCKED_SHELL.subject)}`}
        className="mt-6 inline-block underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        {notice.contact}
      </a>
    ) : null}

    <p className="mt-6 font-sans text-sm text-foreground">
      <Link
        href="/"
        className="underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        {BLOCKED_SHELL.back}
      </Link>
    </p>
  </>
)

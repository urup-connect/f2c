import Link from 'next/link'

import { Wordmark } from '@/components/Brand/Wordmark'
import { LANDING } from '@/lib/landing-content'

type FooterProps = {
  /**
   * The year in the copyright line.
   *
   * A **parameter**, never `new Date()` in here. Two reasons and both are ordinary: a component that
   * reads the clock cannot be tested without stubbing one, and a year baked into a statically
   * rendered page is a year that goes stale on the first of January. The page passes it at request
   * time.
   */
  year: number
}

/**
 * The foot of the public pages.
 *
 * The legal link goes to the index rather than to three named documents, because **which documents
 * exist is Django's answer, not this component's** — the store's terms and privacy notice are not
 * published yet, and a footer listing them by name would link to pages that 404. See
 * `lib/documents.ts`.
 */
export const Footer = ({ year }: FooterProps) => (
  <footer className="mt-8 border-t-2 border-border bg-surface-muted">
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <Wordmark />

      <p className="max-w-2xl font-sans text-sm leading-relaxed text-muted-foreground">
        {LANDING.footer.platformNote}
      </p>

      <div className="flex flex-wrap items-center gap-6">
        <Link
          href="/legal"
          className="font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
        >
          {LANDING.footer.legalLabel}
        </Link>

        <p className="font-sans text-sm text-muted-foreground">
          {`© ${year} ${LANDING.footer.copyrightSuffix}`}
        </p>
      </div>
    </div>
  </footer>
)

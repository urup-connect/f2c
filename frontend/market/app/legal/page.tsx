import type { Metadata } from 'next'
import Link from 'next/link'

import { Footer } from '@/components/Landing/Footer'
import { DocumentList } from '@/components/Legal/DocumentList'
import { legalList } from '@/lib/documents'
import { LEGAL } from '@/lib/legal-content'
import { getPublishedDocuments } from '@/lib/server-api'

export const metadata: Metadata = {
  title: LEGAL.title,
  description: LEGAL.standfirst,
  /*
   * The second of the two indexable routes — see `lib/seo.ts`. A shopper looking for the store's terms
   * should be able to find them in a search engine without an account, which is the whole reason the
   * endpoint behind this page is unauthenticated.
   */
  robots: { index: true, follow: true },
}

/*
 * Never statically rendered. Which documents exist, and at which revision, is Django's answer and it
 * changes when a revision is published — a page built at deploy time would keep serving the revision
 * that was in force then, and a document's effective date is exactly the kind of thing that must not be
 * stale.
 */
export const dynamic = 'force-dynamic'

/**
 * The store's terms, privacy notice and data policy, at the revision in force.
 *
 * **Nothing is published yet, and this page is written for that.** The endpoint is built and
 * storefront-scoped; the store's own documents are an item on `design/todo.md` Block B. So the page has
 * three states, and `lib/documents.ts` keeps them apart: documents listed, nothing published, or the
 * API unreachable. Collapsing the last two would tell a shopper the store has no privacy notice on a day
 * when it has one and the network was down.
 *
 * The documents are the market's own and never the club's, by decision rather than by omission — no
 * document is ever shared between the two storefronts, which is why `storefront` is non-null on the
 * model and why the scoping is by host. `design/verticals.md` section 6.
 */
export default async function LegalPage() {
  const list = legalList(await getPublishedDocuments())

  return (
    <>
      <main className="flex flex-1 flex-col">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
          <h1 className="font-display text-3xl tracking-display text-leaf">{LEGAL.title}</h1>
          <p className="max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
            {LEGAL.standfirst}
          </p>

          <div className="mt-4">
            <DocumentList list={list} />
          </div>

          <Link
            href="/"
            className="mt-4 inline-block font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
          >
            {LEGAL.back}
          </Link>
        </div>
      </main>

      <Footer year={new Date().getFullYear()} />
    </>
  )
}

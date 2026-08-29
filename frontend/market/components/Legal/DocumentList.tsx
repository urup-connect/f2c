import { revisionLine, type LegalList } from '@/lib/documents'
import { LEGAL } from '@/lib/legal-content'

type DocumentListProps = {
  list: LegalList
}

/**
 * The store's legal documents, or the reason there are none on screen.
 *
 * **Three states, three different things said.** Django unreachable and Django answering with nothing
 * are not the same event, and the copy in `legal-content.ts` keeps them apart: the first says the
 * fault is ours, the second says the documents have not been written yet. Telling a shopper the store
 * has no privacy notice when in fact the API was down would be an untrue statement about a legal
 * obligation.
 *
 * Each row links to the file Django serves, at the revision in force, with the revision and its
 * effective date beneath. The link text names the document — a list of links all reading "Read" is
 * unusable from a screen reader's list of controls.
 *
 * `rel="noopener"` and no `target`: these open in place. A PDF that hijacks the tab is worse than one
 * a visitor has to come back from, and the back button is what everybody expects.
 */
export const DocumentList = ({ list }: DocumentListProps) => {
  if (list.state === 'unavailable') {
    return (
      <div role="alert" className="rounded-card border-2 border-error bg-surface p-6">
        <h2 className="font-display text-xl tracking-display text-error">
          {LEGAL.unavailableHeading}
        </h2>
        <p className="mt-2 font-sans text-base leading-relaxed text-foreground">
          {LEGAL.unavailableBody}
        </p>
      </div>
    )
  }

  if (list.state === 'none') {
    return (
      <div className="rounded-card border-2 border-dashed border-border bg-surface-muted p-6">
        <h2 className="font-display text-xl tracking-display text-leaf">{LEGAL.noneHeading}</h2>
        <p className="mt-2 font-sans text-base leading-relaxed text-foreground">{LEGAL.noneBody}</p>
      </div>
    )
  }

  return (
    <ul className="flex list-none flex-col gap-4">
      {list.documents.map((document) => (
        <li
          key={document.document}
          className="rounded-card border-2 border-border bg-surface p-6"
        >
          <h2 className="font-display text-xl tracking-display text-leaf">{document.title}</h2>

          <p className="mt-1 font-sans text-sm text-muted-foreground">
            {revisionLine(document, LEGAL.versionLabel, LEGAL.fromLabel)}
          </p>

          <a
            href={document.url}
            rel="noopener"
            className="mt-4 inline-block font-sans text-base text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
          >
            {`${LEGAL.readPrefix} ${document.title}`}
          </a>
        </li>
      ))}
    </ul>
  )
}

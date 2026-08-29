import { CLUB_CONSENT_VALUE } from '@/lib/club-documents'

type ConsentCheckboxProps = {
  /** The form field name. Also the basis of every id on the group, as with `TextField`. */
  name: string
  /** The sentence the member is agreeing to. The checkbox's accessible name. */
  label: string
  /** The link's own words, which say what the document is and that it opens in a new tab. */
  linkText: string
  /** Where the document lives. A prop: this component knows nothing about environments. */
  href: string
  /** The hidden field carrying the revision this box was rendered against, and its name. */
  versionName: string
  version: string
  /** The refusal message, when this agreement has one. */
  error?: string
}

const BOX =
  'mt-1 h-5 w-5 shrink-0 rounded-control border-2 bg-surface accent-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * One club document: the box a member ticks, the link that opens the document, and the refusal.
 *
 * **The link is a sibling of the label, never inside it.** A link inside a checkbox label both
 * follows the link and toggles the checkbox, so a member who opens the rules to read them comes
 * back to a box that has ticked itself — an agreement nobody made. It is attached to the checkbox
 * with `aria-describedby` instead, so a screen reader still reaches it from the control.
 *
 * `target="_blank"` because a member reading a long document must not lose a form they have already
 * filled in, and the link text says so out loud. `rel="noopener noreferrer"`: `noopener` because a
 * page opened this way can otherwise reach back into the one that opened it, `noreferrer` so the
 * document host is not told which page the reader came from.
 *
 * No `required` attribute, like every other control on this screen: it would hand a browser-worded
 * bubble to a member with JavaScript and our own wording to a member without.
 *
 * See design/features/club-document-agreements-at-sign-up.md sections 5 and 8.
 */
export const ConsentCheckbox = ({
  name,
  label,
  linkText,
  href,
  versionName,
  version,
  error,
}: ConsentCheckboxProps) => {
  const id = `member-${name}`
  const linkId = `${id}-document`
  const errorId = `${id}-error`

  const describedBy = [linkId, error ? errorId : null].filter(Boolean).join(' ')

  return (
    <div className="flex flex-col gap-1">
      {/*
        * The revision this box was rendered against, posted whether or not the box is ticked.
        *
        * Hidden rather than derived on the server, because the server would derive whatever is in
        * force at submit time — which is the value that cannot be trusted to say what the member
        * read. A revision published between the render and the submit is caught by comparing the
        * two, and posting nothing would make that comparison impossible.
        *
        * Not a security control, and not treated as one: the server checks it against what is
        * actually published, so a forged value gets refused rather than believed.
        */}
      <input type="hidden" name={versionName} value={version} readOnly />

      <div className="flex items-start gap-3">
        <input
          id={id}
          name={name}
          type="checkbox"
          value={CLUB_CONSENT_VALUE}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`${BOX} ${error ? 'border-error' : 'border-border'}`}
        />

        <label htmlFor={id} className="font-sans text-base text-foreground">
          {label}
        </label>
      </div>

      {/* Indented to the label, so the link reads as belonging to this agreement and no other. */}
      <p id={linkId} className="pl-8 font-sans text-sm">
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-foreground underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
        >
          {linkText}
        </a>
      </p>

      {error ? (
        <p id={errorId} className="pl-8 font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </div>
  )
}

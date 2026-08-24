import { ConsentCheckbox } from './ConsentCheckbox'
import { clubVersionField } from '@/lib/club-documents'
import { MEMBER_CONSENT_FIELDS } from '@/lib/member-details'
import type { MemberDetailsField } from '@/lib/member-details'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'
import type { ClubDocumentRevisions } from '@/lib/club-documents'

type ConsentGroupProps = {
  /**
   * The revisions in force, keyed by document so a link cannot reach the wrong box.
   *
   * Carries the address, the version and the sentence to render. All three come from Django: the
   * version because a revision is published rather than deployed, and the sentence because Django
   * records a digest of it against every agreement.
   */
  revisions: ClubDocumentRevisions
  /** Refusal messages by field, as the form already holds them. */
  messages?: ReadonlyMap<MemberDetailsField, string>
}

/**
 * The three club documents a joining member agrees to.
 *
 * A `fieldset` with a legend, so a screen reader announces what the three boxes have in common
 * before reading the first of them — three agreement sentences with no grouping read as three
 * unrelated questions.
 *
 * The notice above them is not decoration. Nothing on this screen is kept, agreements included, and
 * a tick against "I have read and agree" otherwise implies an agreement was formed and recorded.
 *
 * One box per document, driven by the same mapping the validation uses, so a document can never
 * appear on screen without a rule behind it or the other way round.
 *
 * See design/features/sign-up.md section 5.
 */
export const ConsentGroup = ({ revisions, messages }: ConsentGroupProps) => (
  <fieldset className="flex flex-col gap-4 border-0 p-0">
    <legend className="font-sans text-base font-medium text-foreground">
      {MEMBER_DETAILS_COPY.consents.legend}
    </legend>

    <p className="font-sans text-sm leading-relaxed text-muted-foreground">
      {MEMBER_DETAILS_COPY.consents.notice}
    </p>

    {MEMBER_CONSENT_FIELDS.map(({ field, document }) => (
      <ConsentCheckbox
        key={field}
        name={field}
        label={revisions[document].consentText}
        linkText={MEMBER_DETAILS_COPY.consents.agreements[field].link}
        href={revisions[document].url}
        versionName={clubVersionField(document)}
        version={revisions[document].version}
        error={messages?.get(field)}
      />
    ))}
  </fieldset>
)

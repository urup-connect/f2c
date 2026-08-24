import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/**
 * What POPIA section 18 requires a person to be told when their information is collected: who is
 * asking, what for, whether they have to, and what follows if they do not.
 *
 * Rendered above the fields, never below them. A visitor should know the club is closed and that
 * nothing is kept *before* typing an identity number, not after — that ordering is the whole
 * mitigation for risk 1 in the design doc, and it is not a layout preference.
 *
 * This is a legal instrument rather than marketing text, and it is pending legal sign-off. See
 * design/features/member-details-at-sign-up.md section 9 and section 10, risk 10.
 */
export const CollectionNotice = () => (
  <div className="flex flex-col gap-3">
    {MEMBER_DETAILS_COPY.collectionNotice.map((paragraph) => (
      <p key={paragraph} className="font-sans text-sm leading-relaxed text-muted-foreground">
        {paragraph}
      </p>
    ))}
  </div>
)

'use client'

import { useEffect, useRef } from 'react'
import {
  MEMBER_DETAILS_COPY,
  memberDetailsFieldLabel,
  memberDetailsRefusalMessage,
} from '@/lib/member-details-content'
import type { MemberDetailsFieldRefusal } from '@/lib/member-details'

type ErrorSummaryProps = {
  refusals: readonly MemberDetailsFieldRefusal[]
  /** The date on file, written out, for the one message that names it. */
  dateOfBirth: string
}

/**
 * Every refusal in one place, at the top of the form, with a link to each field.
 *
 * It takes focus when it appears. A refusal on a form this long is otherwise announced somewhere
 * a visitor is not looking and reached only by hunting; moving focus here puts the whole list in
 * front of a screen reader and one Tab away from the first field that needs fixing.
 *
 * See design/features/member-details-at-sign-up.md section 8.
 */
export const ErrorSummary = ({ refusals, dateOfBirth }: ErrorSummaryProps) => {
  const heading = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (refusals.length > 0) heading.current?.focus()
  }, [refusals])

  if (refusals.length === 0) return null

  return (
    <div
      ref={heading}
      role="alert"
      tabIndex={-1}
      className="rounded-control border-2 border-error bg-surface p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
    >
      <h2 className="font-sans text-base font-medium text-error">
        {MEMBER_DETAILS_COPY.errorSummaryHeading}
      </h2>

      <ul className="mt-2 flex flex-col gap-1">
        {refusals.map(({ field, reason }) => (
          <li key={field}>
            <a
              href={`#member-${field}`}
              className="font-sans text-sm text-foreground underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            >
              {memberDetailsFieldLabel(field)} — {memberDetailsRefusalMessage(reason, dateOfBirth)}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

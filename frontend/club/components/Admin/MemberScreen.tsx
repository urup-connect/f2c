'use client'

import { useState } from 'react'
import Link from 'next/link'

import { ClubCard } from '@/components/Club/ClubCard'
import { DetailList } from '@/components/Club/DetailList'
import type { DetailRow } from '@/lib/club-account'
import { type Member, type MemberSubmission } from '@/lib/member-register'
import { saveMember } from '@/lib/member-register-api'
import {
  MEMBER_MEMBERSHIP,
  MEMBER_RECORD,
} from '@/lib/member-register-content'
import { MemberForm } from './MemberForm'
import { MemberIdentityCard } from './MemberIdentityCard'
import { MemberStandingCard } from './MemberStandingCard'

type MemberScreenProps = {
  /** The record as the server rendered it. The starting state, not a fetch trigger. */
  initial: Member
  /** The signed-in administrator's own id, so the standing card never offers self-suspension. */
  viewerId: string
  /** Back to the register, passed in so the component holds no knowledge of the URL scheme. */
  registerHref: string
}

/**
 * One member's record: their details, their standing, their subscription, their document.
 *
 * The screen owns the `Member` and hands it down, so a suspension made in one
 * card redraws the heading and the facts in another without a re-fetch — every
 * write on this router answers with the whole record for exactly that reason.
 * `StrainScreen` holds the same shape.
 *
 * ## Why the form is remounted on an external write and not on its own save
 *
 * `externalWrites` keys the form. A suspension changes the record underneath a
 * form the administrator may be mid-edit in, and the honest thing is to redraw
 * it from what the server now holds. The form's *own* save must not remount it —
 * it already reconciles its fields itself, and a remount there would throw away
 * the focus and the scroll position of somebody who had just pressed save.
 *
 * ## The read-only case renders a banner instead of the form
 *
 * `editable` comes from the API and is false for two records: one erased at the
 * member's request, and a cultivator's sharing member. Both are readable — the
 * register lists them and hiding them would make it disagree with every other
 * count of accounts — and neither may be written to. A banner says which, and
 * the form is absent rather than disabled: a form full of inert inputs invites
 * somebody to work out how to enable them.
 */
export const MemberScreen = ({ initial, viewerId, registerHref }: MemberScreenProps) => {
  const [member, setMember] = useState<Member>(initial)
  const [externalWrites, setExternalWrites] = useState(0)

  /** A write from outside the form: the record moved, so the form is redrawn from it. */
  const applyExternal = (next: Member) => {
    setMember(next)
    setExternalWrites((count) => count + 1)
  }

  const submit = (submission: MemberSubmission) => saveMember(member.id, submission)

  const facts: readonly DetailRow[] = [
    { key: 'role', label: MEMBER_RECORD.roleFact, value: member.role_label },
    { key: 'status', label: MEMBER_RECORD.statusFact, value: member.status_label },
    { key: 'joined', label: MEMBER_RECORD.joinedFact, value: member.created_at.slice(0, 10) },
    { key: 'updated', label: MEMBER_RECORD.updatedFact, value: member.updated_at.slice(0, 10) },
    {
      key: 'last-seen',
      label: MEMBER_RECORD.lastSeenFact,
      // `null` would render as "Not on file", which is wrong: the club holds the
      // fact, and the fact is that they never have. Said in its own words.
      value: member.last_login === null
        ? MEMBER_RECORD.neverSeen
        : member.last_login.slice(0, 10),
    },
    {
      key: 'birth',
      label: MEMBER_RECORD.birthFact,
      value: member.date_of_birth,
    },
    ...(member.registered_by === null
      ? []
      : [
          {
            key: 'registered-by',
            label: MEMBER_RECORD.registeredByFact,
            value: member.registered_by,
          },
        ]),
  ]

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10">
      <div>
        <Link
          href={registerHref}
          className="font-sans text-sm text-forest-green underline decoration-2 underline-offset-4 hover:text-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
        >
          {MEMBER_RECORD.backLabel}
        </Link>

        <p className="mt-6 font-sans text-sm uppercase tracking-label text-muted-foreground">
          {MEMBER_RECORD.heading}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {member.display_name}
        </h1>
      </div>

      {member.editable ? (
        <MemberForm
          key={externalWrites}
          member={member}
          onSubmit={submit}
          onSaved={setMember}
        />
      ) : (
        <ClubCard heading={MEMBER_RECORD.detailsHeading}>
          <p role="status" className="font-sans text-base leading-relaxed text-foreground">
            {member.erased ? MEMBER_RECORD.readOnlyErased : MEMBER_RECORD.readOnlySharing}
          </p>
        </ClubCard>
      )}

      <ClubCard heading={MEMBER_RECORD.factsHeading}>
        <DetailList rows={facts} />

        {member.date_of_birth === null ? null : (
          <p className="mt-4 font-sans text-sm text-muted-foreground">
            {/*
              * Which of the two the date of birth is, said in words. It comes
              * off the identity number at sign-up and nobody has seen a
              * document -- `date_of_birth_verified_at` is what records that
              * somebody has, and it is the field the club would rely on later.
              */}
            {member.date_of_birth_verified_at === null
              ? MEMBER_RECORD.birthUnverified
              : MEMBER_RECORD.birthVerified}
          </p>
        )}
      </ClubCard>

      <ClubCard heading={MEMBER_MEMBERSHIP.heading} standfirst={MEMBER_MEMBERSHIP.standfirst}>
        {member.membership.status_label === null ? (
          <p className="font-sans text-base italic text-muted-foreground">
            {MEMBER_MEMBERSHIP.none}
          </p>
        ) : (
          <DetailList
            rows={[
              {
                key: 'subscription-status',
                label: MEMBER_MEMBERSHIP.statusLabel,
                value: member.membership.status_label,
              },
              {
                key: 'subscription-paid-until',
                label: MEMBER_MEMBERSHIP.paidUntilLabel,
                value: member.membership.paid_until,
              },
            ]}
          />
        )}
      </ClubCard>

      <MemberStandingCard
        member={member}
        viewerId={viewerId}
        onChanged={applyExternal}
      />

      {/*
        * Keyed on the same counter, and for a second reason besides the form's.
        * The identity card holds a revealed number in state, and a write from
        * another card is a moment to let go of it: the record it was read
        * against has moved, and a plaintext identity number surviving a
        * suspension is a value on screen for longer than anybody asked for.
        */}
      <MemberIdentityCard key={`identity-${externalWrites}`} member={member} />
    </div>
  )
}

'use client'

import { useState } from 'react'

import { ClubCard } from '@/components/Club/ClubCard'
import { canReinstate, canSuspend, type Member } from '@/lib/member-register'
import { reinstateMember, suspendMember } from '@/lib/member-register-api'
import { MEMBER_STANDING } from '@/lib/member-register-content'

type MemberStandingCardProps = {
  member: Member
  /** The signed-in administrator's own id, so the screen never offers self-suspension. */
  viewerId: string
  /** Told the record that came back, so the rest of the screen redraws at the new standing. */
  onChanged: (member: Member) => void
}

const DESTRUCTIVE =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-error px-6 font-sans text-base font-medium text-error transition-colors hover:bg-error hover:text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error disabled:opacity-60'

const SECONDARY =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-border px-6 font-sans text-base font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60'

/**
 * Whether this account may sign in, and the two acts that change the answer.
 *
 * ## Suspension confirms; reinstatement does not
 *
 * They are not symmetrical acts. Suspending signs a member out of every device
 * immediately and locks them out until somebody lifts it — an accidental press
 * is a person unable to reach the club with no idea why. Lifting a suspension
 * restores what they had, so a confirmation step there would be ceremony around
 * an act with no victim. `RetireCard` draws the same line for the same reason.
 *
 * ## The button an administrator may not press is absent, not disabled
 *
 * Nobody can suspend their own account: it signs them out on the way and they
 * cannot sign back in to undo it. The API refuses it, and this refuses to offer
 * it — with the reason said in words, because a control that is simply missing
 * reads as a screen that failed to draw.
 *
 * ## There is no delete, and the card says so
 *
 * Erasure is a POPIA act, it is irreversible, and it lives in the back office as
 * an explicit action rather than a button beside a form. A card that offered
 * both would put "suspend" and "erase for ever" a pixel apart.
 */
export const MemberStandingCard = ({
  member,
  viewerId,
  onChanged,
}: MemberStandingCardProps) => {
  const [confirming, setConfirming] = useState(false)
  const [working, setWorking] = useState(false)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const suspendable = canSuspend(member, viewerId)
  const reinstatable = canReinstate(member)
  const isSelf = member.id === viewerId

  const act = async (
    call: () => ReturnType<typeof suspendMember>,
    success: string,
  ) => {
    setWorking(true)
    setFailure(null)
    const result = await call()
    setWorking(false)
    setConfirming(false)

    if (result.status === 'saved') {
      onChanged(result.record)
      setOutcome(success)
      return
    }

    setOutcome(null)
    // A refusal's own sentence where there is one -- "you cannot suspend your
    // own account" is more use than "that could not be done just now" -- and the
    // generic line only for a call that never reached a decision.
    setFailure(
      result.status === 'refused' ? result.refusal.detail : MEMBER_STANDING.failed,
    )
  }

  return (
    <ClubCard heading={MEMBER_STANDING.heading} standfirst={MEMBER_STANDING.standfirst}>
      <div className="flex flex-col gap-4">
        <p className="font-sans text-base text-foreground">
          {member.status_label}
        </p>

        {member.status === 'suspended' ? (
          <p className="font-sans text-sm text-muted-foreground">
            {MEMBER_STANDING.suspended}
          </p>
        ) : null}

        {isSelf ? (
          <p className="font-sans text-sm text-muted-foreground">
            {MEMBER_STANDING.cannotSuspendSelf}
          </p>
        ) : null}

        {confirming ? (
          <div className="rounded-control border-2 border-error p-4">
            <h3 className="font-display text-lg tracking-display text-error">
              {MEMBER_STANDING.confirmSuspendHeading}
            </h3>
            <p className="mt-2 font-sans text-sm leading-relaxed text-foreground">
              {MEMBER_STANDING.confirmSuspendBody}
            </p>

            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                disabled={working}
                onClick={() =>
                  act(() => suspendMember(member.id), MEMBER_STANDING.suspendedNow)
                }
                className={DESTRUCTIVE}
              >
                {working ? MEMBER_STANDING.suspending : MEMBER_STANDING.confirmSuspendAction}
              </button>

              <button
                type="button"
                disabled={working}
                onClick={() => setConfirming(false)}
                className={SECONDARY}
              >
                {MEMBER_STANDING.confirmCancel}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            {suspendable ? (
              <button
                type="button"
                onClick={() => setConfirming(true)}
                className={DESTRUCTIVE}
              >
                {MEMBER_STANDING.suspendLabel}
              </button>
            ) : null}

            {reinstatable ? (
              <button
                type="button"
                disabled={working}
                onClick={() =>
                  act(() => reinstateMember(member.id), MEMBER_STANDING.reinstated)
                }
                className={SECONDARY}
              >
                {working ? MEMBER_STANDING.reinstating : MEMBER_STANDING.reinstateLabel}
              </button>
            ) : null}
          </div>
        )}

        {failure === null ? null : (
          <p
            role="alert"
            className="font-sans text-sm font-medium text-error"
          >
            {failure}
          </p>
        )}

        {/* Always present, so a screen reader is already watching it. */}
        <p role="status" className="font-sans text-sm text-muted-foreground">
          {outcome ?? ''}
        </p>
      </div>
    </ClubCard>
  )
}

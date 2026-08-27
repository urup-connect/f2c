'use client'

import { useState } from 'react'

import { ClubCard } from '@/components/Club/ClubCard'
import { TextField } from '@/components/SignUp/TextField'
import {
  checkMember,
  memberHasChanges,
  memberInputFrom,
  refusalFor,
  refusalsFromApi,
  type Member,
  type MemberFieldRefusal,
  type MemberInput,
  type MemberSubmission,
} from '@/lib/member-register'
import type { MemberOutcome } from '@/lib/member-register-api'
import { MEMBER_RECORD } from '@/lib/member-register-content'
import { filterSaMobileInput, formatSaMobileNumber } from '@/lib/sa-mobile-number'

type MemberFormProps = {
  /** The record as stored. The form's starting values, and what "changed" is measured against. */
  member: Member
  /** Sends the submission. Never throws — see `member-register-api.ts`. */
  onSubmit: (submission: MemberSubmission) => Promise<MemberOutcome<Member>>
  /** Told the record that came back, so the screen's other cards can redraw. */
  onSaved: (member: Member) => void
}

const ACTION =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-6 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60'

/**
 * The five details an administrator may correct on a member's record.
 *
 * Five fields, and what is *not* here is as much the design as what is. The role
 * is appointed in the back office, because handing out authority over other
 * members' records is not a form field. The standing moves through the card
 * below this one, which confirms first and ends the member's sessions. The
 * identity number is write-only. The date of birth comes off the document. Each
 * exclusion has its reason recorded in `app/membership/administration.py`.
 *
 * ## Uncontrolled inputs, remounted per save
 *
 * `TextField` is uncontrolled and reports on blur — the same field sign-up uses,
 * so a mobile number typed here is grouped and filtered exactly as it is there.
 * The consequence is that the DOM holds the value, so after a save the fields
 * are remounted with `key` to show what the server actually stored: an
 * administrator who typed `082 123 4567` should see `+27 82 123 4567` come back,
 * not the string they typed.
 *
 * ## Two sources of refusal, one renderer
 *
 * `checkMember` refuses what a browser can decide. The API refuses what it
 * cannot — whether another account already holds this address, nickname or
 * mobile number, and whether the record may be written to at all. Both arrive as
 * `MemberFieldRefusal`, keyed by the API's own field names, so one renderer
 * handles both and there is no translation table to keep in step.
 *
 * ## The read-only case is a banner, not a disabled form
 *
 * An erased account and a sharing member cannot be written to. The screen says
 * which and why, and does not render the form at all — a form full of disabled
 * inputs invites somebody to work out how to enable them, and reads as a bug
 * rather than as a rule.
 */
export const MemberForm = ({ member, onSubmit, onSaved }: MemberFormProps) => {
  const [input, setInput] = useState<MemberInput>(() => memberInputFrom(member))
  const [stored, setStored] = useState<Member>(member)
  const [refusals, setRefusals] = useState<readonly MemberFieldRefusal[]>([])
  const [rejection, setRejection] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isSaved, setIsSaved] = useState(false)
  const [saveCount, setSaveCount] = useState(0)

  const changed = memberHasChanges(input, stored)

  const set = (field: keyof MemberInput) => (value: string) => {
    setInput((current) => ({ ...current, [field]: value }))
    setIsSaved(false)
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()

    const checked = checkMember(input)
    if (checked.status === 'invalid') {
      setRefusals(checked.refusals)
      setRejection(MEMBER_RECORD.refusedSummary)
      setIsSaved(false)
      return
    }

    setIsSaving(true)
    const outcome = await onSubmit(checked.submission)
    setIsSaving(false)

    if (outcome.status === 'saved') {
      onSaved(outcome.record)
      setStored(outcome.record)
      // From the record as stored, not from what was typed. The mobile number
      // and both names come back normalised, and the fields are remounted below
      // so the administrator sees what the club now holds.
      setInput(memberInputFrom(outcome.record))
      setRefusals([])
      setRejection(null)
      setSaveCount((count) => count + 1)
      setIsSaved(true)
      return
    }

    setIsSaved(false)

    if (outcome.status === 'refused') {
      setRefusals(refusalsFromApi(outcome.refusal.fields ?? {}))
      setRejection(outcome.refusal.detail)
      return
    }

    setRefusals([])
    setRejection(MEMBER_RECORD.failed)
  }

  return (
    <ClubCard
      heading={MEMBER_RECORD.detailsHeading}
      standfirst={MEMBER_RECORD.detailsStandfirst}
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <TextField
            key={`member-first-${saveCount}`}
            name="first-name"
            label={MEMBER_RECORD.firstNameLabel}
            defaultValue={input.firstName}
            autoComplete="off"
            error={refusalFor(refusals, 'first_name')}
            onBlurValue={set('firstName')}
          />

          <TextField
            key={`member-last-${saveCount}`}
            name="last-name"
            label={MEMBER_RECORD.lastNameLabel}
            defaultValue={input.lastName}
            autoComplete="off"
            error={refusalFor(refusals, 'last_name')}
            onBlurValue={set('lastName')}
          />

          <TextField
            key={`member-nickname-${saveCount}`}
            name="nickname"
            label={MEMBER_RECORD.nicknameLabel}
            hint={MEMBER_RECORD.nicknameHint}
            defaultValue={input.nickname}
            autoComplete="off"
            error={refusalFor(refusals, 'nickname')}
            onBlurValue={set('nickname')}
          />

          <TextField
            key={`member-email-${saveCount}`}
            name="email"
            label={MEMBER_RECORD.emailLabel}
            hint={MEMBER_RECORD.emailHint}
            defaultValue={input.email}
            autoComplete="off"
            error={refusalFor(refusals, 'email')}
            onBlurValue={set('email')}
          />

          {/*
            * The same filtering and grouping sign-up applies, from the same
            * module. A number an administrator types has to become the same
            * stored value a member's own would -- and `formatSaMobileNumber`
            * running on blur is what makes the field show the club's form rather
            * than whatever was pasted into it.
            */}
          <TextField
            key={`member-mobile-${saveCount}`}
            name="mobile"
            label={MEMBER_RECORD.mobileLabel}
            defaultValue={input.mobile}
            autoComplete="off"
            inputMode="numeric"
            filterOnInput={filterSaMobileInput}
            formatOnBlur={formatSaMobileNumber}
            error={refusalFor(refusals, 'mobile')}
            onBlurValue={set('mobile')}
          />
        </div>

        {rejection === null ? null : (
          <p
            role="alert"
            className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
          >
            {rejection}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-4">
          <button type="submit" disabled={isSaving || !changed} className={ACTION}>
            {isSaving ? MEMBER_RECORD.saving : MEMBER_RECORD.save}
          </button>

          {/*
            * Always in the DOM, so a screen reader is already watching it when
            * the message arrives. An element that appears at the same moment as
            * its text is an element some readers announce and others do not.
            */}
          <p role="status" className="font-sans text-sm text-muted-foreground">
            {isSaved ? MEMBER_RECORD.saved : changed ? '' : MEMBER_RECORD.unchanged}
          </p>
        </div>
      </form>
    </ClubCard>
  )
}

'use client'

import { useState } from 'react'

import { Card } from '@/components/Ui/Card'
import { Feedback } from '@/components/Ui/Feedback'
import { TextField } from '@/components/Ui/TextField'
import {
  checkProfile,
  profileInputFrom,
  profileRefusalFor,
  readProfileForm,
  type ProfileField,
  type ProfileFieldRefusal,
} from '@/lib/profile'
import {
  refusalMessagesByField,
  saveProfile,
  type Profile,
} from '@/lib/profile-api'
import { filterSaMobileInput, formatSaMobileNumber } from '@/lib/sa-mobile-number'
import { PROFILE_COPY, PROFILE_REFUSAL_MESSAGES } from '@/lib/store-content'

type DetailsFormProps = {
  /** The record as the server rendered it. The form starts from it rather than fetching on mount. */
  initial: Profile
}

const PRIMARY =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf disabled:opacity-60'

/** Messages from the API, keyed by field. Empty except immediately after a refusal. */
type ApiMessages = Partial<Record<ProfileField, string>>

/**
 * The three fields a customer may change about themselves.
 *
 * **Uncontrolled inputs, read on submit.** The values live in the DOM and are read through
 * `readProfileForm`, so nothing re-renders while somebody types and the mobile field's blur-time
 * grouping does not fight a controlled value. It also means the form is exactly as testable as the
 * pure rules behind it — `checkProfile` sees a plain object either way.
 *
 * **Two sources of refusal, kept apart.** `checkProfile` refuses a value before it is sent, in our
 * wording; the API refuses things the form cannot know about — a mobile number already on another
 * account — in its own. Both render under the field they concern, and a local refusal wins where both
 * exist, because it is the one that stopped the request.
 *
 * The email address is shown and not editable. It is the sign-in identifier: changing it is changing
 * how somebody gets in, which is a different act with different checks, and `accounts/profile.py`
 * refuses it at the API. A disabled input would look like an oversight, so it is rendered as a
 * labelled value with the reason beside it.
 */
export const DetailsForm = ({ initial }: DetailsFormProps) => {
  const [profile, setProfile] = useState(initial)
  const [refusals, setRefusals] = useState<readonly ProfileFieldRefusal[]>([])
  const [apiMessages, setApiMessages] = useState<ApiMessages>({})
  const [problem, setProblem] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const input = readProfileForm(new FormData(event.currentTarget))

    setProblem(null)
    setNotice(null)
    setApiMessages({})

    const checked = checkProfile(input)

    if (checked.status === 'invalid') {
      setRefusals(checked.refusals)
      return
    }

    setRefusals([])
    setIsSaving(true)

    const outcome = await saveProfile(checked.submission)

    setIsSaving(false)

    if (outcome.status === 'saved') {
      setProfile(outcome.profile)
      setNotice(PROFILE_COPY.saved)
      return
    }

    if (outcome.status === 'refused') {
      setApiMessages(refusalMessagesByField(outcome.refusal))
      /*
       * The mobile number belonging to somebody else is the one refusal with its own sentence: the
       * value is a perfectly good number, so a message under the field saying it is invalid would be
       * wrong. Everything else falls back to the API's own `detail`, which `accounts/api.py` writes
       * to be read by the person it refuses.
       */
      setProblem(
        outcome.refusal.mobile_unavailable
          ? PROFILE_COPY.mobileUnavailable
          : outcome.refusal.detail || PROFILE_COPY.refused,
      )
      return
    }

    setProblem(PROFILE_COPY.failed)
  }

  const errorFor = (field: ProfileField): string | undefined => {
    const reason = profileRefusalFor(refusals, field)
    if (reason !== undefined) return PROFILE_REFUSAL_MESSAGES[reason]

    return apiMessages[field]
  }

  const values = profileInputFrom(profile)

  return (
    <Card heading={PROFILE_COPY.title} standfirst={PROFILE_COPY.standfirst}>
      <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <TextField
            name="firstName"
            label={PROFILE_COPY.firstNameLabel}
            defaultValue={values.firstName}
            autoComplete="given-name"
            error={errorFor('firstName')}
          />
          <TextField
            name="lastName"
            label={PROFILE_COPY.lastNameLabel}
            defaultValue={values.lastName}
            autoComplete="family-name"
            error={errorFor('lastName')}
          />
        </div>

        <TextField
          name="mobile"
          label={PROFILE_COPY.mobileLabel}
          hint={PROFILE_COPY.mobileHint}
          defaultValue={values.mobile}
          autoComplete="tel-national"
          inputMode="tel"
          filterOnInput={filterSaMobileInput}
          formatOnBlur={formatSaMobileNumber}
          error={errorFor('mobile')}
        />

        <div className="flex flex-col gap-1">
          <p className="font-sans text-base font-medium text-foreground">
            {PROFILE_COPY.emailLabel}
          </p>
          {/*
           * The address, or nothing. An erased account has no address, and `—` in its place reads as
           * a value rather than as an absence.
           */}
          <p className="font-sans text-base text-foreground">{profile.email ?? ''}</p>
          <p className="font-sans text-sm text-muted-foreground">{PROFILE_COPY.emailNote}</p>
        </div>

        <Feedback problem={problem} notice={notice} />

        <div>
          <button type="submit" disabled={isSaving} className={PRIMARY}>
            {isSaving ? PROFILE_COPY.saving : PROFILE_COPY.save}
          </button>
        </div>
      </form>
    </Card>
  )
}

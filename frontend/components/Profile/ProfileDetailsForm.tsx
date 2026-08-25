'use client'

import { useState } from 'react'

import { ClubCard } from '@/components/Club/ClubCard'
import { TextField } from '@/components/SignUp/TextField'
import { PROFILE_COPY } from '@/lib/club-content'
import { memberDetailsRefusalMessage } from '@/lib/member-details-content'
import {
  checkProfile,
  profileHasChanges,
  profileInputFrom,
  profileOnFile,
  profileRefusalFor,
  type ProfileFieldRefusal,
  type ProfileInput,
} from '@/lib/profile'
import { saveProfile, type Profile } from '@/lib/profile-api'
import { filterSaMobileInput, formatSaMobileNumber } from '@/lib/sa-mobile-number'

type ProfileDetailsFormProps = {
  profile: Profile
  /** Told the record as it now stands, whenever a save succeeds. */
  onSaved: (profile: Profile) => void
}

/**
 * The three fields a member may change about themselves.
 *
 * Four decisions worth reading.
 *
 * **The inputs stay uncontrolled, and what the component tracks is their value on blur.** That is
 * `TextField`'s own design and it is kept rather than worked around: it filters and groups by
 * writing to the DOM node, which a controlled value would fight. What this form needs on top is one
 * derived fact — has anything changed — and blur is a fine moment to learn it, because a member has
 * finished with a field by then and the save button is not reachable without leaving it.
 *
 * The cost is that the DOM holds the value and React cannot reset it, which matters exactly once: a
 * save normalises `Ann  Bee` to `Ann Bee`, and the input would go on showing the two spaces. So the
 * fields carry a `key` that changes on every successful save, remounting them against the record
 * that was actually stored. A remount rather than a controlled value, because it happens once per
 * save instead of once per keystroke.
 *
 * **Save is disabled while nothing has changed, and the reason is said out loud.** A button that
 * saves an identical record is a button that reports success for having done nothing, and a member
 * who pressed it learns nothing about whether their edit took.
 *
 * **Refusals come from the rules, not from the response.** `checkProfile` runs first and the API is
 * not called at all when it refuses, so the common case never leaves the browser. The API's own
 * refusals are still rendered — they are what a drift between the two rule sets looks like, and
 * pretending they cannot happen is how a member ends up staring at a form that will not save and
 * will not say why.
 *
 * **The mobile number is grouped on blur, exactly as at sign-up.** Same helpers, same reasons:
 * inserting separators under the caret has a screen reader re-announce the value on every
 * keystroke. `TextField` is reused rather than reimplemented, which is what keeps the two forms
 * behaving alike.
 */
export const ProfileDetailsForm = ({ profile, onSaved }: ProfileDetailsFormProps) => {
  const copy = PROFILE_COPY.details

  const [input, setInput] = useState<ProfileInput>(() => profileInputFrom(profile))
  const [refusals, setRefusals] = useState<readonly ProfileFieldRefusal[]>([])
  /** The one refusal that is not about a field: the number belongs to another account. */
  const [rejection, setRejection] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isSaved, setIsSaved] = useState(false)
  /**
   * Bumped on every successful save, and used as the fields' `key`.
   *
   * A counter rather than a value derived from the record: two saves can store the same thing --
   * a member correcting a number back to what it was -- and a key that did not change would leave
   * the inputs holding what was typed rather than what was stored.
   */
  const [saveCount, setSaveCount] = useState(0)

  const onFile = profileOnFile(profile)
  const changed = profileHasChanges(input, onFile)

  const set = (field: keyof ProfileInput) => (value: string) => {
    setInput((current) => ({ ...current, [field]: value }))
    // Any edit clears the outcome of the last save. Leaving "saved" on screen beside a field being
    // retyped would claim the new value is stored.
    setIsSaved(false)
    setRejection(null)
  }

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const checked = checkProfile(input)

    if (checked.status === 'invalid') {
      setRefusals(checked.refusals)
      setRejection(null)
      setIsSaved(false)
      return
    }

    setRefusals([])
    setRejection(null)
    setIsSaving(true)

    const outcome = await saveProfile(checked.submission)

    setIsSaving(false)

    if (outcome.status === 'saved') {
      onSaved(outcome.profile)
      setInput(profileInputFrom(outcome.profile))
      setSaveCount((count) => count + 1)
      setIsSaved(true)
      return
    }

    /*
     * Both remaining outcomes are shown as one sentence rather than marked up against a field. The
     * per-field refusals the API can send are for a caller that bypassed this form: everything a
     * member can type has already been refused by `checkProfile` above, so a refusal arriving here
     * means the two rule sets disagree, and the honest thing to show is what the API said.
     */
    setRejection(outcome.status === 'refused' ? outcome.refusal.detail : outcome.reason)
  }

  const messageFor = (field: keyof ProfileInput) => {
    const reason = profileRefusalFor(refusals, field)
    return reason ? memberDetailsRefusalMessage(reason) : undefined
  }

  return (
    <ClubCard heading={copy.heading}>
      <form onSubmit={submit} noValidate className="flex flex-col gap-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <TextField
            key={`firstName-${saveCount}`}
            name="firstName"
            label={copy.firstNameLabel}
            defaultValue={input.firstName}
            autoComplete="given-name"
            error={messageFor('firstName')}
            onBlurValue={set('firstName')}
          />

          <TextField
            key={`lastName-${saveCount}`}
            name="lastName"
            label={copy.lastNameLabel}
            defaultValue={input.lastName}
            autoComplete="family-name"
            error={messageFor('lastName')}
            onBlurValue={set('lastName')}
          />
        </div>

        <TextField
          key={`mobile-${saveCount}`}
          name="mobile"
          label={copy.mobileLabel}
          hint={copy.mobileHint}
          defaultValue={input.mobile}
          autoComplete="tel-national"
          inputMode="numeric"
          error={messageFor('mobile')}
          filterOnInput={filterSaMobileInput}
          formatOnBlur={formatSaMobileNumber}
          onBlurValue={set('mobile')}
        />

        {/*
          * Outside the `form` in meaning though not in markup: nothing here submits. Kept inside so
          * that the whole of "your details" is one card and one heading, rather than a member having
          * to notice that two of the six lines they came to check are somewhere else on the page.
          *
          * A description list, so a screen reader announces each label with its value. The same
          * choice `DetailList` and `IdentityCard` make, for the same reason.
          */}
        <div className="border-t-2 border-border pt-6">
          <h3 className="font-sans text-xs uppercase tracking-label text-muted-foreground">
            {copy.fixedHeading}
          </h3>

          <dl className="mt-4 grid gap-6 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <dt className="font-sans text-xs uppercase tracking-label text-muted-foreground">
                {copy.nicknameLabel}
              </dt>
              <dd className="font-sans text-base text-foreground">
                {profile.nickname || <span className="italic text-muted-foreground">{copy.blank}</span>}
              </dd>
            </div>

            <div className="flex flex-col gap-1">
              <dt className="font-sans text-xs uppercase tracking-label text-muted-foreground">
                {copy.emailLabel}
              </dt>
              <dd className="font-sans text-base break-words text-foreground">
                {/*
                  * `break-words`, unlike the nickname beside it. A long address on a narrow phone
                  * is the one value on this screen that can overflow its column, and an address
                  * running off the edge is one a member cannot check.
                  */}
                {profile.email || <span className="italic text-muted-foreground">{copy.blank}</span>}
              </dd>
            </div>
          </dl>

          <p className="mt-4 font-sans text-sm leading-relaxed text-muted-foreground">
            {copy.fixedNote}
          </p>
        </div>

        {rejection ? (
          <p
            role="alert"
            className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
          >
            {rejection}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={isSaving || !changed}
            className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
          >
            {isSaving ? copy.saving : copy.save}
          </button>

          {/*
            * `role="status"`, not `role="alert"`: both of these follow something the member did on
            * purpose, so neither should interrupt. The region is always in the DOM so that a
            * screen reader is watching it before it has anything to say -- one that appears
            * already containing text is often not announced at all.
            */}
          <p role="status" className="font-sans text-sm text-muted-foreground">
            {isSaved ? copy.saved : changed ? '' : copy.unchanged}
          </p>
        </div>
      </form>
    </ClubCard>
  )
}

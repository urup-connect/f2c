'use client'

import { useState } from 'react'
import Link from 'next/link'

import { ClubCard } from '@/components/Club/ClubCard'
import { TextField } from '@/components/SignUp/TextField'
import {
  DIFFICULTY_LEVELS,
  GROWING_ENVIRONMENTS,
  STRAIN_STATUSES,
  STRAIN_TYPES,
  blankStrainInput,
  checkStrain,
  refusalFor,
  refusalsFromApi,
  strainInputFrom,
  type Cultivator,
  type Strain,
  type StrainFieldRefusal,
  type StrainInput,
  type StrainSubmission,
  type Vocabularies,
} from '@/lib/strain-catalogue'
import type { SaveOutcome } from '@/lib/strain-catalogue-api'
import { STRAIN_FORM } from '@/lib/strain-catalogue-content'
import { PairField } from './PairField'
import { SelectField } from './SelectField'
import { TermPicker } from './TermPicker'
import { TextAreaField } from './TextAreaField'

type StrainFormProps = {
  /** The strain being edited, or null on the add screen. */
  strain: Strain | null
  vocabularies: Vocabularies
  cultivators: readonly Cultivator[]
  /** Where the vocabularies are managed, so a missing term is one click away. */
  termsHref: string
  /** Where to go back to. */
  catalogueHref: string
  /** Performs the write. The screen owns which endpoint that is. */
  onSubmit: (submission: StrainSubmission) => Promise<SaveOutcome<Strain>>
  /** Told the record as stored, whenever a save succeeds. */
  onSaved: (strain: Strain) => void
}

/**
 * The whole strain form, shared by the add screen and the edit screen.
 *
 * One component for both, because they differ in three things and agree on
 * eighteen: the heading, the verb on the button, and which endpoint the caller
 * hands over as `onSubmit`. Two files would be two copies of the fieldsets, and
 * a field added to one of them would go missing from the other.
 *
 * ## Where the rules are, and where they are not
 *
 * `checkStrain` runs first and the API is not called at all when it refuses, so
 * a mistyped percentage never leaves the browser. But — and this is the
 * difference from `ProfileDetailsForm`, which looks almost identical — the API's
 * refusals here are the *normal* path, not evidence of drift. Whether "OG Kush"
 * is already in the catalogue, whether an account holds the cultivator role, and
 * whether an aroma has been withdrawn are three questions no browser can answer,
 * and each has its own refusal keyed to its own field. So both sources feed one
 * list of `StrainFieldRefusal`, keyed the way the API keys them, and every field
 * renders whichever it has.
 *
 * ## Controlled inputs, and the one exception
 *
 * Everything here is controlled, unlike the profile form. Nothing on this screen
 * filters or reformats a value under the caret — the reason `TextField` stays
 * uncontrolled — and the form needs to know on every keystroke whether anything
 * has changed, so that the save button is not inert while somebody is typing
 * into the field above it.
 *
 * The exception is `TextField` itself, which is reused rather than reimplemented
 * and reports on blur. That is fine for the six short text fields it holds: a
 * name or a percentage is finished with by the time focus leaves it, and the
 * button becomes live one tab later. Reimplementing it as a controlled field
 * would be a second text input in the codebase that behaves *almost* like the
 * one at sign-up.
 *
 * ## Why the save button reports "nothing has changed"
 *
 * A button that saves an identical record reports success for having done
 * nothing, and an administrator who pressed it learns nothing about whether
 * their edit took. Same rule as the profile form, and the comparison is against
 * the submission rather than the input: two forms that differ only in a trailing
 * empty JSON row are the same record.
 */
export const StrainForm = ({
  strain,
  vocabularies,
  cultivators,
  termsHref,
  catalogueHref,
  onSubmit,
  onSaved,
}: StrainFormProps) => {
  const creating = strain === null

  const [input, setInput] = useState<StrainInput>(() =>
    strain === null ? blankStrainInput() : strainInputFrom(strain),
  )
  const [refusals, setRefusals] = useState<readonly StrainFieldRefusal[]>([])
  /** The sentence that is not about a field: a failure, or a refusal with no field. */
  const [rejection, setRejection] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isSaved, setIsSaved] = useState(false)
  /**
   * The record as last stored, for the changed-since comparison.
   *
   * Kept beside `input` rather than read from the `strain` prop, so that a
   * successful save makes the form clean again without the parent having to
   * re-render it with a new prop. On the add screen it starts null, and the
   * form is "changed" from the first keystroke.
   */
  const [stored, setStored] = useState<Strain | null>(strain)
  /**
   * Bumped on every successful save, and used as the `key` on every `TextField`.
   *
   * `TextField` is uncontrolled — the DOM holds the value, and React cannot
   * reset it. That matters exactly once per save: the service trims a name, so
   * saving `  Cheese  ` stores `Cheese` while the input goes on showing the
   * spaces, and the form would then read as changed against the record it just
   * wrote. Remounting the fields against what was actually stored fixes it, and
   * a remount is cheap at once per save where a controlled value would cost one
   * per keystroke. The same device `ProfileDetailsForm` uses, for the same
   * reason.
   *
   * A counter rather than something derived from the record: two saves can store
   * the same thing, and a key that did not change would leave the inputs holding
   * what was typed rather than what was stored.
   */
  const [saveCount, setSaveCount] = useState(0)

  const changed = hasChanges(input, stored)

  const set = <Field extends keyof StrainInput>(field: Field) =>
    (value: StrainInput[Field]) => {
      setInput((current) => ({ ...current, [field]: value }))
      // Any edit clears the outcome of the last save. Leaving "Saved." on screen
      // beside a field being retyped would claim the new value is stored.
      setIsSaved(false)
      setRejection(null)
    }

  const messageFor = (field: keyof StrainSubmission) => refusalFor(refusals, field)

  /*
   * The picker's options, plus the reserved cultivator when they are not among
   * them.
   *
   * That happens for one reason and it matters: `reservable_cultivators` excludes
   * an account that has left, and `Strain.exclusive_to` is `PROTECT` so the
   * reservation survives them — deliberately, because clearing it is what
   * releases the strain back to the club. Without this branch the `select` would
   * hold an id matching no option, render as its empty placeholder, and tell an
   * administrator the strain is open to all. The next save would then make that
   * true, having never said so.
   *
   * `reserved_to` is why the payload carries the name as well as the id. The
   * option is marked, and it is the only way to see the reservation in order to
   * clear it.
   */
  const departed =
    strain !== null &&
    strain.exclusive_to !== null &&
    !cultivators.some((cultivator) => cultivator.id === strain.exclusive_to)

  const exclusiveChoices = [
    ...(departed
      ? [
          {
            value: strain.exclusive_to as string,
            label: `${strain.reserved_to ?? ''} ${STRAIN_FORM.exclusiveDeparted}`.trim(),
          },
        ]
      : []),
    ...cultivators.map((cultivator) => ({
      value: cultivator.id,
      label: cultivator.display_name,
    })),
  ]

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const checked = checkStrain(input)

    if (checked.status === 'invalid') {
      setRefusals(checked.refusals)
      setRejection(STRAIN_FORM.refusedSummary)
      setIsSaved(false)
      return
    }

    setRefusals([])
    setRejection(null)
    setIsSaving(true)

    const outcome = await onSubmit(checked.submission)

    setIsSaving(false)

    if (outcome.status === 'saved') {
      onSaved(outcome.record)
      setStored(outcome.record)
      setInput(strainInputFrom(outcome.record))
      setSaveCount((count) => count + 1)
      setIsSaved(true)
      return
    }

    if (outcome.status === 'refused') {
      const fields = refusalsFromApi(outcome.refusal.fields ?? {})
      setRefusals(fields)
      /*
       * `detail` is shown as well as the per-field messages, never instead of
       * them. A refusal whose only field is one this build does not know would
       * otherwise render as a form that will not save and will not say why.
       */
      setRejection(outcome.refusal.detail)
      return
    }

    setRejection(outcome.reason)
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-6">
      <ClubCard heading={STRAIN_FORM.identityHeading}>
        <div className="flex flex-col gap-6">
          <TextField
            key={`strain-name-${saveCount}`}
            name="strain-name"
            label={STRAIN_FORM.nameLabel}
            hint={STRAIN_FORM.nameHint}
            defaultValue={input.name}
            error={messageFor('name')}
            onBlurValue={set('name')}
          />

          <div className="grid gap-6 sm:grid-cols-2">
            <SelectField
              name="status"
              label={STRAIN_FORM.statusLabel}
              hint={STRAIN_FORM.statusHint}
              value={input.status}
              choices={STRAIN_STATUSES}
              placeholder={STRAIN_FORM.chooseOne}
              error={messageFor('status')}
              onValue={set('status')}
            />

            <SelectField
              name="strain-type"
              label={STRAIN_FORM.typeLabel}
              hint={STRAIN_FORM.typeHint}
              value={input.strainType}
              choices={STRAIN_TYPES}
              placeholder={STRAIN_FORM.chooseOne}
              error={messageFor('strain_type')}
              onValue={set('strainType')}
            />
          </div>

          <SelectField
            name="exclusive-to"
            label={STRAIN_FORM.exclusiveLabel}
            hint={STRAIN_FORM.exclusiveHint}
            value={input.exclusiveTo}
            choices={exclusiveChoices}
            placeholder={STRAIN_FORM.exclusiveNobody}
            error={messageFor('exclusive_to')}
            onValue={set('exclusiveTo')}
          />
        </div>
      </ClubCard>

      <ClubCard heading={STRAIN_FORM.botanicalHeading}>
        <div className="flex flex-col gap-6">
          <div className="grid gap-6 sm:grid-cols-2">
            <TextField
              key={`genetic-lineage-${saveCount}`}
              name="genetic-lineage"
              label={STRAIN_FORM.lineageLabel}
              hint={STRAIN_FORM.lineageHint}
              defaultValue={input.geneticLineage}
              error={messageFor('genetic_lineage')}
              onBlurValue={set('geneticLineage')}
            />

            <TextField
              key={`breeder-origin-${saveCount}`}
              name="breeder-origin"
              label={STRAIN_FORM.breederLabel}
              defaultValue={input.breederOrigin}
              error={messageFor('breeder_origin')}
              onBlurValue={set('breederOrigin')}
            />
          </div>

          <TextAreaField
            name="description"
            label={STRAIN_FORM.descriptionLabel}
            hint={STRAIN_FORM.descriptionHint}
            rows={5}
            value={input.description}
            error={messageFor('description')}
            onValue={set('description')}
          />
        </div>
      </ClubCard>

      <ClubCard
        heading={STRAIN_FORM.chemicalHeading}
        standfirst={STRAIN_FORM.chemicalStandfirst}
      >
        <div className="flex flex-col gap-6">
          <div className="grid gap-6 sm:grid-cols-2">
            {/*
              * `inputMode="numeric"` gives a phone its keypad. Never
              * `type="number"`, for the reason `TextField` states: it strips a
              * leading zero, and `0.30` is a CBD figure.
              */}
            <TextField
              key={`thc-content-${saveCount}`}
              name="thc-content"
              label={STRAIN_FORM.thcLabel}
              defaultValue={input.thcContent}
              inputMode="numeric"
              error={messageFor('thc_content')}
              onBlurValue={set('thcContent')}
            />

            <TextField
              key={`cbd-content-${saveCount}`}
              name="cbd-content"
              label={STRAIN_FORM.cbdLabel}
              defaultValue={input.cbdContent}
              inputMode="numeric"
              error={messageFor('cbd_content')}
              onBlurValue={set('cbdContent')}
            />
          </div>

          <PairField
            name="other-cannabinoids"
            label={STRAIN_FORM.cannabinoidsLabel}
            hint={STRAIN_FORM.cannabinoidsHint}
            pairs={input.otherCannabinoids}
            error={messageFor('other_cannabinoids')}
            onPairs={set('otherCannabinoids')}
          />

          <PairField
            name="terpene-profile"
            label={STRAIN_FORM.terpenesLabel}
            hint={STRAIN_FORM.terpenesHint}
            pairs={input.terpeneProfile}
            error={messageFor('terpene_profile')}
            onPairs={set('terpeneProfile')}
          />
        </div>
      </ClubCard>

      <ClubCard
        heading={STRAIN_FORM.sensoryHeading}
        standfirst={STRAIN_FORM.sensoryStandfirst}
      >
        <div className="flex flex-col gap-6">
          <TermPicker
            name="aromas"
            label={STRAIN_FORM.aromasLabel}
            terms={vocabularies.aromas}
            selected={input.aromas}
            error={messageFor('aromas')}
            onSelected={set('aromas')}
          />

          <TermPicker
            name="effects"
            label={STRAIN_FORM.effectsLabel}
            terms={vocabularies.effects}
            selected={input.effects}
            error={messageFor('effects')}
            onSelected={set('effects')}
          />

          {/*
            * A way to the vocabularies screen, because the commonest reason to
            * stop filling this form in is a term that is not in the list. A
            * link rather than an inline "add a term" control: adding one is a
            * club-wide act, and doing it from inside an unsaved strain form
            * would mean losing the form or writing the term before the strain.
            */}
          <p className="font-sans text-sm">
            <Link
              href={termsHref}
              className="text-forest-green underline decoration-2 underline-offset-4 hover:text-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            >
              {STRAIN_FORM.termsLinkLabel}
            </Link>
          </p>
        </div>
      </ClubCard>

      <ClubCard
        heading={STRAIN_FORM.cultivationHeading}
        standfirst={STRAIN_FORM.cultivationStandfirst}
      >
        <div className="flex flex-col gap-6">
          <div className="grid gap-6 sm:grid-cols-3">
            <TextField
              key={`flowering-time-weeks-${saveCount}`}
              name="flowering-time-weeks"
              label={STRAIN_FORM.floweringLabel}
              defaultValue={input.floweringTimeWeeks}
              inputMode="numeric"
              error={messageFor('flowering_time_weeks')}
              onBlurValue={set('floweringTimeWeeks')}
            />

            <SelectField
              name="growing-environment"
              label={STRAIN_FORM.environmentLabel}
              value={input.preferredGrowingEnvironment}
              choices={GROWING_ENVIRONMENTS}
              placeholder={STRAIN_FORM.anyEnvironment}
              error={messageFor('preferred_growing_environment')}
              onValue={set('preferredGrowingEnvironment')}
            />

            <SelectField
              name="difficulty-level"
              label={STRAIN_FORM.difficultyLabel}
              value={input.difficultyLevel}
              choices={DIFFICULTY_LEVELS}
              placeholder={STRAIN_FORM.anyDifficulty}
              error={messageFor('difficulty_level')}
              onValue={set('difficultyLevel')}
            />
          </div>

          <PairField
            name="disease-resistance"
            label={STRAIN_FORM.resistanceLabel}
            hint={STRAIN_FORM.resistanceHint}
            pairs={input.diseaseResistance}
            error={messageFor('disease_resistance')}
            onPairs={set('diseaseResistance')}
          />
        </div>
      </ClubCard>

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
          {isSaving
            ? creating
              ? STRAIN_FORM.creating
              : STRAIN_FORM.saving
            : creating
              ? STRAIN_FORM.create
              : STRAIN_FORM.save}
        </button>

        <Link
          href={catalogueHref}
          className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-border px-6 font-sans text-base font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
        >
          {STRAIN_FORM.cancel}
        </Link>

        {/*
          * `role="status"`, not `role="alert"`: both messages follow something
          * the administrator did on purpose, so neither should interrupt. The
          * region is always in the DOM so a screen reader is watching it before
          * it has anything to say -- one that appears already containing text is
          * often not announced at all.
          */}
        <p role="status" className="font-sans text-sm text-muted-foreground">
          {isSaved ? STRAIN_FORM.saved : changed ? '' : STRAIN_FORM.unchanged}
        </p>
      </div>
    </form>
  )
}

/**
 * Whether the form holds anything the stored record does not.
 *
 * Compared as submissions rather than as inputs, and that is the point: a form
 * whose only difference from the stored strain is a trailing empty JSON row is
 * the same record, and comparing raw inputs would report it as changed and offer
 * a save that stores nothing.
 *
 * `JSON.stringify` on two objects built by the same function, so the key order
 * is identical by construction — this is not a general-purpose deep equal and is
 * not asked to be. An invalid form counts as changed: there is something in it
 * that is not in the record, even if what is in it cannot be saved, and
 * disabling the button would leave an administrator unable to submit and so
 * unable to see the refusals.
 */
const hasChanges = (input: StrainInput, stored: Strain | null): boolean => {
  if (stored === null) return true

  const submitted = checkStrain(input)
  if (submitted.status === 'invalid') return true

  const onFile = checkStrain(strainInputFrom(stored))
  if (onFile.status === 'invalid') return true

  return JSON.stringify(submitted.submission) !== JSON.stringify(onFile.submission)
}

'use client'

import { useState } from 'react'

import type { Cultivator, Strain, Vocabularies } from '@/lib/strain-catalogue'
import { createStrain, saveStrain } from '@/lib/strain-catalogue-api'
import { STRAIN_FORM } from '@/lib/strain-catalogue-content'
import { OffersCard } from './OffersCard'
import { RetireCard } from './RetireCard'
import { StrainForm } from './StrainForm'

type StrainScreenProps = {
  /** The strain as the server rendered it, or null on the add screen. */
  initial: Strain | null
  vocabularies: Vocabularies
  cultivators: readonly Cultivator[]
  catalogueHref: string
  termsHref: string
}

/**
 * A strain's own screen, and the one place that holds which record is current.
 *
 * A client component wrapping three cards, for the same reason `ProfileScreen`
 * is one: there is a single piece of shared state, and more than one card
 * writes it. The form answers with the whole strain, the retire control answers
 * with the whole strain, and both the offers card and the retire control have to
 * see the result — without one owner, retiring a strain would leave the form's
 * status select still saying Active.
 *
 * `initial` is trusted for the first paint and nothing is fetched on mount. An
 * administrator should never see a strain they opened render blank for a frame;
 * that reads as though the club had lost the record.
 *
 * ## Add and edit are the same screen
 *
 * `initial === null` is the add screen. It shows the form and nothing else,
 * because the other two cards have nothing to say about a strain that does not
 * exist: there are no offers against it and it cannot be retired. Once the
 * create succeeds the record arrives, and the same component grows the two cards
 * without a navigation — which is deliberate. Sending an administrator to a
 * different URL after a create would lose the "Saved." they just earned and make
 * a second edit a second page load.
 *
 * ## Card order
 *
 * The form, then who is selling it, then retirement. By how likely an
 * administrator is to be here for each, and with the destructive control last
 * because it is the one nobody should reach by scrolling absent-mindedly.
 */
export const StrainScreen = ({
  initial,
  vocabularies,
  cultivators,
  catalogueHref,
  termsHref,
}: StrainScreenProps) => {
  const [strain, setStrain] = useState<Strain | null>(initial)
  /**
   * How many times the record has changed from *outside* the form.
   *
   * Only retirement bumps it, and the distinction is the whole reason it exists.
   * Two writes on this screen produce a new record and they need opposite
   * treatment:
   *
   * * **The form's own save.** The form has already reset itself — it sets its
   *   `stored`, its `input` and its "Saved." from the record that came back. A
   *   remount here would throw all three away, and the visible symptom is the
   *   confirmation vanishing the instant it is earned.
   * * **A retirement.** The form knows nothing about it, so its status select
   *   goes on saying Active while the strain is Inactive — and the next save
   *   would quietly publish it again. Nothing short of a reset fixes that: the
   *   form's state is its own, and a prop change does not reach it.
   *
   * So the key is bumped by one of them and not the other. Deriving it from
   * something on the record — `updated_at`, say — would look neater and would
   * remount on both, which is the bug in the first bullet.
   */
  const [externalWrites, setExternalWrites] = useState(0)

  const retired = (record: Strain) => {
    setStrain(record)
    setExternalWrites((count) => count + 1)
  }

  /*
   * Which endpoint the form writes to, decided from what the screen currently
   * holds rather than from `initial`. After a create, `strain` is set and a
   * further save is a PUT against the row that now exists -- so a second edit on
   * the add screen does not create a second strain.
   */
  const submit = strain === null
    ? createStrain
    : (submission: Parameters<typeof createStrain>[0]) =>
        saveStrain(strain.id, submission)

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <div>
        <p className="font-sans text-sm uppercase tracking-label text-muted-foreground">
          {strain === null ? STRAIN_FORM.addHeading : strain.name}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {strain === null ? STRAIN_FORM.addHeading : STRAIN_FORM.editHeading}
        </h1>

        {strain === null ? (
          <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
            {STRAIN_FORM.addStandfirst}
          </p>
        ) : null}
      </div>

      <StrainForm
        /*
         * `externalWrites` alone — deliberately not the record's id.
         *
         * Keying on the id looks obviously right and is wrong: a create takes it
         * from null to a real value, so the form would remount the instant it
         * succeeded and lose the "Saved." it had just set. It does not need to.
         * A create leaves the form holding the created record already, because
         * that is what its own save path does with the response.
         */
        key={externalWrites}
        strain={strain}
        vocabularies={vocabularies}
        cultivators={cultivators}
        termsHref={termsHref}
        catalogueHref={catalogueHref}
        onSubmit={submit}
        onSaved={setStrain}
      />

      {/*
        * Both cards need a strain that exists. On the add screen there are no
        * offers to list and nothing to retire, and rendering either with a
        * placeholder would be two cards saying "not yet".
        */}
      {strain === null ? null : (
        <>
          <OffersCard listings={strain.listings} />
          <RetireCard strain={strain} onRetired={retired} />
        </>
      )}
    </div>
  )
}

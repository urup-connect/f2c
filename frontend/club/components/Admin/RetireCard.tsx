'use client'

import { useState } from 'react'

import { ClubCard } from '@/components/Club/ClubCard'
import { retirementImpact, type Strain } from '@/lib/strain-catalogue'
import { retireStrain } from '@/lib/strain-catalogue-api'
import { RETIRE_CARD } from '@/lib/strain-catalogue-content'

type RetireCardProps = {
  strain: Strain
  /** Told the record as it now stands, so the whole screen follows the retirement. */
  onRetired: (strain: Strain) => void
}

/**
 * Retiring a strain: what stands in for a delete, and the confirmation in front.
 *
 * There is no delete anywhere in this feature, and this card is where that is
 * explained rather than merely implemented. Both foreign keys into a strain are
 * `PROTECT` — a strain has cultivators' listings behind it and those listings
 * have members' plants behind them — so a strain the club has sold against
 * genuinely cannot be removed. Retirement is the whole answer: it sets
 * `status = inactive`, which `StrainQuerySet.browsable` excludes, so the strain
 * leaves the members' catalogue and every live offer against it leaves the shelf
 * platform-wide, in one act.
 *
 * ## Why there is a confirmation
 *
 * Not because the act is irreversible — it is not; setting the status back to
 * Active on the form above restores everything. Because the *blast radius* is
 * invisible from the button: one click can take four growers' offers off the
 * shelf, and an administrator tidying up a duplicate entry has no way to know
 * that from the strain's own row. The confirmation exists to state the two
 * numbers, and it names the plants specifically, because "will this destroy
 * something a member owns" is the question and the answer is no.
 *
 * ## Why the confirmation is inline rather than a dialog
 *
 * A `window.confirm` cannot show the counts, and a modal needs a focus trap,
 * an escape handler and a scroll lock to be usable with a keyboard — three
 * things that are easy to get almost right. An inline panel that replaces the
 * button needs none of them: focus moves to the confirming button, the way out
 * is a button beside it, and nothing is hidden behind an overlay.
 */
export const RetireCard = ({ strain, onRetired }: RetireCardProps) => {
  const [isConfirming, setIsConfirming] = useState(false)
  const [isRetiring, setIsRetiring] = useState(false)
  const [outcome, setOutcome] = useState<string | null>(null)

  const impact = retirementImpact(strain)

  const retire = async () => {
    setIsRetiring(true)
    setOutcome(null)

    const result = await retireStrain(strain.id)

    setIsRetiring(false)
    setIsConfirming(false)

    if (result.status === 'saved') {
      onRetired(result.record.strain)
      setOutcome(RETIRE_CARD.retired)
      return
    }

    /*
     * Both remaining outcomes are one sentence. There is nothing on this card to
     * mark a per-field refusal against -- retirement takes no input -- so a
     * refused body's `detail` and a failure's reason are shown the same way.
     */
    setOutcome(result.status === 'refused' ? result.refusal.detail : RETIRE_CARD.failed)
  }

  return (
    <ClubCard heading={RETIRE_CARD.heading} standfirst={RETIRE_CARD.standfirst}>
      {impact.alreadyRetired ? (
        <div className="flex flex-col gap-3">
          <p className="font-sans text-sm font-medium text-foreground">
            {RETIRE_CARD.alreadyRetired}
          </p>
          <p className="font-sans text-sm text-muted-foreground">
            {RETIRE_CARD.reinstate}
          </p>
        </div>
      ) : isConfirming ? (
        <div className="flex flex-col gap-4 rounded-control border-2 border-error p-4">
          <h3 className="font-sans text-base font-medium text-foreground">
            {RETIRE_CARD.confirmHeading}
          </h3>

          <div className="flex flex-col gap-2 font-sans text-sm text-foreground">
            {impact.liveListings === 0 ? (
              <p>{RETIRE_CARD.noOffers}</p>
            ) : (
              <p>
                {impact.liveListings} {RETIRE_CARD.offersWarning}
              </p>
            )}

            {/*
              * Only when there are plants. "0 plants are already growing" is a
              * sentence that makes an administrator read twice to learn nothing.
              */}
            {impact.plants > 0 ? (
              <p>
                {impact.plants} {RETIRE_CARD.plantsWarning}
              </p>
            ) : null}

            <p className="text-muted-foreground">{RETIRE_CARD.reinstate}</p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={retire}
              disabled={isRetiring}
              /*
               * `autoFocus` so a keyboard user is on the confirming control the
               * moment the panel appears, rather than having to hunt for where
               * the button they pressed went. Safe here because the panel only
               * ever appears in response to a deliberate click.
               */
              autoFocus
              className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-error bg-error px-6 font-sans text-base font-medium text-surface transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error disabled:opacity-60"
            >
              {isRetiring ? RETIRE_CARD.retiring : RETIRE_CARD.confirmAction}
            </button>

            <button
              type="button"
              onClick={() => setIsConfirming(false)}
              disabled={isRetiring}
              className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-border px-6 font-sans text-base font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
            >
              {RETIRE_CARD.confirmCancel}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setIsConfirming(true)}
          className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-error px-6 font-sans text-base font-medium text-error transition-colors hover:bg-error hover:text-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error"
        >
          {RETIRE_CARD.action}
        </button>
      )}

      {/*
        * `role="status"`: the outcome follows something the administrator did on
        * purpose, so it should not interrupt. Always in the DOM so a screen
        * reader is watching it before it has anything to say.
        */}
      <p role="status" className="mt-4 font-sans text-sm text-muted-foreground">
        {outcome ?? ''}
      </p>
    </ClubCard>
  )
}

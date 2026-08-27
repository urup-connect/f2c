'use client'

import { useState } from 'react'
import Link from 'next/link'

import { ClubCard } from '@/components/Club/ClubCard'
import type { Term, Vocabularies } from '@/lib/strain-catalogue'
import { createTerm, saveTerm, type TermKind } from '@/lib/strain-catalogue-api'
import { TERMS_SCREEN } from '@/lib/strain-catalogue-content'

type TermsScreenProps = {
  /** Both lists as the server rendered them. The starting state, not a fetch trigger. */
  initial: Vocabularies
  /** True when the server could not read them at all. */
  unavailable?: boolean
  catalogueHref: string
}

const INPUT =
  'w-full rounded-control border-2 bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * The two vocabularies: aromas and effects, added, renamed and withdrawn.
 *
 * These are lookup tables rather than choice lists because `member-roles.md` has
 * cultivators asking for additions to them, which makes them runtime data by
 * definition. This is the screen an administrator acts on such a request from.
 *
 * ## Withdrawal, not deletion
 *
 * `is_available` is cleared and the row stays. Deleting an `Aroma` would strip it
 * from every strain that carried it with nothing to say it had happened — so the
 * control says "Withdraw", the term keeps its place in the list, and the strains
 * that already have it keep it. The way back is a button beside it, because a
 * withdrawal that could not be reversed from the screen that made it would be a
 * delete with extra steps.
 *
 * ## Why the usage count is on every row
 *
 * It is the only thing that tells an administrator whether a term is safe to
 * rename or worth withdrawing. A term twelve strains carry is not one to rename
 * casually — the rename takes the slug with it and every one of those strains
 * now reads differently — and a term nobody has used is a term somebody guessed
 * at. The same column `admin.AromaEffectAdmin` puts on its list, for the same
 * reason.
 *
 * ## One list component, twice
 *
 * `VocabularyCard` below is rendered once per vocabulary. The two are identical
 * apart from their heading and the segment the API names them by — which is what
 * `SlugFromName` already says about the models — so a second copy would be a
 * second place to fix anything.
 */
export const TermsScreen = ({
  initial,
  unavailable = false,
  catalogueHref,
}: TermsScreenProps) => {
  const [aromas, setAromas] = useState<readonly Term[]>(initial.aromas)
  const [effects, setEffects] = useState<readonly Term[]>(initial.effects)

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <div>
        <p className="font-sans text-sm uppercase tracking-label text-muted-foreground">
          {TERMS_SCREEN.title}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {TERMS_SCREEN.heading}
        </h1>
        <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
          {TERMS_SCREEN.standfirst}
        </p>

        <p className="mt-6">
          <Link
            href={catalogueHref}
            className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-border px-6 font-sans text-base font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
          >
            {TERMS_SCREEN.backLabel}
          </Link>
        </p>
      </div>

      {unavailable ? (
        <p
          role="alert"
          className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
        >
          {TERMS_SCREEN.loadFailed}
        </p>
      ) : null}

      <VocabularyCard
        kind="aromas"
        heading={TERMS_SCREEN.aromasHeading}
        terms={aromas}
        onTerms={setAromas}
      />

      <VocabularyCard
        kind="effects"
        heading={TERMS_SCREEN.effectsHeading}
        terms={effects}
        onTerms={setEffects}
      />
    </div>
  )
}

type VocabularyCardProps = {
  kind: TermKind
  heading: string
  terms: readonly Term[]
  onTerms: (terms: readonly Term[]) => void
}

/** One vocabulary: an add row, then a row per term. */
const VocabularyCard = ({ kind, heading, terms, onTerms }: VocabularyCardProps) => {
  const [newName, setNewName] = useState('')
  const [isAdding, setIsAdding] = useState(false)
  /**
   * The refusal, and which row it belongs to.
   *
   * One piece of state rather than one per row, because only one row can be
   * mid-write at a time — every control here disables itself while its own call
   * is in flight. `row` is the term's id, or 'new' for the add field.
   */
  const [refusal, setRefusal] = useState<{ row: string; message: string } | null>(null)

  const messageFor = (row: string) => (refusal?.row === row ? refusal.message : null)

  const add = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    const name = newName.trim()
    if (name === '') {
      // Refused here rather than sent. The API would refuse it too, and this way
      // the empty case never leaves the browser.
      setRefusal({ row: 'new', message: TERMS_SCREEN.blankName })
      return
    }

    setIsAdding(true)
    setRefusal(null)

    const outcome = await createTerm(kind, name)

    setIsAdding(false)

    if (outcome.status === 'saved') {
      /*
       * Inserted in the list's own order rather than appended. The API orders
       * these by name, so appending would leave the new term at the bottom until
       * the next page load and then move it -- which reads as the screen having
       * got it wrong the first time.
       */
      onTerms(
        [...terms, outcome.record].sort((left, right) =>
          left.name.localeCompare(right.name),
        ),
      )
      setNewName('')
      return
    }

    setRefusal({
      row: 'new',
      message:
        outcome.status === 'refused' ? outcome.refusal.detail : outcome.reason,
    })
  }

  return (
    <ClubCard heading={heading}>
      <div className="flex flex-col gap-6">
        <form onSubmit={add} noValidate className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-48 flex-1 flex-col gap-1">
            <label
              htmlFor={`term-new-${kind}`}
              className="font-sans text-base font-medium text-foreground"
            >
              {TERMS_SCREEN.newLabel}
            </label>
            <input
              id={`term-new-${kind}`}
              type="text"
              value={newName}
              onChange={(event) => {
                setNewName(event.currentTarget.value)
                setRefusal(null)
              }}
              aria-invalid={messageFor('new') ? true : undefined}
              className={`${INPUT} ${messageFor('new') ? 'border-error' : 'border-border'}`}
            />
          </div>

          <button
            type="submit"
            disabled={isAdding || newName.trim() === ''}
            className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-6 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
          >
            {isAdding ? TERMS_SCREEN.adding : TERMS_SCREEN.addLabel}
          </button>
        </form>

        {messageFor('new') ? (
          <p role="alert" className="font-sans text-sm font-medium text-error">
            {messageFor('new')}
          </p>
        ) : null}

        {terms.length === 0 ? (
          <p className="font-sans text-sm text-muted-foreground">{TERMS_SCREEN.empty}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {terms.map((term) => (
              <TermRow
                key={term.id}
                kind={kind}
                term={term}
                error={messageFor(term.id)}
                onRefused={(message) => setRefusal({ row: term.id, message })}
                onSaved={(saved) =>
                  onTerms(
                    terms
                      .map((existing) => (existing.id === saved.id ? saved : existing))
                      .sort((left, right) => left.name.localeCompare(right.name)),
                  )
                }
              />
            ))}
          </ul>
        )}
      </div>
    </ClubCard>
  )
}

type TermRowProps = {
  kind: TermKind
  term: Term
  error: string | null
  onSaved: (term: Term) => void
  onRefused: (message: string) => void
}

/**
 * One term: its name, its usage count, and the two things that can be done to it.
 *
 * The name is editable in place and the save button is inert until it changes,
 * for the reason every other form here gives: a save that stores an identical
 * value reports success for having done nothing.
 *
 * Withdrawing and restoring are one call with `is_available` flipped, and they
 * send the *current* name rather than the edited one — so an administrator who
 * has typed a new name and then pressed Withdraw does not silently commit the
 * rename as well. Two acts, two buttons, and neither does the other's work.
 */
const TermRow = ({ kind, term, error, onSaved, onRefused }: TermRowProps) => {
  const [name, setName] = useState(term.name)
  const [isBusy, setIsBusy] = useState(false)

  const renamed = name.trim() !== '' && name.trim() !== term.name

  const write = async (nextName: string, isAvailable: boolean) => {
    setIsBusy(true)

    const outcome = await saveTerm(kind, term.id, nextName, isAvailable)

    setIsBusy(false)

    if (outcome.status === 'saved') {
      onSaved(outcome.record)
      setName(outcome.record.name)
      return
    }

    onRefused(outcome.status === 'refused' ? outcome.refusal.detail : outcome.reason)
  }

  return (
    <li className="flex flex-col gap-2 rounded-control border-2 border-border p-3">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-40 flex-1 flex-col gap-1">
          <label
            htmlFor={`term-${term.id}`}
            className="font-sans text-xs uppercase tracking-label text-muted-foreground"
          >
            {TERMS_SCREEN.nameLabel}
          </label>
          <input
            id={`term-${term.id}`}
            type="text"
            value={name}
            onChange={(event) => setName(event.currentTarget.value)}
            aria-invalid={error ? true : undefined}
            className={`${INPUT} ${error ? 'border-error' : 'border-border'}`}
          />
        </div>

        <p className="font-sans text-sm text-muted-foreground">
          {term.strain_count === 0
            ? TERMS_SCREEN.unused
            : `${term.strain_count} ${
                term.strain_count === 1 ? TERMS_SCREEN.usedByOne : TERMS_SCREEN.usedBy
              }`}
          {term.is_available ? null : (
            <span className="ml-2 text-xs uppercase tracking-label text-error">
              {TERMS_SCREEN.withdrawnBadge}
            </span>
          )}
        </p>

        <button
          type="button"
          disabled={isBusy || !renamed}
          onClick={() => write(name.trim(), term.is_available)}
          className="inline-flex h-11 items-center rounded-pill border-2 border-transparent bg-primary px-5 font-sans text-sm font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
        >
          {isBusy ? TERMS_SCREEN.saving : TERMS_SCREEN.saveLabel}
        </button>

        <button
          type="button"
          disabled={isBusy}
          /*
           * `term.name`, not `name`. An administrator who typed a new name and
           * then pressed Withdraw meant to withdraw, not to rename -- and doing
           * both would commit an edit they had not asked to save.
           */
          onClick={() => write(term.name, !term.is_available)}
          className="inline-flex h-11 items-center rounded-pill border-2 border-border px-5 font-sans text-sm font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
        >
          {term.is_available ? TERMS_SCREEN.withdrawLabel : TERMS_SCREEN.restoreLabel}
        </button>
      </div>

      {error ? (
        <p role="alert" className="font-sans text-sm font-medium text-error">
          {error}
        </p>
      ) : null}
    </li>
  )
}

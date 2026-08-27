'use client'

import { useState, useTransition } from 'react'
import Link from 'next/link'

import { ClubCard } from '@/components/Club/ClubCard'
import {
  STRAIN_STATUSES,
  STRAIN_TYPES,
  isBrowsable,
  labelFor,
  type StrainRow,
} from '@/lib/strain-catalogue'
import { listStrains } from '@/lib/strain-catalogue-api'
import { CATALOGUE_LIST } from '@/lib/strain-catalogue-content'
import { SelectField } from './SelectField'

type CatalogueScreenProps = {
  /** The catalogue as the server rendered it. The starting state, not a fetch trigger. */
  initial: readonly StrainRow[]
  /** True when the server could not read the catalogue at all. */
  unavailable?: boolean
  /** Route bases, passed in so the component holds no knowledge of the URL scheme. */
  strainHref: (id: string) => string
  addHref: string
  termsHref: string
}

const HEAD = 'px-3 py-2 text-left font-sans text-xs uppercase tracking-label text-muted-foreground'
const CELL = 'px-3 py-3 align-top font-sans text-sm text-foreground'

/**
 * The catalogue: every strain, narrowed by three filters, each row a way in.
 *
 * ## Filtering happens on the server
 *
 * The three controls re-query the API rather than filtering an array in the
 * browser, which is the more expensive choice and the right one. The list is
 * unpaginated today — a club's catalogue is tens of rows — and the moment it is
 * not, a browser-side filter would be filtering one page and calling it the
 * catalogue. Filtering server-side now means paging later is a change to the
 * endpoint and this component's `useTransition`, not a rewrite of what
 * "narrowed" means.
 *
 * `useTransition` rather than a `loading` flag: the previous list stays on screen
 * and readable while the next one is fetched, instead of being replaced by a
 * spinner every time somebody changes a dropdown.
 *
 * ## What the rows carry, and what they do not
 *
 * No description and no JSON columns — see `StrainRowOut`. The list is for
 * scanning, and the two things a scan is actually for are *is this strain in
 * front of members* and *is anybody selling it*. Both are called out rather than
 * left to be inferred: a bare status of "Hidden" does not tell an administrator
 * that hidden means invisible, and a count of offers is what a retirement
 * decision turns on.
 *
 * ## Why a failed read is not an empty catalogue
 *
 * "The catalogue holds no strains yet" shown to somebody whose API is down is a
 * sentence that sends them to add strains that already exist. `unavailable` says
 * the read failed; the two are never conflated. Same reasoning as
 * `readPasskeys`.
 */
export const CatalogueScreen = ({
  initial,
  unavailable = false,
  strainHref,
  addHref,
  termsHref,
}: CatalogueScreenProps) => {
  const [rows, setRows] = useState<readonly StrainRow[]>(initial)
  const [status, setStatus] = useState('')
  const [strainType, setStrainType] = useState('')
  const [search, setSearch] = useState('')
  const [failed, setFailed] = useState(unavailable)
  const [isPending, startTransition] = useTransition()

  const filtering = status !== '' || strainType !== '' || search.trim() !== ''

  /**
   * Re-read the catalogue under a new set of filters.
   *
   * Takes the whole filter set rather than reading state, because a `setState`
   * in the same tick has not landed yet — calling this after `setStatus` would
   * query with the previous status. Every caller passes what it is changing.
   */
  const refresh = (next: { status: string; strainType: string; search: string }) => {
    startTransition(async () => {
      try {
        setRows(
          await listStrains({
            status: next.status,
            strain_type: next.strainType,
            search: next.search,
          }),
        )
        setFailed(false)
      } catch {
        // The rows already on screen stay there. They are stale rather than
        // wrong, and a table replaced by an error message loses the
        // administrator's place in a list they were reading.
        setFailed(true)
      }
    })
  }

  const setFilter = (field: 'status' | 'strainType' | 'search') => (value: string) => {
    const next = { status, strainType, search, [field]: value }
    if (field === 'status') setStatus(value)
    if (field === 'strainType') setStrainType(value)
    if (field === 'search') setSearch(value)
    refresh(next)
  }

  const clear = () => {
    setStatus('')
    setStrainType('')
    setSearch('')
    refresh({ status: '', strainType: '', search: '' })
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <div>
        <p className="font-sans text-sm uppercase tracking-label text-muted-foreground">
          {CATALOGUE_LIST.title}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {CATALOGUE_LIST.heading}
        </h1>
        <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
          {CATALOGUE_LIST.standfirst}
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Link
            href={addHref}
            className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-6 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
          >
            {CATALOGUE_LIST.addLabel}
          </Link>

          <Link
            href={termsHref}
            className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-border px-6 font-sans text-base font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
          >
            {CATALOGUE_LIST.termsLabel}
          </Link>
        </div>
      </div>

      <ClubCard heading={CATALOGUE_LIST.filterHeading}>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {/*
            * A controlled `input` rather than the shared `TextField`, and the
            * exception is worth naming: `TextField` reports on blur, which for a
            * search box means an administrator types a name, sees nothing
            * happen, and clicks elsewhere to find out whether it worked.
            */}
          <div className="flex flex-col gap-1 sm:col-span-2">
            <label
              htmlFor="catalogue-search"
              className="font-sans text-base font-medium text-foreground"
            >
              {CATALOGUE_LIST.searchLabel}
            </label>
            <p
              id="catalogue-search-hint"
              className="font-sans text-sm leading-relaxed text-muted-foreground"
            >
              {CATALOGUE_LIST.searchHint}
            </p>
            <input
              id="catalogue-search"
              type="search"
              value={search}
              aria-describedby="catalogue-search-hint"
              onChange={(event) => setFilter('search')(event.currentTarget.value)}
              className="w-full rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            />
          </div>

          <SelectField
            name="filter-status"
            label={CATALOGUE_LIST.statusLabel}
            value={status}
            choices={STRAIN_STATUSES}
            placeholder={CATALOGUE_LIST.anyStatus}
            onValue={setFilter('status')}
          />

          <SelectField
            name="filter-type"
            label={CATALOGUE_LIST.typeLabel}
            value={strainType}
            choices={STRAIN_TYPES}
            placeholder={CATALOGUE_LIST.anyType}
            onValue={setFilter('strainType')}
          />
        </div>

        {filtering ? (
          <div className="mt-6">
            <button
              type="button"
              onClick={clear}
              className="inline-flex h-10 items-center rounded-pill border-2 border-border px-4 font-sans text-sm font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            >
              {CATALOGUE_LIST.clearLabel}
            </button>
          </div>
        ) : null}
      </ClubCard>

      {failed ? (
        <p
          role="alert"
          className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
        >
          {CATALOGUE_LIST.loadFailed}
        </p>
      ) : null}

      <section
        aria-labelledby="catalogue-table-heading"
        aria-busy={isPending}
        className="rounded-card bg-surface p-6 shadow-sm sm:p-8"
      >
        <h2
          id="catalogue-table-heading"
          className="font-display text-2xl tracking-display text-forest-green"
        >
          {CATALOGUE_LIST.heading}
        </h2>

        <div className="mt-6">
          {rows.length === 0 ? (
            <p className="font-sans text-sm text-muted-foreground">
              {/* Never conflated: an empty catalogue and an empty filter send an
                * administrator to two different places. */}
              {filtering ? CATALOGUE_LIST.emptyFiltered : CATALOGUE_LIST.empty}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[48rem] border-collapse">
                <thead>
                  <tr className="border-b-2 border-border">
                    <th scope="col" className={HEAD}>
                      {CATALOGUE_LIST.columnName}
                    </th>
                    <th scope="col" className={HEAD}>
                      {CATALOGUE_LIST.columnType}
                    </th>
                    <th scope="col" className={HEAD}>
                      {CATALOGUE_LIST.columnStatus}
                    </th>
                    <th scope="col" className={HEAD}>
                      {CATALOGUE_LIST.columnReserved}
                    </th>
                    <th scope="col" className={HEAD}>
                      {CATALOGUE_LIST.columnOffers}
                    </th>
                    <th scope="col" className={HEAD}>
                      {CATALOGUE_LIST.columnUpdated}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b border-border last:border-b-0">
                      <th scope="row" className={`${CELL} font-medium`}>
                        {/*
                          * The name is the link, so the target of the click is
                          * the thing that identifies the row -- rather than an
                          * "Edit" cell at the far right of a table that scrolls.
                          */}
                        <Link
                          href={strainHref(row.id)}
                          className="text-forest-green underline decoration-2 underline-offset-4 hover:text-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
                        >
                          {row.name}
                        </Link>
                      </th>

                      <td className={CELL}>{labelFor(STRAIN_TYPES, row.strain_type)}</td>

                      <td className={CELL}>
                        <span className="flex flex-col gap-0.5">
                          <span>{labelFor(STRAIN_STATUSES, row.status)}</span>

                          {/*
                            * Said in words, because three of the four statuses
                            * keep a strain out of the members' catalogue and
                            * nothing about the label says which.
                            */}
                          {isBrowsable(row.status) ? null : (
                            <span className="text-xs text-muted-foreground">
                              {CATALOGUE_LIST.notBrowsable}
                            </span>
                          )}
                        </span>
                      </td>

                      <td className={CELL}>
                        {row.reserved_to ?? (
                          <span className="text-muted-foreground">
                            {CATALOGUE_LIST.openToAll}
                          </span>
                        )}
                      </td>

                      <td className={`${CELL} tabular-nums`}>
                        {row.listings_live} {CATALOGUE_LIST.offersSummary}{' '}
                        {row.listings_total}
                      </td>

                      <td className={CELL}>
                        {/*
                          * `dateTime` carries the machine value; the text is the
                          * date part alone. A full ISO timestamp in a table cell
                          * is six columns' worth of noise, and the API's value is
                          * already UTC.
                          */}
                        <time dateTime={row.updated_at}>{row.updated_at.slice(0, 10)}</time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

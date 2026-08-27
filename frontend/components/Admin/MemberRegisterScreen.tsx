'use client'

import { useState, useTransition } from 'react'
import Link from 'next/link'

import { ClubCard } from '@/components/Club/ClubCard'
import {
  JOINED_WINDOWS,
  MEMBER_ROLES,
  MEMBER_STATUSES,
  canSignIn,
  type MemberRow,
} from '@/lib/member-register'
import { listMembers } from '@/lib/member-register-api'
import { MEMBER_REGISTER } from '@/lib/member-register-content'
import { memberPath } from '@/lib/member-register-routes'
import { SelectField } from './SelectField'

type MemberRegisterScreenProps = {
  /** The register as the server rendered it. The starting state, not a fetch trigger. */
  initial: readonly MemberRow[]
  /** True when the server could not read the register at all. */
  unavailable?: boolean
}

const HEAD = 'px-3 py-2 text-left font-sans text-xs uppercase tracking-label text-muted-foreground'
const CELL = 'px-3 py-3 align-top font-sans text-sm text-foreground'

type Filters = {
  status: string
  role: string
  search: string
  joinedWithin: string
}

const NOTHING: Filters = { status: '', role: '', search: '', joinedWithin: '' }

/**
 * The register: every account the club holds, narrowed by four filters.
 *
 * Modelled on `CatalogueScreen` and diverging from it in three places, each of
 * which is about this screen holding people rather than plants.
 *
 * ## Filtering happens on the server, and here it is not optional
 *
 * The catalogue's list filters server-side because a club's strains will one day
 * outgrow a page. A membership already has. More importantly, the search reaches
 * the identity number's blind index — an exact-match lookup the browser could
 * not perform even if it wanted to, because the number is encrypted and the
 * browser never receives it. A browser-side filter here would silently be a
 * different search from the one the label promises.
 *
 * ## No row carries an identity number
 *
 * Not even the masked form. `MemberRowOut` does not send one, and the column
 * that would show it is absent rather than blank — see `lib/member-register.ts`.
 * The `has_id_number` flag is what the register needs, and it is folded into the
 * member cell rather than given a column of its own.
 *
 * ## An erased account is listed, and marked
 *
 * `soft_delete` keeps the row because the club's own history points at it, so
 * hiding those rows would make the register disagree with every other screen
 * about how many accounts exist. It is marked instead, and its contact column
 * says what happened rather than being empty.
 *
 * ## Why a failed read is not an empty register
 *
 * "The register holds no accounts yet" shown to somebody whose API is down is a
 * sentence that sends them looking for a bug in sign-up. `unavailable` says the
 * read failed; the two are never conflated. Same reasoning as `CatalogueScreen`
 * and `readPasskeys`.
 */
export const MemberRegisterScreen = ({
  initial,
  unavailable = false,
}: MemberRegisterScreenProps) => {
  const [rows, setRows] = useState<readonly MemberRow[]>(initial)
  const [filters, setFilters] = useState<Filters>(NOTHING)
  const [failed, setFailed] = useState(unavailable)
  const [isPending, startTransition] = useTransition()

  const filtering =
    filters.status !== '' ||
    filters.role !== '' ||
    filters.joinedWithin !== '' ||
    filters.search.trim() !== ''

  /**
   * Re-read the register under a new set of filters.
   *
   * Takes the whole filter set rather than reading state, because a `setState`
   * in the same tick has not landed yet — calling this after `setFilters` would
   * query with the previous set. Every caller passes what it is changing.
   */
  const refresh = (next: Filters) => {
    startTransition(async () => {
      try {
        setRows(
          await listMembers({
            status: next.status,
            role: next.role,
            search: next.search,
            joined_within: next.joinedWithin,
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

  const setFilter = (field: keyof Filters) => (value: string) => {
    const next = { ...filters, [field]: value }
    setFilters(next)
    refresh(next)
  }

  const clear = () => {
    setFilters(NOTHING)
    refresh(NOTHING)
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <div>
        <p className="font-sans text-sm uppercase tracking-label text-muted-foreground">
          {MEMBER_REGISTER.title}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {MEMBER_REGISTER.heading}
        </h1>
        <p className="mt-3 max-w-3xl font-sans text-base leading-relaxed text-muted-foreground">
          {MEMBER_REGISTER.standfirst}
        </p>
      </div>

      <ClubCard heading={MEMBER_REGISTER.filterHeading}>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {/*
            * A controlled `input` rather than the shared `TextField`, for the
            * reason `CatalogueScreen` gives: `TextField` reports on blur, which
            * for a search box means typing a name, seeing nothing happen, and
            * clicking elsewhere to find out whether it worked.
            */}
          <div className="flex flex-col gap-1 sm:col-span-2">
            <label
              htmlFor="register-search"
              className="font-sans text-base font-medium text-foreground"
            >
              {MEMBER_REGISTER.searchLabel}
            </label>
            <p
              id="register-search-hint"
              className="font-sans text-sm leading-relaxed text-muted-foreground"
            >
              {MEMBER_REGISTER.searchHint}
            </p>
            <input
              id="register-search"
              type="search"
              value={filters.search}
              aria-describedby="register-search-hint"
              onChange={(event) => setFilter('search')(event.currentTarget.value)}
              className="w-full rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            />
          </div>

          <SelectField
            name="filter-standing"
            label={MEMBER_REGISTER.statusLabel}
            value={filters.status}
            choices={MEMBER_STATUSES}
            placeholder={MEMBER_REGISTER.anyStatus}
            onValue={setFilter('status')}
          />

          <SelectField
            name="filter-role"
            label={MEMBER_REGISTER.roleLabel}
            value={filters.role}
            choices={MEMBER_ROLES}
            placeholder={MEMBER_REGISTER.anyRole}
            onValue={setFilter('role')}
          />

          {/*
            * The recent sign-ups view, as a filter rather than a screen of its
            * own. The register is newest-first regardless, so a window on it is
            * already the list of who joined lately in the order somebody wants
            * to read it -- see `administration.register`.
            */}
          <SelectField
            name="filter-joined"
            label={MEMBER_REGISTER.joinedLabel}
            value={filters.joinedWithin}
            choices={JOINED_WINDOWS}
            placeholder={MEMBER_REGISTER.anyTime}
            onValue={setFilter('joinedWithin')}
          />
        </div>

        {filtering ? (
          <div className="mt-6">
            <button
              type="button"
              onClick={clear}
              className="inline-flex h-10 items-center rounded-pill border-2 border-border px-4 font-sans text-sm font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
            >
              {MEMBER_REGISTER.clearLabel}
            </button>
          </div>
        ) : null}
      </ClubCard>

      {failed ? (
        <p
          role="alert"
          className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
        >
          {MEMBER_REGISTER.loadFailed}
        </p>
      ) : null}

      <section
        aria-labelledby="register-table-heading"
        aria-busy={isPending}
        className="rounded-card bg-surface p-6 shadow-sm sm:p-8"
      >
        <h2
          id="register-table-heading"
          className="font-display text-2xl tracking-display text-forest-green"
        >
          {MEMBER_REGISTER.heading}
        </h2>

        <div className="mt-6">
          {rows.length === 0 ? (
            <p className="font-sans text-sm text-muted-foreground">
              {/* Never conflated: an empty register and an empty filter send an
                * administrator to two different places. */}
              {filtering ? MEMBER_REGISTER.emptyFiltered : MEMBER_REGISTER.empty}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[52rem] border-collapse">
                <thead>
                  <tr className="border-b-2 border-border">
                    <th scope="col" className={HEAD}>
                      {MEMBER_REGISTER.columnMember}
                    </th>
                    <th scope="col" className={HEAD}>
                      {MEMBER_REGISTER.columnRole}
                    </th>
                    <th scope="col" className={HEAD}>
                      {MEMBER_REGISTER.columnStatus}
                    </th>
                    <th scope="col" className={HEAD}>
                      {MEMBER_REGISTER.columnMembership}
                    </th>
                    <th scope="col" className={HEAD}>
                      {MEMBER_REGISTER.columnContact}
                    </th>
                    <th scope="col" className={HEAD}>
                      {MEMBER_REGISTER.columnJoined}
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
                          * "Open" cell at the far right of a table that scrolls.
                          */}
                        <Link
                          href={memberPath(row.id)}
                          className="text-forest-green underline decoration-2 underline-offset-4 hover:text-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
                        >
                          {row.display_name}
                        </Link>

                        {row.erased ? (
                          <span className="mt-0.5 block text-xs font-normal text-muted-foreground">
                            {MEMBER_REGISTER.erasedBadge}
                          </span>
                        ) : null}
                      </th>

                      <td className={CELL}>{row.role_label}</td>

                      <td className={CELL}>
                        <span className="flex flex-col gap-0.5">
                          <span>{row.status_label}</span>

                          {/*
                            * Said in words, because five of the six statuses
                            * block a sign-in and nothing about the label says
                            * which. `User.is_active` is derived from exactly
                            * this, with a check constraint holding the two
                            * together.
                            */}
                          {canSignIn(row.status) ? null : (
                            <span className="text-xs text-muted-foreground">
                              {MEMBER_REGISTER.cannotSignIn}
                            </span>
                          )}
                        </span>
                      </td>

                      <td className={CELL}>
                        {row.membership.status_label === null ? (
                          <span className="text-muted-foreground">
                            {MEMBER_REGISTER.noSubscription}
                          </span>
                        ) : (
                          <span className="flex flex-col gap-0.5">
                            <span>{row.membership.status_label}</span>
                            {row.membership.paid_until === null ? null : (
                              <span className="text-xs text-muted-foreground">
                                {MEMBER_REGISTER.paidUntil}{' '}
                                <time dateTime={row.membership.paid_until}>
                                  {row.membership.paid_until}
                                </time>
                              </span>
                            )}
                          </span>
                        )}
                      </td>

                      <td className={CELL}>
                        {row.email === null ? (
                          <span className="text-muted-foreground">
                            {MEMBER_REGISTER.noContact}
                          </span>
                        ) : (
                          <span className="flex flex-col gap-0.5">
                            <span className="break-all">{row.email}</span>
                            {row.mobile === '' ? null : (
                              <span className="text-xs text-muted-foreground">{row.mobile}</span>
                            )}
                          </span>
                        )}
                      </td>

                      <td className={CELL}>
                        {/*
                          * `dateTime` carries the machine value; the text is the
                          * date part alone. A full ISO timestamp in a table cell
                          * is six columns' worth of noise, and the API's value is
                          * already UTC.
                          */}
                        <time dateTime={row.created_at}>{row.created_at.slice(0, 10)}</time>
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

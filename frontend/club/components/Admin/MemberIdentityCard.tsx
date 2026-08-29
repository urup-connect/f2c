'use client'

import { useState } from 'react'

import { ClubCard } from '@/components/Club/ClubCard'
import {
  UNREADABLE_ID_NUMBER,
  disclosureReasonIsEnough,
  type Disclosure,
  type Member,
} from '@/lib/member-register'
import { discloseIdentityNumber } from '@/lib/member-register-api'
import { MEMBER_IDENTITY } from '@/lib/member-register-content'

type MemberIdentityCardProps = {
  member: Member
}

const ACTION =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-border px-6 font-sans text-base font-medium text-forest-green transition-colors hover:border-forest-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60'

const PRIMARY =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-6 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60'

/**
 * The identity document: the masked form by default, and a recorded full read.
 *
 * `design/backend.md` section 10 makes the number write-only in the Django
 * admin — staff may set it and confirm which one is on file from the last four
 * digits, and the plaintext is never rendered. This screen keeps that default
 * and adds one exception, and the exception is what the disclosure ledger pays
 * for.
 *
 * ## The reason is asked for before the number is fetched, not after
 *
 * Not a nicety. `POST /identity-number` writes the disclosure row *before* it
 * decrypts the column, so there is no call that returns a number without leaving
 * a record — and the reason is the field that makes the record reviewable. A
 * screen that fetched first and asked afterwards would be a screen with a way to
 * read the number and abandon the form.
 *
 * ## The number is never put in a URL, and never persisted here
 *
 * It arrives in a POST response body, lives in this component's state, and is
 * gone on the next render of the page. Nothing writes it to storage, to a query
 * string, or to the record the rest of the screen holds.
 *
 * ## `UNREADABLE` is shown, not hidden
 *
 * A row whose ciphertext will not decrypt is a key or an integrity problem
 * somebody has to look at. Presenting it as "no document on file" would be
 * unrecoverable data reported as absent, which is the one outcome worse than the
 * problem itself — nobody would know to look.
 */
export const MemberIdentityCard = ({ member }: MemberIdentityCardProps) => {
  const [asking, setAsking] = useState(false)
  const [reason, setReason] = useState('')
  const [working, setWorking] = useState(false)
  const [number, setNumber] = useState<string | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [history, setHistory] = useState<readonly Disclosure[]>(member.disclosures)

  const unreadable = member.id_number_masked === UNREADABLE_ID_NUMBER
  const enough = disclosureReasonIsEnough(reason)

  const reveal = async () => {
    if (!enough) {
      setRefusal(MEMBER_IDENTITY.reasonTooShort)
      return
    }

    setWorking(true)
    setRefusal(null)
    const outcome = await discloseIdentityNumber(member.id, reason)
    setWorking(false)

    if (outcome.status === 'saved') {
      setNumber(outcome.record.id_number)
      // Prepended rather than re-fetched: the endpoint answers with the row it
      // just wrote, and the list is newest-first.
      setHistory((current) => [outcome.record.disclosure, ...current])
      setAsking(false)
      setReason('')
      return
    }

    setRefusal(
      outcome.status === 'refused' ? outcome.refusal.detail : MEMBER_IDENTITY.failed,
    )
  }

  const cancel = () => {
    setAsking(false)
    setReason('')
    setRefusal(null)
  }

  return (
    <ClubCard heading={MEMBER_IDENTITY.heading} standfirst={MEMBER_IDENTITY.standfirst}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <p className="font-sans text-xs uppercase tracking-label text-muted-foreground">
            {MEMBER_IDENTITY.maskedLabel}
          </p>

          {!member.has_id_number ? (
            <p className="font-sans text-base italic text-muted-foreground">
              {MEMBER_IDENTITY.none}
            </p>
          ) : unreadable ? (
            <p role="alert" className="font-sans text-sm font-medium text-error">
              {MEMBER_IDENTITY.unreadable}
            </p>
          ) : (
            <p className="font-sans text-base tabular-nums text-foreground">
              {number ?? member.id_number_masked}
            </p>
          )}
        </div>

        {number === null ? null : (
          <div className="flex flex-wrap items-center gap-4">
            <p role="status" className="font-sans text-sm text-muted-foreground">
              {MEMBER_IDENTITY.revealed}
            </p>
            <button type="button" onClick={() => setNumber(null)} className={ACTION}>
              {MEMBER_IDENTITY.hideLabel}
            </button>
          </div>
        )}

        {member.has_id_number && !unreadable && number === null ? (
          asking ? (
            <div className="flex flex-col gap-3 rounded-control border-2 border-border p-4">
              <label
                htmlFor="member-disclosure-reason"
                className="font-sans text-base font-medium text-foreground"
              >
                {MEMBER_IDENTITY.reasonLabel}
              </label>
              <p
                id="member-disclosure-reason-hint"
                className="font-sans text-sm leading-relaxed text-muted-foreground"
              >
                {MEMBER_IDENTITY.reasonHint}
              </p>
              <textarea
                id="member-disclosure-reason"
                rows={3}
                value={reason}
                aria-describedby="member-disclosure-reason-hint"
                onChange={(event) => setReason(event.currentTarget.value)}
                className="w-full rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
              />

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  /*
                   * Disabled until the reason is long enough, rather than
                   * refused on press. The rule is not a secret and the button is
                   * the place to say so -- but the message below still exists,
                   * because a disabled button explains nothing on its own.
                   */
                  disabled={working || !enough}
                  onClick={reveal}
                  className={PRIMARY}
                >
                  {working ? MEMBER_IDENTITY.revealing : MEMBER_IDENTITY.confirmReveal}
                </button>

                <button
                  type="button"
                  disabled={working}
                  onClick={cancel}
                  className={ACTION}
                >
                  {MEMBER_IDENTITY.cancelReveal}
                </button>
              </div>

              {!enough && reason.trim() !== '' ? (
                <p className="font-sans text-sm text-muted-foreground">
                  {MEMBER_IDENTITY.reasonTooShort}
                </p>
              ) : null}
            </div>
          ) : (
            <div>
              <button type="button" onClick={() => setAsking(true)} className={ACTION}>
                {MEMBER_IDENTITY.revealLabel}
              </button>
            </div>
          )
        ) : null}

        {refusal === null ? null : (
          <p role="alert" className="font-sans text-sm font-medium text-error">
            {refusal}
          </p>
        )}

        <div>
          <h3 className="font-sans text-xs uppercase tracking-label text-muted-foreground">
            {MEMBER_IDENTITY.historyHeading}
          </h3>

          {history.length === 0 ? (
            <p className="mt-2 font-sans text-sm text-muted-foreground">
              {MEMBER_IDENTITY.historyEmpty}
            </p>
          ) : (
            <ul className="mt-2 flex flex-col gap-3">
              {history.map((entry) => (
                <li key={entry.id} className="flex flex-col gap-0.5">
                  <p className="font-sans text-sm text-foreground">
                    {MEMBER_IDENTITY.historyBy}{' '}
                    {entry.read_by ?? MEMBER_IDENTITY.historyUnknown},{' '}
                    <time dateTime={entry.created_at}>{entry.created_at.slice(0, 10)}</time>
                  </p>
                  <p className="font-sans text-sm text-muted-foreground">{entry.reason}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </ClubCard>
  )
}

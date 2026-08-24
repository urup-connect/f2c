'use client'

import { useState } from 'react'
import type { FormEvent } from 'react'
import { ConsentGroup } from './ConsentGroup'
import { ErrorSummary } from './ErrorSummary'
import { TextField } from './TextField'
import {
  MEMBER_DETAILS_FIELDS,
  readMemberDetailsInput,
  validateMemberDetails,
} from '@/lib/member-details'
import type { MemberDetailField, MemberDetailsFieldRefusal } from '@/lib/member-details'
import { MEMBER_DETAILS_COPY, formatDateOfBirth, memberDetailsRefusalMessage } from '@/lib/member-details-content'
import { NICKNAME_MAX_LENGTH } from '@/lib/nickname'
import { filterSaIdInput } from '@/lib/sa-id-number'
import { filterSaMobileInput, formatSaMobileNumber } from '@/lib/sa-mobile-number'
import type { CalendarDate } from '@/lib/age-gate'
import type { ClubDocumentRevisions } from '@/lib/club-documents'

type MemberDetailsFormProps = {
  /** Where the submission goes. A server action at the route; a spy in tests. */
  action: (formData: FormData) => void | Promise<void>
  /**
   * The date the age pass carried. A prop, never an input: nothing on this page may offer to
   * change it, and the server re-reads the pass rather than trusting anything sent back.
   */
  dateOfBirth: CalendarDate
  /**
   * The club document revisions in force, read from Django by the route.
   *
   * A prop rather than a lookup, so this component knows nothing about which environment it is in
   * and no address, version or agreement wording ends up hard-coded next to the markup.
   */
  revisions: ClubDocumentRevisions
  /** Refusals the server decided, arriving as codes in the query string on the no-script path. */
  refusals?: readonly MemberDetailsFieldRefusal[]
}

type FieldConfig = {
  readonly name: MemberDetailField
  readonly autoComplete: string
  readonly inputMode?: 'numeric'
  readonly maxLength?: number
  /** Whether the field takes a whole row of its own once there are two columns. */
  readonly fullRow?: true
  /** Tidies the field's value once it loses focus. Only the mobile number has one. */
  readonly formatOnBlur?: (value: string) => string
  /**
   * Drops characters the field will never accept, as they are typed.
   *
   * The two number fields have one. The name and nickname fields deliberately do not: a name may
   * contain almost anything, and silently dropping a character out of somebody's name would be a
   * good deal worse than refusing it in words.
   */
  readonly filterOnInput?: (value: string) => string
}

/*
 * Reading order, always. The grid decides where a field sits and never what order it is tabbed
 * through, so the two must not be separated here.
 *
 * The names pair, and so do the two ways of reaching a member. The nickname and the ID number have
 * no partner and take a full row each: a lone half-width field leaves a hole in the grid, and the
 * nickname's hint wants the room.
 */
const FIELDS: readonly FieldConfig[] = [
  { name: 'firstName', autoComplete: 'given-name' },
  { name: 'lastName', autoComplete: 'family-name' },
  { name: 'nickname', autoComplete: 'nickname', maxLength: NICKNAME_MAX_LENGTH, fullRow: true },
  { name: 'email', autoComplete: 'email' },
  {
    name: 'mobile',
    autoComplete: 'tel-national',
    inputMode: 'numeric',
    filterOnInput: filterSaMobileInput,
    formatOnBlur: formatSaMobileNumber,
  },
  /*
   * `autoComplete="off"`: an identity number is not a token any browser knows, and offering to
   * remember it is not a service to anyone.
   *
   * No `maxLength`, deliberately, even though there is a thirteen-digit cap: the browser's own
   * attribute counts characters, and a pasted number written with spaces is fifteen characters and
   * thirteen digits. `filterSaIdInput` counts the digits instead.
   */
  {
    name: 'idNumber',
    autoComplete: 'off',
    inputMode: 'numeric',
    fullRow: true,
    filterOnInput: filterSaIdInput,
  },
]

const SUBMIT =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green'

/**
 * The six details, validated in the browser and again on the server.
 *
 * A Client Component, unlike everything else on this route, and for one reason: the form has to
 * hold what the visitor typed across a refusal. Six fields is too many to ask anyone to retype
 * because of one mistake, and the values cannot travel back in a redirect — an identity number in
 * a query string lands in every access log between here and the browser.
 *
 * The inputs are uncontrolled. React holds the refusals; the DOM holds the values, which is what
 * keeps them across a refusal without a single piece of per-field state.
 *
 * Both runtimes call the same pure functions from `src/lib/`, so there is one implementation of
 * every rule rather than two that drift. The browser's check is a courtesy: the server re-reads
 * the age pass and re-validates, and its decision is the one that counts. Criterion 41.
 *
 * Without JavaScript the form still posts, the server still decides, and refusals come back as
 * codes in the query string — with the fields empty, because no value travels with them.
 * Criterion 40.
 */
export const MemberDetailsForm = ({
  action,
  dateOfBirth,
  revisions,
  refusals = [],
}: MemberDetailsFormProps) => {
  const [shown, setShown] = useState<readonly MemberDetailsFieldRefusal[]>(refusals)
  const writtenDate = formatDateOfBirth(dateOfBirth)

  const messages = new Map(
    shown.map(({ field, reason }) => [field, memberDetailsRefusalMessage(reason, writtenDate)]),
  )

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    /*
     * The revisions this page was rendered with, which is the right comparison for the browser to
     * make: it tells a member their box is unticked without a round trip. It cannot tell them a
     * document was revised a moment ago, and it does not try — the server re-reads what is in
     * force, and its answer is the one that counts.
     */
    const outcome = validateMemberDetails(
      readMemberDetailsInput(new FormData(event.currentTarget)),
      dateOfBirth,
      revisions,
    )

    if (outcome.status === 'refused') {
      // Nothing reaches the server, so nothing the visitor typed leaves the page.
      event.preventDefault()
      setShown(outcome.refusals)

      return
    }

    setShown([])
  }

  return (
    <form action={action} onSubmit={handleSubmit} className="flex flex-col gap-6">
      <ErrorSummary refusals={shown} dateOfBirth={writtenDate} />

      {/* One column on a phone, two from the medium breakpoint up. */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {FIELDS.map((field) => (
          <div key={field.name} className={field.fullRow ? 'md:col-span-2' : undefined}>
            <TextField
              name={field.name}
              label={MEMBER_DETAILS_COPY.fields[field.name].label}
              hint={MEMBER_DETAILS_COPY.fields[field.name].hint || undefined}
              error={messages.get(field.name)}
              autoComplete={field.autoComplete}
              inputMode={field.inputMode}
              maxLength={field.maxLength}
              formatOnBlur={field.formatOnBlur}
              filterOnInput={field.filterOnInput}
            />
          </div>
        ))}
      </div>

      {/*
        * Below the fields and above the submit control: a member reads what they are agreeing to
        * last, immediately before agreeing to it.
        */}
      <ConsentGroup revisions={revisions} messages={messages} />

      <button type="submit" className={`${SUBMIT} self-start`}>
        {MEMBER_DETAILS_COPY.submit}
      </button>
    </form>
  )
}

/** The field order the form renders, so a caller ordering refusals matches what is on screen. */
export const MEMBER_DETAILS_FORM_FIELDS = MEMBER_DETAILS_FIELDS

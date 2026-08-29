'use client'

import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ConsentGroup } from './ConsentGroup'
import { ErrorSummary } from './ErrorSummary'
import { TextField } from './TextField'
import {
  MEMBER_DETAILS_FIELDS,
  mergeMemberDetailsRefusals,
  readMemberDetailsInput,
  validateMemberDetails,
} from '@/lib/member-details'
import type { MemberDetailField, MemberDetailsFieldRefusal } from '@/lib/member-details'
import { MEMBER_DETAILS_COPY, formatDateOfBirth, memberDetailsRefusalMessage } from '@/lib/member-details-content'
import { requestNicknameAvailability } from '@/lib/nickname-availability'
import { NICKNAME_MAX_LENGTH, checkNickname, nicknameKey } from '@/lib/nickname'
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
  /**
   * Whether leaving this field asks the API about its value.
   *
   * Only the nickname has it, and only the nickname can. A nickname is a claim against other
   * members, so "is this one free" is a question the club may answer out loud. The address, the
   * mobile number and the identity number are the opposite: a live answer about any of those would
   * make this form a way to ask whether a named person is a member here, so there is no endpoint to
   * ask and this flag is not something a future field should acquire without that argument being
   * made again. See design/features/sign-up.md section 7.
   */
  readonly asksTheApiOnBlur?: true
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
  {
    name: 'nickname',
    autoComplete: 'nickname',
    maxLength: NICKNAME_MAX_LENGTH,
    fullRow: true,
    asksTheApiOnBlur: true,
  },
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
 * One field asks the API a question on the way out of it: whether the nickname is already
 * somebody's. It is the only field that may — see `asksTheApiOnBlur` below — and the answer is a
 * courtesy rather than a gate, because the write asks again. A check that cannot be made is
 * reported as itself, not as a refusal: the member is told, given a reference to quote, and left
 * free to submit. See design/features/sign-up.md section 7.
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
  /**
   * The nickname the API said belongs to somebody, in its comparable form, or null.
   *
   * The key rather than a boolean, so the submit can tell whether the answer is still about the
   * value in the field. A member who reads "that nickname is taken", types a different one and
   * clicks straight through gives the browser no time to ask again — and refusing that submission
   * on the strength of the previous answer would be refusing the wrong nickname.
   */
  const [taken, setTaken] = useState<string | null>(null)
  /**
   * The check that could not be made, and the reference that says where the reason is written.
   *
   * `reference` is null when the browser could not reach this site at all: there is no line on our
   * side to point anybody at, so none is quoted.
   */
  const [checkFailed, setCheckFailed] = useState<{ reference: string | null } | null>(null)

  /** The last nickname asked about. Tabbing through a field unchanged is not a new question. */
  const asked = useRef<string | null>(null)
  /** Answers can arrive out of order; only the newest question's answer may be shown. */
  const sequence = useRef(0)

  const writtenDate = formatDateOfBirth(dateOfBirth)

  /*
   * What the API decided, as a refusal like any other. Separate from `shown` all the way to the
   * field, because the two arrive at different moments and only one of them may move focus: see
   * the error summary below.
   */
  const live: readonly MemberDetailsFieldRefusal[] =
    taken === null ? [] : [{ field: 'nickname', reason: 'nickname-unavailable' }]

  /*
   * `shown` first, so it wins the nickname. A submit that refused the nickname on its own rules is
   * telling the member to fix its shape, and "that nickname is taken" about a value that cannot be
   * a nickname would be both wrong and impossible to act on.
   */
  const messages = new Map(
    mergeMemberDetailsRefusals(shown, live).map(({ field, reason }) => [
      field,
      memberDetailsRefusalMessage(reason, writtenDate),
    ]),
  )

  /*
   * Not a refusal, so not in `messages` and not in the summary: the nickname may be free, may be
   * taken, and nobody could find out. The member is told, told what to quote if they want to report
   * it, and left to carry on.
   */
  const nicknameNotice =
    checkFailed === null
      ? undefined
      : [
          MEMBER_DETAILS_COPY.checkFailed.nickname,
          checkFailed.reference === null
            ? null
            : MEMBER_DETAILS_COPY.checkFailed.reference(checkFailed.reference),
        ]
          .filter((line): line is string => line !== null)
          .join(' ')

  /**
   * Asks the API whether the nickname just left behind is free.
   *
   * On blur, because that is the moment a value is finished with, and the alternative — asking as
   * it is typed — sends a member's half-written name to the API a dozen times and answers each
   * time about something they have already changed.
   *
   * Nothing is asked unless the nickname's own rules accept it first. A malformed value has a
   * refusal of its own to show and nothing anybody else can add, and sending it would spend a
   * request to be told what this browser already knew.
   *
   * A failure is not an answer. The field is left alone, the member is told the check could not be
   * made, and the submission is not blocked: `/api/members/register` asks the same question inside
   * the transaction that writes, so the protection is where it has to be and this is a courtesy
   * ahead of it. Trapping somebody in a form because a request failed would cost them the
   * membership to protect a nickname.
   */
  const askWhetherTheNicknameIsFree = async (value: string) => {
    const nickname = checkNickname(value)

    if (nickname.status !== 'valid') {
      asked.current = null
      setTaken(null)
      setCheckFailed(null)

      return
    }

    const key = nicknameKey(nickname.nickname)

    if (key === asked.current) return

    asked.current = key
    const question = (sequence.current += 1)

    const outcome = await requestNicknameAvailability(nickname.nickname)

    // A later blur has already asked about a later value; this answer is about the past.
    if (question !== sequence.current) return

    if (outcome.status === 'unusable') {
      /*
       * `asked` is cleared as well as the verdict. A failure is not something to remember as an
       * answer: coming back to the field asks again rather than showing a stale notice for a
       * nickname nobody ever managed to check.
       */
      asked.current = null
      setTaken(null)
      setCheckFailed({ reference: outcome.reference })

      return
    }

    setCheckFailed(null)
    setTaken(outcome.status === 'taken' ? key : null)
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    const input = readMemberDetailsInput(new FormData(event.currentTarget))

    /*
     * The revisions this page was rendered with, which is the right comparison for the browser to
     * make: it tells a member their box is unticked without a round trip. It cannot tell them a
     * document was revised a moment ago, and it does not try — the server re-reads what is in
     * force, and its answer is the one that counts.
     */
    const outcome = validateMemberDetails(input, dateOfBirth, revisions)

    /*
     * The API's answer, applied only while it is still about the value being submitted. A nickname
     * reported taken and then changed is not refused here — nobody has asked about the new one, and
     * the register call is what will.
     */
    const stillTaken: readonly MemberDetailsFieldRefusal[] =
      taken !== null && taken === nicknameKey(input.nickname) ? live : []

    const refused = mergeMemberDetailsRefusals(
      outcome.status === 'refused' ? outcome.refusals : [],
      stillTaken,
    )

    if (refused.length > 0) {
      // Nothing reaches the server, so nothing the visitor typed leaves the page.
      event.preventDefault()
      setShown(refused)

      return
    }

    setShown([])
  }

  return (
    <form action={action} onSubmit={handleSubmit} className="flex flex-col gap-6">
      {/*
        * `shown` only, never the API's answer on its own. The summary takes focus when it appears,
        * which is right after a submit and wrong while somebody is typing: a nickname answered
        * two fields ago would haul the caret back up the form out of their last keystroke. The
        * answer reaches the summary at the submit, along with everything else.
        */}
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
              notice={field.asksTheApiOnBlur ? nicknameNotice : undefined}
              autoComplete={field.autoComplete}
              inputMode={field.inputMode}
              maxLength={field.maxLength}
              formatOnBlur={field.formatOnBlur}
              filterOnInput={field.filterOnInput}
              onBlurValue={field.asksTheApiOnBlur ? askWhetherTheNicknameIsFree : undefined}
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

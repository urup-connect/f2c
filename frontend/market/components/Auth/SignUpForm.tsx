'use client'

import Link from 'next/link'
import { useActionState } from 'react'

import { ButtonLink } from '@/components/Ui/ButtonLink'
import { Feedback } from '@/components/Ui/Feedback'
import { TextField } from '@/components/Ui/TextField'
import { filterSaMobileInput, formatSaMobileNumber } from '@/lib/sa-mobile-number'
import {
  SIGN_UP_IDLE,
  signUpRefusalFor,
  type SignUpFormState,
  type SignUpInput,
} from '@/lib/sign-up'
import { SIGN_UP, SIGN_UP_OUTCOME, SIGN_UP_REFUSAL_MESSAGES } from '@/lib/sign-up-content'

type SignUpFormProps = {
  /** The server action that validates, registers, and answers with the next state. */
  action: (state: SignUpFormState, form: FormData) => Promise<SignUpFormState>
}

const PRIMARY =
  'inline-flex h-12 w-full items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf disabled:opacity-60 sm:w-auto'

/** Blank fields, for the first render and for every state that keeps nothing typed. */
const EMPTY: SignUpInput = { firstName: '', lastName: '', email: '', mobile: '' }

/**
 * Create an account: four fields, one of them optional.
 *
 * **A form element with a server action, not a `fetch`.** Three things follow from that and each is
 * the reason for it: it submits without JavaScript, so an account can be created on a phone with a
 * failed bundle; the registration call is made from our server rather than from a browser, which is
 * what keeps the unauthenticated endpoint behind one origin; and the refusals come back as data
 * rather than as a rendered message, so this component decides how each reads.
 *
 * **Every terminal state replaces the form rather than sitting above it.** A confirmation with a
 * filled-in form still underneath it invites a second submission of the same details, and the second
 * one would be answered identically — which is correct behaviour reading as a bug.
 */
export const SignUpForm = ({ action }: SignUpFormProps) => {
  const [state, submit, isPending] = useActionState(action, SIGN_UP_IDLE)

  if (state.status === 'accepted') {
    return (
      <div className="flex flex-col gap-4">
        <h2 className="font-display text-2xl tracking-display text-leaf">
          {SIGN_UP_OUTCOME.acceptedHeading}
        </h2>
        <p role="status" className="font-sans text-base leading-relaxed text-foreground">
          {`${SIGN_UP_OUTCOME.acceptedBodyPrefix} ${state.email} ${SIGN_UP_OUTCOME.acceptedBodySuffix}`}
        </p>
        <div>
          <ButtonLink href="/sign-in">{SIGN_UP_OUTCOME.acceptedAction}</ButtonLink>
        </div>
      </div>
    )
  }

  if (state.status === 'unavailable') {
    return (
      <div className="flex flex-col gap-4">
        <h2 className="font-display text-2xl tracking-display text-leaf">
          {SIGN_UP_OUTCOME.unavailableHeading}
        </h2>
        {/*
         * `status`, not `alert`. Nothing has gone wrong and nobody did anything incorrectly — the
         * store is not taking accounts yet, which is a fact about the store rather than a refusal of
         * this submission.
         */}
        <p role="status" className="font-sans text-base leading-relaxed text-foreground">
          {SIGN_UP_OUTCOME.unavailableBody}
        </p>
      </div>
    )
  }

  const values = state.status === 'invalid' ? state.values : EMPTY
  const refusals = state.status === 'invalid' ? state.refusals : []

  const refusal = (field: keyof SignUpInput) => {
    const reason = signUpRefusalFor(refusals, field)
    return reason === undefined ? undefined : SIGN_UP_REFUSAL_MESSAGES[reason]
  }

  return (
    <form action={submit} className="flex flex-col gap-6">
      {/*
       * One `alert` for the whole form rather than a summary listing every field. The form is four
       * fields long: a screen reader user who has been told something needs correcting reaches the
       * first refusal in one Tab, and each field carries its own message and `aria-invalid`. The
       * club's `ErrorSummary` earns its keep over eleven fields; here it would be a second copy of
       * what is already beneath it.
       */}
      {refusals.length > 0 ? <Feedback problem={SIGN_UP_OUTCOME.refusedHeading} /> : null}

      {state.status === 'failed' ? <Feedback problem={SIGN_UP_OUTCOME.failedBody} /> : null}

      <div className="grid gap-6 sm:grid-cols-2">
        <TextField
          name="firstName"
          label={SIGN_UP.firstNameLabel}
          defaultValue={values.firstName}
          autoComplete="given-name"
          error={refusal('firstName')}
        />
        <TextField
          name="lastName"
          label={SIGN_UP.lastNameLabel}
          defaultValue={values.lastName}
          autoComplete="family-name"
          error={refusal('lastName')}
        />
      </div>

      <TextField
        name="email"
        label={SIGN_UP.emailLabel}
        hint={SIGN_UP.emailHint}
        defaultValue={values.email}
        autoComplete="email"
        inputMode="email"
        error={refusal('email')}
      />

      <TextField
        name="mobile"
        label={SIGN_UP.mobileLabel}
        hint={SIGN_UP.mobileHint}
        defaultValue={values.mobile}
        autoComplete="tel-national"
        inputMode="tel"
        filterOnInput={filterSaMobileInput}
        formatOnBlur={formatSaMobileNumber}
        error={refusal('mobile')}
      />

      <p className="font-sans text-sm leading-relaxed text-muted-foreground">
        {SIGN_UP.noPassword}
      </p>

      <div>
        <button type="submit" disabled={isPending} className={PRIMARY}>
          {isPending ? SIGN_UP.submitting : SIGN_UP.submit}
        </button>
      </div>

      <p className="font-sans text-sm text-muted-foreground">
        {SIGN_UP.haveAccount}{' '}
        <Link
          href="/sign-in"
          className="text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf"
        >
          {SIGN_UP.haveAccountLink}
        </Link>
      </p>
    </form>
  )
}

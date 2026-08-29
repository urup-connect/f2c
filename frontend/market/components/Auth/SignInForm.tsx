'use client'

import { browserSupportsWebAuthn, startAuthentication } from '@simplewebauthn/browser'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

import { Feedback } from '@/components/Ui/Feedback'
import { loginWithCode, loginWithPasskey, sendLoginCode, startLogin } from '@/lib/api'
import {
  CODE_LENGTH,
  RESEND_COOLDOWN_SECONDS,
  apiProblem,
  destinationAfterSignIn,
  digitsOnly,
  passkeyProblem,
} from '@/lib/sign-in'
import { CODE_SENT_PREFIX, CODE_SENT_SUFFIX, SIGN_IN } from '@/lib/sign-in-content'

const INPUT =
  'w-full rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf'

const PRIMARY =
  'inline-flex h-12 w-full items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf disabled:opacity-60'

const QUIET =
  'font-sans text-sm text-primary underline underline-offset-4 hover:text-leaf-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-leaf disabled:no-underline disabled:opacity-60'

/**
 * Identifier-first sign-in: an address, then whichever credential Django asks for.
 *
 * The flow is Django's and is described in `design/features/authentication.md` section 3. What this
 * component adds is the two things a browser has to decide:
 *
 * **A failed passkey is not a dead end.** The customer is told what happened and offered a code, and
 * the offer changes its wording so it reads as a fallback rather than as the same button again. The
 * alternative — silently swapping the form out — leaves somebody who cancelled by accident looking
 * at a screen they did not ask for.
 *
 * **Everything that is not a passkey lands on the code step, including an address with no account.**
 * That is what keeps the two indistinguishable from the outside, and it is why the notice is
 * conditional: *if that address belongs to an account*.
 *
 * Where the club's copy of this component differs is one line: it sends a member to whichever of
 * three homes their role names, and this sends a customer to the one account area there is. That
 * asymmetry is the identity split, not an omission — see `lib/sign-in.ts`.
 */
export const SignInForm = () => {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [step, setStep] = useState<'email' | 'code'>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  /** Set when a passkey attempt failed, so the fallback is offered as one. */
  const [passkeyFailed, setPasskeyFailed] = useState(false)
  const [isBusy, setIsBusy] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  const finish = useCallback(() => {
    /*
     * The refresh is not optional and has to come first: every signed-in screen is a Server
     * Component that reads the session when it renders, and the router would otherwise serve one
     * from a cache built before the cookie existed.
     */
    router.refresh()
    router.push(destinationAfterSignIn(searchParams.get('next')))
  }, [router, searchParams])

  /** Move to the code step, sending a code first unless one has already gone out. */
  const goToCodeStep = async (alreadySent: boolean) => {
    if (!alreadySent) await sendLoginCode(email)

    setPasskeyFailed(false)
    setProblem(null)
    setNotice(`${CODE_SENT_PREFIX} ${email} ${CODE_SENT_SUFFIX}`)
    setCooldown(RESEND_COOLDOWN_SECONDS)
    setStep('code')
  }

  const handleEmailSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setProblem(null)
    setNotice(null)
    setIsBusy(true)

    try {
      const start = await startLogin(email)

      if (start.method === 'passkey' && start.options) {
        if (!browserSupportsWebAuthn()) {
          // Django prepared a challenge this browser cannot answer, and so sent no code. Ask for one
          // now rather than leaving the customer stuck.
          await goToCodeStep(false)
          return
        }

        try {
          const credential = await startAuthentication({ optionsJSON: start.options })
          await loginWithPasskey(email, credential)
          finish()
          return
        } catch (caught) {
          setProblem(passkeyProblem(caught))
          setPasskeyFailed(true)
          return
        }
      }

      // login/start has already emailed the code.
      await goToCodeStep(true)
    } catch (caught) {
      setProblem(apiProblem(caught))
    } finally {
      setIsBusy(false)
    }
  }

  const handleCodeSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setProblem(null)
    setNotice(null)
    setIsBusy(true)

    try {
      await loginWithCode(email, code)
      finish()
    } catch (caught) {
      setProblem(apiProblem(caught))
      setIsBusy(false)
    }
    /*
     * No `finally`. On success this component is navigating away, and clearing the busy flag would
     * re-enable the button underneath somebody who has already been signed in.
     */
  }

  const handleRequestCode = async () => {
    setProblem(null)
    setIsBusy(true)

    try {
      await goToCodeStep(false)
    } catch (caught) {
      setProblem(apiProblem(caught))
    } finally {
      setIsBusy(false)
    }
  }

  const handleStartOver = () => {
    setStep('email')
    setCode('')
    setProblem(null)
    setNotice(null)
    setPasskeyFailed(false)
  }

  if (step === 'code') {
    return (
      <form onSubmit={handleCodeSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="code" className="font-sans text-base font-medium text-foreground">
            {SIGN_IN.codeLabel}
          </label>
          <p id="code-hint" className="font-sans text-sm text-muted-foreground">
            {`${SIGN_IN.codeHintPrefix} ${email}. ${SIGN_IN.codeHintSuffix}`}
          </p>
          <input
            id="code"
            name="code"
            type="text"
            value={code}
            onChange={(event) => setCode(digitsOnly(event.target.value))}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={CODE_LENGTH}
            autoFocus
            aria-describedby="code-hint"
            className={`${INPUT} tracking-[0.4em]`}
          />
        </div>

        <Feedback problem={problem} notice={notice} />

        <button type="submit" disabled={isBusy} className={PRIMARY}>
          {isBusy ? SIGN_IN.codeChecking : SIGN_IN.codeSubmit}
        </button>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={handleRequestCode}
            disabled={isBusy || cooldown > 0}
            className={QUIET}
          >
            {cooldown > 0 ? `${SIGN_IN.resendWaitingPrefix} ${cooldown}s` : SIGN_IN.resend}
          </button>

          <button type="button" onClick={handleStartOver} disabled={isBusy} className={QUIET}>
            {SIGN_IN.startOver}
          </button>
        </div>
      </form>
    )
  }

  return (
    <form onSubmit={handleEmailSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <label htmlFor="email" className="font-sans text-base font-medium text-foreground">
          {SIGN_IN.emailLabel}
        </label>
        <input
          id="email"
          name="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          // Lets the browser offer a saved passkey inline where it can.
          autoComplete="username webauthn"
          required
          autoFocus
          className={INPUT}
        />
      </div>

      <Feedback problem={problem} notice={notice} />

      <button type="submit" disabled={isBusy} className={PRIMARY}>
        {isBusy ? SIGN_IN.emailChecking : SIGN_IN.emailContinue}
      </button>

      <div className="text-center">
        <button
          type="button"
          onClick={handleRequestCode}
          disabled={isBusy || email.length === 0}
          className={QUIET}
        >
          {passkeyFailed ? SIGN_IN.requestCodeInstead : SIGN_IN.requestCode}
        </button>
      </div>
    </form>
  )
}

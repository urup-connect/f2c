'use client'

import { browserSupportsWebAuthn, startRegistration } from '@simplewebauthn/browser'
import { useState, useSyncExternalStore } from 'react'

import {
  deletePasskey,
  listPasskeys,
  passkeyRegistrationOptions,
  registerPasskey,
  type Passkey,
} from '@/lib/api'
import { ClubCard } from '@/components/Club/ClubCard'
import { PASSKEYS_CARD } from '@/lib/club-content'
import {
  PASSKEY_NAME_MAX,
  enrolmentProblem,
  passkeyNameToSend,
  trimPasskeyName,
} from '@/lib/passkeys'
import { apiProblem } from '@/lib/sign-in'
import { PasskeyList } from './PasskeyList'

type PasskeyCardProps = {
  /**
   * The list as the server rendered it. The card takes it as its starting state rather than
   * fetching on mount, so a member with passkeys sees them in the first paint and there is no
   * empty flash saying they have none.
   */
  initial: readonly Passkey[]
  /** True when the server could not read the list. The card then says so rather than saying zero. */
  unavailable?: boolean
}

const INPUT =
  'w-full rounded-control border-2 border-border bg-surface px-3 py-2 font-sans text-base text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green sm:max-w-xs'

/*
 * Whether this browser can make a passkey, read through `useSyncExternalStore`.
 *
 * `'use client'` does not mean "browser only" — the club pages server-render this component first,
 * and on the server there is no `navigator` to ask. Reading the capability during render therefore
 * answered *no* on the server for every browser alive, which put "this browser cannot create
 * passkeys" into the server HTML of a machine perfectly able to make one.
 *
 * `useSyncExternalStore` is the primitive for exactly this: a value that has one answer on the
 * server and another in the browser, resolved without a hydration mismatch and without an effect
 * that sets state on mount.
 *
 * The **server snapshot is optimistic**, because the two errors are not symmetrical. A capable
 * browser told it cannot enrol is a member who gives up on a feature that works; an incapable one
 * offered the button gets a refusal it can act on.
 *
 * Nothing subscribes, because nothing changes: a browser does not gain WebAuthn support while the
 * page is open. Both functions are module-level so their identity is stable across renders.
 */
const subscribeToNothing = () => () => {}

const assumeSupported = () => true

/**
 * Enrol, list and revoke the passkeys on this account.
 *
 * A client component because WebAuthn is a browser ceremony: `navigator.credentials.create()` runs
 * on the device and nothing about it can happen on the server.
 *
 * Three things here are decisions rather than implementation:
 *
 * **The list is re-read after enrolling rather than appended to.** Django owns the canonical list —
 * it names the credential, truncates the name and stamps the dates — so appending what this
 * component believes it created would show a member a row that differs from what was stored.
 *
 * **A browser that cannot do WebAuthn is told what to do instead**, not shown a button that will
 * fail. The emailed code is a first-class credential and remains the way in.
 *
 * **`initial` is trusted for the first paint.** A member who has passkeys should never see "no
 * passkey yet" for a frame before the real list arrives; that reads as though the club lost them.
 */
export const PasskeyCard = ({ initial, unavailable = false }: PasskeyCardProps) => {
  const [passkeys, setPasskeys] = useState<readonly Passkey[]>(initial)
  const [name, setName] = useState('')
  const [problem, setProblem] = useState<string | null>(unavailable ? PASSKEYS_CARD.loadFailed : null)
  const [isAdding, setIsAdding] = useState(false)
  const [removingId, setRemovingId] = useState<number | null>(null)

  const supported = useSyncExternalStore(
    subscribeToNothing,
    browserSupportsWebAuthn,
    assumeSupported,
  )

  const busy = isAdding || removingId !== null

  const handleAdd = async () => {
    setProblem(null)
    setIsAdding(true)

    try {
      const { options } = await passkeyRegistrationOptions()
      const credential = await startRegistration({ optionsJSON: options })
      await registerPasskey(credential, passkeyNameToSend(name, navigator.userAgent))

      setPasskeys(await listPasskeys())
      setName('')
    } catch (caught) {
      // Two kinds of failure arrive here and they read differently to a member: the
      // authenticator refusing is about this device, Django refusing is about the account.
      setProblem(enrolmentProblem(caught))
    } finally {
      setIsAdding(false)
    }
  }

  const handleRemove = async (id: number) => {
    setProblem(null)
    setRemovingId(id)

    try {
      await deletePasskey(id)
      setPasskeys((current) => current.filter((passkey) => passkey.id !== id))
    } catch (caught) {
      setProblem(apiProblem(caught))
    } finally {
      setRemovingId(null)
    }
  }

  return (
    <ClubCard heading={PASSKEYS_CARD.heading} standfirst={PASSKEYS_CARD.standfirst}>
      <div className="flex flex-col gap-6">
        <PasskeyList
          passkeys={passkeys}
          removingId={removingId}
          busy={busy}
          onRemove={handleRemove}
        />

        {problem ? (
          <p
            role="alert"
            className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
          >
            {problem}
          </p>
        ) : null}

        {supported ? (
          <div className="flex flex-col gap-3">
            <label
              htmlFor="passkey-name"
              className="font-sans text-base font-medium text-foreground"
            >
              {PASSKEYS_CARD.addLabel}
            </label>
            <p id="passkey-name-hint" className="font-sans text-sm text-muted-foreground">
              {PASSKEYS_CARD.addHint}
            </p>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                id="passkey-name"
                name="passkey-name"
                type="text"
                value={name}
                onChange={(event) => setName(trimPasskeyName(event.target.value))}
                maxLength={PASSKEY_NAME_MAX}
                aria-describedby="passkey-name-hint"
                className={INPUT}
              />

              <button
                type="button"
                onClick={handleAdd}
                disabled={busy}
                className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
              >
                {isAdding ? PASSKEYS_CARD.adding : PASSKEYS_CARD.add}
              </button>
            </div>
          </div>
        ) : (
          <p className="font-sans text-sm leading-relaxed text-muted-foreground">
            {PASSKEYS_CARD.unsupported}
          </p>
        )}
      </div>
    </ClubCard>
  )
}

import type { Passkey } from '@/lib/api'
import { PASSKEYS_CARD } from '@/lib/club-content'
import { passkeyTimeline } from '@/lib/passkeys'

type PasskeyListProps = {
  passkeys: readonly Passkey[]
  /** Which one is being removed, so only that row's button says so. `null` when none is. */
  removingId: number | null
  /** True while any request is in flight: every button is stood down, not just the busy one. */
  busy: boolean
  onRemove: (id: number) => void
}

/**
 * The passkeys on this account, and the way to revoke one.
 *
 * Presentational: it fetches nothing and owns no state, so the list a member sees is whatever the
 * card decided it is. That is what makes "removing this one" and "a request is in flight"
 * separately testable — they are two props here and were one boolean when this lived inside the
 * component that fetched.
 *
 * Every row names the passkey in its own button. A screen full of buttons all called "Remove" is
 * unusable from a screen reader's list of controls, and the visible label stays short because the
 * name is added through `aria-label`.
 */
export const PasskeyList = ({ passkeys, removingId, busy, onRemove }: PasskeyListProps) => {
  if (passkeys.length === 0) {
    return (
      <p className="rounded-control border-2 border-dashed border-border px-4 py-3 font-sans text-sm text-muted-foreground">
        {PASSKEYS_CARD.empty}
      </p>
    )
  }

  return (
    <ul className="flex list-none flex-col gap-3">
      {passkeys.map((passkey) => (
        <li
          key={passkey.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-control border-2 border-border px-4 py-3"
        >
          <div className="flex flex-col gap-1">
            <p className="font-sans text-base font-medium text-foreground">
              {passkey.name}
              {passkey.backed_up ? (
                <span className="ml-2 rounded-pill bg-sage-green px-2 py-0.5 font-sans text-xs uppercase tracking-label text-forest-green">
                  {PASSKEYS_CARD.synced}
                </span>
              ) : null}
            </p>
            <p className="font-sans text-sm text-muted-foreground">
              {passkeyTimeline(passkey)}
            </p>
          </div>

          <button
            type="button"
            onClick={() => onRemove(passkey.id)}
            disabled={busy}
            aria-label={`${PASSKEYS_CARD.remove}: ${passkey.name}`}
            className="inline-flex h-10 items-center justify-center rounded-pill border-2 border-primary bg-transparent px-5 font-sans text-sm font-medium text-primary transition-colors hover:bg-sage-green focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
          >
            {removingId === passkey.id ? PASSKEYS_CARD.removing : PASSKEYS_CARD.remove}
          </button>
        </li>
      ))}
    </ul>
  )
}

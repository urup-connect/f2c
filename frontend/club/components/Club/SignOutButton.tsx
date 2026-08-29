'use client'

import { useRouter } from 'next/navigation'
import { useState, useTransition } from 'react'

import { logout } from '@/lib/api'
import { CLUB_SHELL } from '@/lib/club-content'

/**
 * Ends the session and returns to the front door.
 *
 * `router.refresh()` before the navigation, and it is not optional: every signed-in screen is a
 * Server Component that read the session when it rendered, and the App Router will happily serve
 * one of those from its client-side cache after the cookie is gone. The refresh discards that
 * cache, so what the member sees next was rendered without a session.
 *
 * **The failure is not swallowed, and it is not shown either.** If the API cannot be reached the
 * cookie may or may not have been cleared, and the honest thing is to send the member to the front
 * door regardless: the next screen asks Django who they are and will show them signed out if they
 * are. Leaving them on a club page beside a red message would be worse — they asked to leave.
 */
export const SignOutButton = () => {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [isSigningOut, setIsSigningOut] = useState(false)

  const handleClick = async () => {
    setIsSigningOut(true)

    try {
      await logout()
    } catch {
      // Deliberately silent. See above.
    }

    startTransition(() => {
      router.refresh()
      router.push('/')
    })
  }

  const busy = isSigningOut || isPending

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={busy}
      className="inline-flex h-10 items-center justify-center rounded-pill border-2 border-cream-warm bg-transparent px-5 font-sans text-sm font-medium text-cream-warm transition-colors hover:bg-cream-warm/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cream-warm disabled:opacity-60"
    >
      {busy ? CLUB_SHELL.signingOut : CLUB_SHELL.signOut}
    </button>
  )
}

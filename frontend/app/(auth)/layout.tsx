import type { ReactNode } from 'react'

/**
 * Shared frame for the signed-out screens.
 *
 * A route group, so it shapes the layout without appearing in the URL: the screens stay at
 * /login and /signup, where the authentication library's page configuration will point.
 *
 * No `robots` field here, deliberately. These screens inherit `noindex, nofollow` from the
 * root layout, which is the guarantee the design doc relies on — see section 6.3.
 *
 * The card itself is not here. It was, until sign-up needed a wider one, and a child cannot exceed
 * its parent's maximum width — so each page renders its own `AuthCard` at the width that screen
 * needs. This owns the landmark and the centring, and nothing else.
 * See design/features/member-details-at-sign-up.md section 5.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-16">{children}</main>
  )
}

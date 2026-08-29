import type { ReactNode } from 'react'

/**
 * Shared frame for the signed-out screens.
 *
 * A route group, so it shapes the layout without appearing in the URL: the screens stay at /sign-in
 * and /sign-up.
 *
 * No `robots` field here, deliberately. These screens inherit `noindex, nofollow` from the root
 * layout, and they are not on the indexable list in `lib/seo.ts` — a sign-in page in a search index
 * is a page somebody arrives at instead of the front door.
 *
 * The card itself is not here: sign-up is a four-field form and sign-in is one field, and a child
 * cannot exceed its parent's maximum width, so each page renders its own `AuthCard` at the width that
 * screen needs. This owns the landmark and the centring, and nothing else.
 */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return <main className="flex flex-1 items-center justify-center px-6 py-16">{children}</main>
}

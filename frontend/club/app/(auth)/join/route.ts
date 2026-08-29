import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { AGE_PASS_COOKIE } from '@/lib/age-gate-cookie'

/*
 * The landing page's way in to joining: a clean start, every time.
 *
 * The landing page's Sign Up buttons point here rather than at `/signup`, because `/signup`'s
 * guard admits anyone still holding a valid age pass — a returning visitor would walk straight
 * back into the member details form, against a date of birth they can neither see nor change.
 * Coming from the landing page is a decision to begin, so the pass is discarded and the age gate
 * is asked again. The gate is reached with no query string either, so a refusal from a previous
 * attempt is not still on the screen.
 *
 * A Route Handler rather than a link straight to `/age-check`, because a cookie cannot be cleared
 * while a Server Component renders. It is also the only place the pass is deliberately thrown
 * away, which is easier to find here than folded into a page.
 *
 * `/signup`'s own guard is untouched. This is an additional entry point, not a replacement for it:
 * a bookmark, a shared link or any entry point added later is still gated by the check on the
 * route that needs it. See design/features/sign-up.md section 2.
 *
 * No route segment config. Reading the cookie store is runtime data, so this never runs at build
 * time and never answers from a cache — which matters, because a cached redirect clears nobody's
 * cookie. `export const dynamic` would say the same thing less reliably: Next removes it once
 * Cache Components is enabled.
 */
export const GET = async () => {
  const store = await cookies()

  /*
   * The path has to match the one the pass was set with, or the browser keeps the cookie and the
   * gate is handed back the date it was meant to forget. See `agePassCookieOptions`.
   */
  store.delete({ name: AGE_PASS_COOKIE, path: '/' })

  // `redirect` signals by throwing, so it sits after the delete rather than around it.
  redirect('/age-check')
}

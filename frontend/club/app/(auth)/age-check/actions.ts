'use server'

import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { checkAge } from '@/lib/age-gate'
import { AGE_PASS_COOKIE, agePassCookieOptions, serialiseAgePass } from '@/lib/age-gate-cookie'
import { siteConfig } from '@/lib/site'

/**
 * A `FormData` entry is a string or a `File`. A file in one of these fields is not something a
 * visitor can do through the form, so it is read as no answer at all rather than special-cased.
 */
const field = (formData: FormData, name: string) => {
  const value = formData.get(name)

  return typeof value === 'string' ? value : ''
}

/**
 * Decides the age check, and goes nowhere else.
 *
 * The refusal path redirects rather than returning state, so the outcome is identical with
 * JavaScript and without it, and so the page stays a Server Component with nothing to hold. Only
 * the reason travels in the URL: never the date, which would otherwise land in every access log.
 *
 * See design/features/age-gate-before-sign-up.md sections 6.1 and 7.
 */
export const submitAgeCheck = async (formData: FormData) => {
  const now = new Date()

  const outcome = checkAge(
    {
      day: field(formData, 'day'),
      month: field(formData, 'month'),
      year: field(formData, 'year'),
    },
    now,
  )

  /*
   * `redirect` signals by throwing, so both calls sit outside any try/catch and the cookie is
   * written before the pass redirect rather than after it.
   */
  if (outcome.status === 'refused') {
    redirect(`/age-check?refused=${outcome.reason}`)
  }

  const store = await cookies()

  store.set(
    AGE_PASS_COOKIE,
    serialiseAgePass({ dateOfBirth: outcome.dateOfBirth, assertedAt: now.toISOString() }),
    agePassCookieOptions(siteConfig()),
  )

  redirect('/signup')
}

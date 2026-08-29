import { apiBaseUrl } from '@/lib/api'
import { newErrorReference } from '@/lib/error-reference'

/**
 * Is this nickname free — asked by the sign-up form, answered by Django, proxied here.
 *
 * The only route handler in the product, and it exists for reasons that are all about what the
 * browser is allowed to know.
 *
 * **Django's address stays out of the bundle.** The browser posts to this origin. Nothing in a
 * client component has to know where the API lives, and `NEXT_PUBLIC_DJANGO_API_URL` is not made a
 * requirement of the sign-up page.
 *
 * **The cause is logged where the member cannot read it.** A failure is answered with an opaque
 * reference and nothing else: no status code from Django, no `detail`, no exception text. The line
 * that says which of those it was is written here, server-side, against that reference. That is the
 * whole shape of the requirement — the member is told something failed and given a handle on it,
 * without the screen or the browser's network log carrying anything about the fault or about them.
 *
 * **The nickname is not logged.** Not on the happy path and not on a failure. It is the mildest
 * value this form collects and it is still a member's chosen name; a reference plus a status code is
 * enough to diagnose anything this route can do wrong. The one thing worth knowing about the value
 * — that Django refused it as malformed when the browser's own rules accepted it — is logged as the
 * fact that it happened, not as the value it happened to.
 *
 * **The answer is one boolean.** Django's body is re-read and re-written rather than streamed back,
 * so a field added to that response later cannot reach a browser through here without somebody
 * deciding it should.
 *
 * A POST, because the nickname travels in the body. A GET would put it in this application's own
 * access log, in the browser's history, and in any cache in between.
 */

/** What the browser gets. Mirrors `NicknameAvailabilityBody` in lib/nickname-availability.ts. */
type Answer = { available: boolean } | { reference: string }

const answer = (body: Answer, status: number) =>
  Response.json(body, {
    status,
    // Says the obvious out loud: the answer is about another member's record a moment ago.
    headers: { 'Cache-Control': 'no-store' },
  })

/**
 * A failure the member is shown, and the line that says what it actually was.
 *
 * One function, so there is no path out of here that reports a fault without logging its cause —
 * an opaque reference with nothing behind it is worse than no reference at all.
 */
const unusable = (cause: string) => {
  const reference = newErrorReference()

  console.error(`[nickname-availability] ${reference}: ${cause}`)

  // 502, not 200: this application could not get an answer, and monitoring should see that as
  // clearly as the member does. The body carries the reference and nothing else.
  return answer({ reference }, 502)
}

export const POST = async (request: Request) => {
  let submitted: unknown

  try {
    submitted = await request.json()
  } catch {
    submitted = null
  }

  const nickname =
    submitted !== null && typeof submitted === 'object'
      ? (submitted as { nickname?: unknown }).nickname
      : undefined

  /*
   * Not something the form can do, so it is not worded for a member: the sign-up page checks the
   * nickname's own rules before asking, and asks with a string when it does.
   */
  if (typeof nickname !== 'string') {
    return unusable('the request carried no nickname')
  }

  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}/api/members/nickname/availability`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      body: JSON.stringify({ nickname }),
    })
  } catch {
    return unusable('the API is unreachable')
  }

  if (response.status === 422) {
    /*
     * Django refused as malformed a nickname the browser's rules accepted. Nothing is wrong with
     * the member — the two implementations have drifted, and this line is the only warning anyone
     * gets. Logged without the value: the fact that it happened is what needs fixing.
     */
    return unusable('the API refused the nickname as malformed, which the browser rules accepted')
  }

  if (!response.ok) {
    // Includes 429. A member who has tried a great many nicknames is told the check failed, not
    // that they have been counted — and they can still submit, which is what matters.
    return unusable(`the API answered ${response.status}`)
  }

  let body: unknown

  try {
    body = await response.json()
  } catch {
    return unusable('the API answered 200 with a body that does not parse')
  }

  const available =
    body !== null && typeof body === 'object'
      ? (body as { available?: unknown }).available
      : undefined

  /*
   * A 200 that does not carry a boolean is not believed. Reading a missing field as "taken" would
   * send a member off to invent a nickname for no reason; reading it as "available" would promise
   * one that may be somebody else's.
   */
  if (typeof available !== 'boolean') {
    return unusable('the API answered 200 without saying whether the nickname is available')
  }

  return answer({ available }, 200)
}

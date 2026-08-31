/**
 * Every word on the blocked-membership screen, in one place.
 *
 * **The screen exists because a redirect to the landing page is not an answer.** A member whose
 * membership the club has blocked, or has not finished checking, used to be sent to the marketing
 * front page: no explanation, and a sign-up form they cannot use. See `lib/club-membership.ts`.
 *
 * Held to all four compliance rules and exempt from none. It takes no `CURRENCY` exemption because
 * it names no amount — that is deliberate rather than incidental. A blocked membership is not
 * settled by paying, so a figure on this screen would invite exactly the payment the API now
 * refuses with a 409.
 *
 * **One wording decision runs through it.** Nothing here says why the club blocked anybody. The
 * screen is served over a session, but a shared device and a forwarded screenshot are both ordinary,
 * and a reason recorded by an administrator is not something to render into a page when an email to
 * the member is the private channel and already carries it. So the screen says where they stand and
 * how to ask; the reason travels by mail.
 *
 * Placed for structure and pending client and legal sign-off, like the rest of the member-facing
 * wording.
 */
import type { GateReason } from './club-membership'

/** The heading and body for one situation. */
export type BlockedNotice = {
  readonly heading: string
  readonly body: readonly string[]
  /** The label on the mailto link, or `null` where there is nothing to ask anybody. */
  readonly contact: string | null
}

export const BLOCKED_COPY = {
  /**
   * `blocked` — the club has suspended this membership.
   *
   * Says the club made a decision and that it can be looked at again, because a member who cannot
   * tell the difference between a block and a fault will write to support either way, and the
   * version that names it gets a more useful email.
   */
  blocked: {
    heading: 'Your membership is on hold',
    body: [
      'The club has placed a hold on your membership, so the member area is closed to you for now.',
      'Nothing has been deleted and your details are still with the club. A hold can be lifted by an administrator.',
      'If you would like this looked at again, write to us and quote the address you signed up with.',
    ],
    contact: 'Email the club',
  },

  /**
   * `awaiting-verification` — the application is with the club and unanswered.
   *
   * No contact label. There is nothing to ask for and nothing to correct; the club has the
   * application and is working through it. A "contact us" link here would generate mail that says
   * only "is it done yet", which serves nobody.
   */
  'awaiting-verification': {
    heading: 'We are still checking your application',
    body: [
      'Your application is with the club and has not been decided yet.',
      'There is nothing for you to do. We will email you at the address you signed up with as soon as it has been looked at.',
    ],
    contact: null,
  },

  /**
   * `not-settled-by-payment` — the fallback, and the wording is general on purpose.
   *
   * Reached by a placeholder, which cannot sign in and so never arrives, and by a membership state
   * Django has added since this bundle was built. The second is the one that matters: it must read
   * sensibly for a situation nobody has written copy for yet.
   */
  'not-settled-by-payment': {
    heading: 'The member area is closed to this account',
    body: [
      'This account cannot use the member area at the moment.',
      'If you think that is wrong, write to us and quote the address you signed up with.',
    ],
    contact: 'Email the club',
  },
} as const satisfies Partial<Record<GateReason, BlockedNotice>>

/**
 * The two strings the screen shares across all three situations.
 *
 * `subject` is the mail subject, and it is deliberately bland: a subject line travels through the
 * member's own mail client and whatever their mail provider indexes, so it names the topic and not
 * their standing.
 */
export const BLOCKED_SHELL = {
  back: 'Back to the front page',
  subject: 'Membership enquiry',
} as const

/** The situations this screen has wording for. The others never redirect here. */
export type BlockedReason = keyof typeof BLOCKED_COPY

/** Whether this gate reason is one the screen can speak to. */
export const isBlockedReason = (reason: GateReason): reason is BlockedReason =>
  reason in BLOCKED_COPY

/** Every string above, flattened, for the compliance tests. */
export const ALL_BLOCKED_COPY: readonly string[] = [
  ...Object.values(BLOCKED_SHELL),
  ...Object.values(BLOCKED_COPY).flatMap((notice) => [
    notice.heading,
    ...notice.body,
    ...(notice.contact ? [notice.contact] : []),
  ]),
]

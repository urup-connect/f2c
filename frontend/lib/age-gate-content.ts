import type { AgeCheckRefusal } from './age-gate'

/**
 * Every word on the age check, in one place.
 *
 * Kept apart from `landing-content.ts` on purpose. This is the one screen in the product that
 * states anything about who may join, so it is the one corpus exempt from the eligibility check
 * the landing copy must pass. Both corpora are held to the medical, retail and currency rules in
 * `copy-compliance.ts`.
 *
 * Placed for structure and pending client and legal sign-off, like the rest of the member-facing
 * wording. See design/features/age-gate-before-sign-up.md sections 6.3 and 10, risk 2.
 */

export const AGE_CHECK = {
  heading: 'Age check',
  hint: 'Membership is open to adults only, so we ask for your date of birth before you join. It is kept on your membership and used to confirm you are old enough.',
  legend: 'Date of birth',
  fields: {
    day: 'Day',
    month: 'Month',
    year: 'Year',
  },
  submit: 'Continue',
  back: 'Back to Cultivators Collective',
  /*
   * One message per refusal the check can return, so a new refusal cannot ship without wording.
   * Each says what to do about it rather than only what went wrong, and none repeats back what
   * the visitor typed.
   */
  refusals: {
    'under-age': 'You need to be 18 or older to join Cultivators Collective.',
    incomplete: 'Enter your date of birth, including the day, the month and the year.',
    'not-a-number': 'Enter the day, month and year using numbers only.',
    'not-a-real-date':
      'That is not a date on the calendar. Check the day, the month and the four-digit year.',
    'in-the-future': 'A date of birth cannot be in the future.',
    implausible: 'Check the year — that is further back than we can accept.',
  } satisfies Record<AgeCheckRefusal, string>,
} as const

/**
 * The corpus the compliance tests read.
 *
 * Assembled here rather than in the test, so a line cannot be added to the screen without the
 * checks seeing it.
 */
export const ALL_AGE_CHECK_COPY: readonly string[] = [
  AGE_CHECK.heading,
  AGE_CHECK.hint,
  AGE_CHECK.legend,
  ...Object.values(AGE_CHECK.fields),
  AGE_CHECK.submit,
  AGE_CHECK.back,
  ...Object.values(AGE_CHECK.refusals),
]

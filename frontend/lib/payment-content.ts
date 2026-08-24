/**
 * Every word on the payment screens, in one place.
 *
 * **This is the surface `copy-compliance.ts` reserved two exemptions for, and it takes one.** It is
 * exempt from `CURRENCY`, because it has to name an amount. It was also expected to need
 * `RETAIL_VOICE`, on the reasoning that a screen asking to be paid cannot avoid a shop's
 * vocabulary — and it does not: "subscription", "payment" and "Payfast" say it without a single one
 * of those words. So that exemption is declined and the corpus here is held to the rule, which
 * `payment-content.test.ts` asserts.
 *
 * It is held to the other two as well, and being a payment screen buys no relief from either.
 * `CLINICAL_CLAIM` is absolute everywhere. `ELIGIBILITY_CLAIM` matters more here than elsewhere,
 * not less: this is the screen a member reaches after giving an identity number, and it is the
 * likeliest place for somebody to add a reassuring sentence about who may join. The age check is
 * still the only surface that says any part of that.
 *
 * One wording decision runs through all of it. **Nothing here says the member is a member.** They
 * have applied and they have not paid; until a Payfast notification arrives, the account cannot
 * sign in. So the screens say what is outstanding and what happens next, and none of them
 * congratulates anybody on joining a club they have not joined yet.
 *
 * A second, quieter one: the amount is rendered from the signed Payfast field set rather than
 * written here, so the figure on screen and the figure being charged cannot disagree. There is no
 * copy string holding a price.
 *
 * Placed for structure and pending client and legal sign-off, like the rest of the member-facing
 * wording. See design/features/payments.md section 5.
 */

/** Rands and cents, from the amount Payfast is actually being sent. */
const AMOUNT = new Intl.NumberFormat('en-ZA', {
  style: 'currency',
  currency: 'ZAR',
  numberingSystem: 'latn',
})

/**
 * Format the amount out of the signed field set.
 *
 * Takes the string Django signed rather than a number, so what is displayed is derived from what
 * is being charged. An unparseable value returns `null` and the screen simply omits the figure:
 * showing "NaN" beside a payment button is worse than showing no figure at all, and the amount is
 * on Payfast's own page a moment later either way.
 */
export const formatAmount = (value: string | undefined): string | null => {
  if (!value) return null

  const amount = Number(value)
  return Number.isFinite(amount) ? AMOUNT.format(amount) : null
}

export const PAYMENT_COPY = {
  /** `/pay` — the hand-off to Payfast. */
  checkout: {
    heading: 'One step left',
    /**
     * Says where they are going and who takes the card, because a member about to be redirected to
     * a domain they did not type is entitled to know that before it happens rather than after.
     */
    body: [
      'Your details are with the club. Your membership subscription is not paid yet, so your account cannot sign in.',
      'Payfast handles the payment. Card details are typed on their page and never reach the club.',
    ],
    /**
     * Rendered as "Pay R150.00 with Payfast" when the amount could be read, and without the figure
     * otherwise. The amount is on the button rather than only in the prose because the button is
     * the thing being pressed, and what it costs should be legible at the point of pressing it.
     */
    submit: 'Continue to Payfast',
    submitWithAmount: (amount: string) => `Pay ${amount} with Payfast`,
    recurring:
      'This sets up a recurring subscription. Payfast will bill it until you cancel, and you can cancel at any time.',
  },

  /** `/pay` and `/pay/[token]` — the token names nothing payable. */
  unavailable: {
    heading: 'This payment link is no longer valid',
    body: [
      'It may have expired, or the payment may already be complete.',
      'Ask the club for a new link. If you have already paid, nothing further is needed and you can sign in once the payment clears.',
    ],
  },

  /** `/pay` — our fault, not theirs. */
  unusable: {
    heading: 'We could not start the payment',
    body: [
      'Something on our side went wrong, and nothing has been charged.',
      'Please try again shortly. If it keeps happening, contact the club and quote the reference below.',
    ],
    /** Prefixes the eight-character reference the server action logged the cause against. */
    reference: 'Reference',
  },

  /** `/signup/paid` — where Payfast returns a member who completed the payment. */
  paid: {
    heading: 'Thank you — your payment is with Payfast',
    /**
     * Careful about what it claims. The browser being redirected here means the member finished at
     * Payfast; it does **not** mean the notification that activates the account has arrived, and
     * this screen is reached by a redirect the member could replay. So it says the payment is being
     * confirmed rather than that the membership is active.
     */
    body: [
      'Payfast is confirming the payment with your bank. This is usually quick, and it can take a little longer.',
      'Your account is activated once the club receives confirmation. We will email you when it is, and you can sign in from then.',
    ],
  },

  /** `/signup/cancelled` — where Payfast returns a member who backed out. */
  cancelled: {
    heading: 'Payment cancelled',
    body: [
      'Nothing has been charged. Your details are still with the club, and your membership is not active.',
      'You can complete the payment whenever you are ready — use the link we emailed you, or ask the club for a new one.',
    ],
  },

  /** On every screen here, and it goes to the landing page rather than back into sign-up. */
  back: 'Back to the home page',
} as const

import { PAYMENT_COPY, formatAmount } from '@/lib/payment-content'
import type { Checkout } from '@/lib/checkout'

/**
 * The form that hands a member over to Payfast.
 *
 * A real `<form method="post">` with hidden inputs, which is the only thing Payfast's payment
 * engine accepts — it takes a form POST, not a URL. Three properties follow, and each is
 * deliberate.
 *
 * **It does not submit itself.** An earlier version did, on the reasoning that a member who has
 * just filled in a form should not need a second click. That was wrong here. This is the screen
 * where a recurring debit mandate is agreed to, and auto-submitting means the amount and the words
 * "Payfast will bill it until you cancel" are on screen for a few milliseconds before the browser
 * leaves. A member is entitled to read what they are agreeing to be charged, repeatedly, before
 * they agree to it — and under the Consumer Protection Act that is not merely courtesy. So the
 * button is the member's, and pressing it is the consent.
 *
 * **It is a Server Component**, which is what dropping the auto-submit bought. There is no state,
 * no effect, and no client bundle — so the screen behaves identically with JavaScript on and off,
 * rather than having a JavaScript path and a fallback that only one of them is ever exercised.
 *
 * **Every field is rendered exactly as Django built it.** No sorting, no trimming, no filtering, no
 * added field. Payfast signs the checkout over that precise set, so anything this component
 * "tidied" would make the signature fail — and Payfast answers a failed signature with a generic
 * decline that says nothing about which field was wrong. `Object.entries` in insertion order is
 * what the API sent, passed through untouched.
 *
 * The fields carry nothing about the member — no name, no address, no account id, by design (see
 * `gateway.checkout`) — which is what makes them safe to put in a page at all. The checkout *token*
 * that fetched them is not here and never crosses: it stays in the `httpOnly` cookie and in the
 * server component that read it. See `lib/checkout-api.ts`.
 */
export const PayfastForm = ({ checkout }: { checkout: Checkout }) => {
  const amount = formatAmount(checkout.fields.amount)

  return (
    <form method="post" action={checkout.url}>
      {Object.entries(checkout.fields).map(([name, value]) => (
        <input key={name} type="hidden" name={name} value={value} />
      ))}

      {/*
        * The recurring mandate, above the button rather than below it. The position is the point:
        * what a member is agreeing to has to be readable before the thing that agrees to it, not
        * after. Same reasoning as the collection notice sitting above the sign-up fields.
        */}
      <p className="font-sans text-sm leading-relaxed text-foreground">
        {PAYMENT_COPY.checkout.recurring}
      </p>

      <button
        type="submit"
        className="mt-6 w-full rounded-card bg-forest-green px-6 py-3 font-sans text-base text-white transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
      >
        {amount ? PAYMENT_COPY.checkout.submitWithAmount(amount) : PAYMENT_COPY.checkout.submit}
      </button>
    </form>
  )
}

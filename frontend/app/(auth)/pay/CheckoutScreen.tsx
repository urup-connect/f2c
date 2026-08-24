import { PayfastForm } from '@/components/Payment/PayfastForm'
import { PaymentNotice } from '@/components/Payment/PaymentNotice'
import { AuthCard } from '@/components/Ui/AuthCard'
import { fetchCheckout } from '@/lib/checkout-api'
import { newErrorReference } from '@/lib/error-reference'
import { PAYMENT_COPY } from '@/lib/payment-content'

/**
 * The payment hand-off, given a token — shared by both routes that have one.
 *
 * `/pay` gets its token from the `httpOnly` cookie the registration action set. `/pay/[token]` gets
 * it from the path, which is what an emailed link can carry. Everything after that point is
 * identical, so it is written once: two copies of a screen that takes money is two places for one
 * of them to stop failing closed.
 *
 * The three outcomes are three screens, and the split between the last two is the point.
 *
 * **Ready** renders the Payfast form. **Unavailable** — expired, unknown, already paid — is the
 * member's to solve by getting a fresh link, and says so. **Unusable** is ours: Django unreachable,
 * or an answer this application could not read. Telling a member their link had expired because our
 * own API was down would send them chasing a link that was never the problem.
 *
 * A fault of ours mints a reference, logs the cause against it server-side, and shows only the
 * reference. So the member gets eight characters to quote and the cause stays in a log line they
 * cannot read — the same treatment a failed registration gets, and for the same reason. See
 * design/features/sign-up.md section 7.
 */
export const CheckoutScreen = async ({ token }: { token: string | null }) => {
  /*
   * No token at all is answered as unavailable rather than as a fault. It means the cookie expired,
   * was never set, or the link was hand-edited — none of which is an error on our side, and all of
   * which are fixed by a fresh link.
   */
  if (!token) {
    return (
      <AuthCard>
        <PaymentNotice notice={PAYMENT_COPY.unavailable} />
      </AuthCard>
    )
  }

  const outcome = await fetchCheckout(token)

  if (outcome.status === 'unavailable') {
    return (
      <AuthCard>
        <PaymentNotice notice={PAYMENT_COPY.unavailable} />
      </AuthCard>
    )
  }

  if (outcome.status === 'unusable') {
    const reference = newErrorReference()

    /*
     * Logged here, where the member cannot read it and where the token is not in scope of the
     * message. `outcome.reason` is written by `checkout-api.ts` and names the kind of failure; it
     * carries no token and no member value, which is why it may be logged at all.
     */
    console.error(`[checkout] ${reference}: ${outcome.reason}`)

    return (
      <AuthCard>
        <PaymentNotice notice={PAYMENT_COPY.unusable} reference={reference} />
      </AuthCard>
    )
  }

  return (
    <AuthCard>
      <h1 className="font-display text-3xl tracking-display text-forest-green">
        {PAYMENT_COPY.checkout.heading}
      </h1>

      {PAYMENT_COPY.checkout.body.map((line) => (
        <p key={line} className="mt-4 font-sans text-base leading-relaxed text-foreground">
          {line}
        </p>
      ))}

      <div className="mt-8">
        <PayfastForm checkout={outcome.checkout} />
      </div>
    </AuthCard>
  )
}

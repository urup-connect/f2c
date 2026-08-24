import { CheckoutScreen } from '../CheckoutScreen'
import { readCheckoutToken } from '@/lib/checkout'

/*
 * Payment, reached from the link in an email.
 *
 * The one path where the token has to travel in a URL. An email cannot set a cookie, so there is no
 * alternative — which is why the token Django mints is 32 bytes of entropy, lives a day rather than
 * a year, and is spent the moment the subscription is paid. A link found in an inbox afterwards
 * resolves to the "no longer valid" screen rather than to a second mandate.
 *
 * This is the route the duplicate-registration fallback leads to: a submission naming an address
 * already on file is answered with the neutral confirmation screen and no token, and the link to
 * finish an outstanding payment is emailed instead. So this route is what keeps that path usable
 * without the response having disclosed anything. See design/features/payments.md section 4.
 *
 * The path segment is validated before it becomes a request. It is not a security control — Django
 * looks the token up and is the only thing that decides it is real — it stops a hand-edited URL
 * becoming an API call.
 *
 * Reading a route parameter already makes this dynamic, so there is no cache directive here.
 */
export default async function PayWithToken({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params

  return <CheckoutScreen token={readCheckoutToken(token)} />
}

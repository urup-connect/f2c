import { PaymentNotice } from '@/components/Payment/PaymentNotice'
import { AuthCard } from '@/components/Ui/AuthCard'
import { PAYMENT_COPY } from '@/lib/payment-content'

/*
 * Where Payfast returns a member who backed out of the payment.
 *
 * Reads nothing, like its sibling, and for the same reason. It says that nothing was charged and
 * that the details are still with the club, because a member who cancelled a payment after typing
 * an identity number is entitled to know where they now stand.
 *
 * It points at the emailed link rather than offering the payment again inline. The checkout cookie
 * may well still be live and `/pay` would work — but a member who has just cancelled is not asking
 * to be sent straight back, and the link is in their inbox either way.
 */
export default function Cancelled() {
  return (
    <AuthCard>
      <PaymentNotice notice={PAYMENT_COPY.cancelled} />
    </AuthCard>
  )
}

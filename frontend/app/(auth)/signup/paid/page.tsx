import { PaymentNotice } from '@/components/Payment/PaymentNotice'
import { AuthCard } from '@/components/Ui/AuthCard'
import { PAYMENT_COPY } from '@/lib/payment-content'

/*
 * Where Payfast returns a member who completed the payment.
 *
 * **It reads nothing and decides nothing.** This is a browser redirect from a third party: the
 * member controls it, can replay it, can bookmark it, and can arrive here having paid nothing at
 * all. So it carries no query parameters that mean anything, looks nothing up, and above all does
 * not tell the member their membership is active.
 *
 * What activates an account is the server-to-server notification Payfast sends to
 * `POST /api/payments/payfast/notify`. This screen says the payment is being confirmed, which is
 * the only thing being here actually proves.
 */
export default function Paid() {
  return (
    <AuthCard>
      <PaymentNotice notice={PAYMENT_COPY.paid} />
    </AuthCard>
  )
}

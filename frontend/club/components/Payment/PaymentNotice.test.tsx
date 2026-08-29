import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { PaymentNotice } from './PaymentNotice'
import { PAYMENT_COPY } from '@/lib/payment-content'

/* design/features/payments.md section 5. */

const SCREENS = [
  ['an expired link', PAYMENT_COPY.unavailable],
  ['a fault of ours', PAYMENT_COPY.unusable],
  ['a completed payment', PAYMENT_COPY.paid],
  ['a cancelled payment', PAYMENT_COPY.cancelled],
] as const

describe('the payment notice', () => {
  test.each(SCREENS)('renders the heading and body for %s', (_name, notice) => {
    render(<PaymentNotice notice={notice} />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(notice.heading)

    for (const line of notice.body) {
      expect(screen.getByText(line)).toBeInTheDocument()
    }
  })

  test('the heading is the only level-one heading, so it is the document heading', () => {
    /*
     * The reason this needs no focus script: the heading is the first thing in the document, and
     * the screen is reached by a fresh page render rather than by replacing part of one. Same
     * reasoning as `SubmissionOutcome`.
     */
    render(<PaymentNotice notice={PAYMENT_COPY.paid} />)

    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
  })

  test('offers a way back, to the landing page', () => {
    render(<PaymentNotice notice={PAYMENT_COPY.cancelled} />)

    // Never back into sign-up: the details are already with the club.
    expect(screen.getByRole('link', { name: PAYMENT_COPY.back })).toHaveAttribute('href', '/')
  })

  test('shows a reference when there is a fault of ours to quote', () => {
    render(<PaymentNotice notice={PAYMENT_COPY.unusable} reference="a1b2c3d4" />)

    expect(screen.getByText('a1b2c3d4')).toBeInTheDocument()
  })

  test('shows no reference label when there is no reference', () => {
    /*
     * A bare "Reference:" with nothing after it asks a member to quote something that does not
     * exist, which is worse than saying nothing.
     */
    render(<PaymentNotice notice={PAYMENT_COPY.unavailable} />)

    expect(screen.queryByText(new RegExp(PAYMENT_COPY.unusable.reference))).toBeNull()
  })

  test('never says the membership is active', () => {
    // Not even on the screen a member reaches after paying: what activates an account is the
    // notification Payfast sends server-to-server, and this screen has not seen it.
    render(<PaymentNotice notice={PAYMENT_COPY.paid} />)

    expect(document.body.textContent?.toLowerCase()).not.toMatch(
      /membership is active|you are now a member/,
    )
  })
})

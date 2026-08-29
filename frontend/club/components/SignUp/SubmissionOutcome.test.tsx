import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { SubmissionOutcome } from './SubmissionOutcome'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/* design/features/member-details-at-sign-up.md criterion 37. */

describe('SubmissionOutcome', () => {
  test('heads the page, so it is the first thing read after the submission', () => {
    render(<SubmissionOutcome />)

    expect(
      screen.getByRole('heading', { level: 1, name: MEMBER_DETAILS_COPY.outcome.heading }),
    ).toBeInTheDocument()
  })

  test('says the membership has been set up', () => {
    render(<SubmissionOutcome />)

    expect(screen.getByText(/membership has been set up/)).toBeInTheDocument()
  })

  test('says plainly that the membership is not active yet', () => {
    /*
     * Criterion 37, reversed by the data layer landing. The point of the screen used to be that
     * nothing was kept; now it is that something was, and that it does not yet let them in. A
     * member who is not told will try to sign in and conclude the club lost their details.
     */
    render(<SubmissionOutcome />)

    expect(screen.getByText(/not active yet/)).toBeInTheDocument()
  })

  test('says what completes it, and how they will hear', () => {
    render(<SubmissionOutcome />)

    expect(screen.getByText(/payment/)).toBeInTheDocument()
    expect(screen.getByText(/email you/)).toBeInTheDocument()
  })

  test('renders every line of the outcome', () => {
    render(<SubmissionOutcome />)

    for (const line of MEMBER_DETAILS_COPY.outcome.body) {
      expect(screen.getByText(line)).toBeInTheDocument()
    }
  })

  test('offers a way back to the club', () => {
    render(<SubmissionOutcome />)

    expect(screen.getByRole('link', { name: MEMBER_DETAILS_COPY.back })).toHaveAttribute(
      'href',
      '/',
    )
  })

  test('offers no form, because there is nothing left to submit', () => {
    const { container } = render(<SubmissionOutcome />)

    expect(container.querySelector('form')).toBeNull()
  })
})

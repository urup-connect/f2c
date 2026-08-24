import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { DocumentsUnavailable } from './DocumentsUnavailable'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/*
 * design/features/sign-up.md sections 5, 6 and 7.
 *
 * One screen, two causes, and — since a submission can now fail on our side — one optional
 * reference. What is asserted here is that the reference is all it is: a handle on a log line, with
 * no description of the fault beside it and nothing about the person quoting it.
 */

describe('the screen shown instead of the form', () => {
  test('says joining is unavailable and that the details are not at fault', () => {
    render(<DocumentsUnavailable />)

    expect(
      screen.getByRole('heading', { name: MEMBER_DETAILS_COPY.unavailable.heading }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Nothing is wrong with your details/)).toBeInTheDocument()
  })

  test('offers no reference when nothing was attempted on the member’s behalf', () => {
    /*
     * The club documents could not be read on the way in. Nothing was tried, there is no log line
     * for this visitor, and a reference with nothing behind it is worse than none.
     */
    render(<DocumentsUnavailable />)

    expect(screen.queryByText(/reference/i)).not.toBeInTheDocument()
  })

  test('quotes the reference when a submission could not be written', () => {
    render(<DocumentsUnavailable reference="3f9a1c04" />)

    expect(screen.getByText(/3f9a1c04/)).toBeInTheDocument()
  })

  test('says what the reference is for, and that it says nothing about the member', () => {
    /*
     * Somebody who has just typed an identity number into a form and is then asked to send us a
     * code deserves an answer to the obvious question, on the screen, unprompted.
     */
    render(<DocumentsUnavailable reference="3f9a1c04" />)

    expect(screen.getByText(/says nothing about you/i)).toBeInTheDocument()
  })

  test('does not say what failed', () => {
    render(<DocumentsUnavailable reference="3f9a1c04" />)

    const page = document.body.textContent ?? ''

    // Which fault it was is a log line, not a screen. See app/(auth)/signup/actions.ts.
    for (const cause of ['unreachable', 'API', 'Django', '500', '503']) {
      expect(page).not.toContain(cause)
    }
  })

  test('offers a way back that is not the age check', () => {
    render(<DocumentsUnavailable reference="3f9a1c04" />)

    expect(screen.getByRole('link', { name: MEMBER_DETAILS_COPY.back })).toHaveAttribute(
      'href',
      '/',
    )
  })
})

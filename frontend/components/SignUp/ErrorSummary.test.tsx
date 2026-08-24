import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { ErrorSummary } from './ErrorSummary'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'
import type { MemberDetailsFieldRefusal } from '@/lib/member-details'

/* design/features/member-details-at-sign-up.md criterion 38, and section 8. */

const DATE_OF_BIRTH = '15 March 1990'

const REFUSALS: readonly MemberDetailsFieldRefusal[] = [
  { field: 'firstName', reason: 'name-missing' },
  { field: 'idNumber', reason: 'id-checksum' },
]

describe('ErrorSummary', () => {
  test('renders nothing when there is nothing wrong', () => {
    const { container } = render(<ErrorSummary refusals={[]} dateOfBirth={DATE_OF_BIRTH} />)

    expect(container).toBeEmptyDOMElement()
  })

  test('announces itself as an alert', () => {
    render(<ErrorSummary refusals={REFUSALS} dateOfBirth={DATE_OF_BIRTH} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  test('heads the list with wording from the copy module', () => {
    render(<ErrorSummary refusals={REFUSALS} dateOfBirth={DATE_OF_BIRTH} />)

    expect(
      screen.getByRole('heading', { name: MEMBER_DETAILS_COPY.errorSummaryHeading }),
    ).toBeInTheDocument()
  })

  test('lists every refusal', () => {
    // Criterion 38: every failing field at once, not one at a time.
    render(<ErrorSummary refusals={REFUSALS} dateOfBirth={DATE_OF_BIRTH} />)

    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  test('links each refusal to the field it belongs to', () => {
    render(<ErrorSummary refusals={REFUSALS} dateOfBirth={DATE_OF_BIRTH} />)

    const links = screen.getAllByRole('link')

    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '#member-firstName',
      '#member-idNumber',
    ])
  })

  test('names the field and the problem in each entry', () => {
    render(<ErrorSummary refusals={REFUSALS} dateOfBirth={DATE_OF_BIRTH} />)

    expect(screen.getByRole('link', { name: /First name/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /does not add up/ })).toBeInTheDocument()
  })

  test('takes focus, so a refusal is reached rather than waited for', () => {
    render(<ErrorSummary refusals={REFUSALS} dateOfBirth={DATE_OF_BIRTH} />)

    expect(screen.getByRole('alert')).toHaveFocus()
  })

  test('renders the date-of-birth message with the date on file', () => {
    render(
      <ErrorSummary
        refusals={[{ field: 'idNumber', reason: 'id-date-mismatch' }]}
        dateOfBirth={DATE_OF_BIRTH}
      />,
    )

    expect(screen.getByRole('link', { name: new RegExp(DATE_OF_BIRTH) })).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { CollectionNotice } from './CollectionNotice'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'

/* design/features/member-details-at-sign-up.md criterion 48, and section 9. */

describe('CollectionNotice', () => {
  test('renders every paragraph of the notice', () => {
    render(<CollectionNotice />)

    for (const paragraph of MEMBER_DETAILS_COPY.collectionNotice) {
      expect(screen.getByText(paragraph)).toBeInTheDocument()
    }
  })

  test('names who is collecting the details', () => {
    render(<CollectionNotice />)

    expect(screen.getByText(/Cultivators Collective is asking/)).toBeInTheDocument()
  })

  test('says the details are kept, and that signing in waits on payment', () => {
    /*
     * It said nothing was kept until the details were stored. The consequence belongs in the same
     * paragraph: a member told their details are kept and not told they cannot sign in yet will
     * try to, and conclude the club lost them.
     */
    render(<CollectionNotice />)

    expect(screen.getByText(/These details are kept/)).toBeInTheDocument()
    expect(screen.getByText(/cannot sign in, until payment/)).toBeInTheDocument()
  })

  test('says that giving the details is voluntary', () => {
    render(<CollectionNotice />)

    expect(screen.getByText(/voluntary/)).toBeInTheDocument()
  })
})

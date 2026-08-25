import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { MembershipSummary } from './MembershipSummary'
import { MEMBERSHIP_CARD } from '@/lib/club-content'

describe('MembershipSummary', () => {
  test('says what the account is', () => {
    render(<MembershipSummary role="cultivator" status="active" />)

    expect(screen.getByText('Cultivator')).toBeInTheDocument()
  })

  test('says how it stands, in a sentence as well as a word', () => {
    render(<MembershipSummary role="member" status="active" />)

    expect(screen.getByText(MEMBERSHIP_CARD.statusLabels.active)).toBeInTheDocument()
    expect(screen.getByText(MEMBERSHIP_CARD.statusNotes.active)).toBeInTheDocument()
  })

  test('keeps the two facts apart', () => {
    // Role says what the account is. Status says whether it may sign in. An
    // administrator is as suspendable as a member.
    render(<MembershipSummary role="admin" status="suspended" />)

    expect(screen.getByText('Administrator')).toBeInTheDocument()
    expect(screen.getByText(MEMBERSHIP_CARD.statusLabels.suspended)).toBeInTheDocument()
  })

  test('labels both', () => {
    render(<MembershipSummary role="member" status="active" />)

    expect(screen.getByText(MEMBERSHIP_CARD.roleLabel)).toBeInTheDocument()
    expect(screen.getByText(MEMBERSHIP_CARD.statusLabel)).toBeInTheDocument()
  })

  test('shows something rather than nothing for a role with no home', () => {
    // A sharing member cannot hold a session. An impossible state should look odd,
    // not look like a page that failed to draw.
    render(<MembershipSummary role="sharing_member" status="sharing" />)

    expect(screen.getByText('sharing_member')).toBeInTheDocument()
  })
})

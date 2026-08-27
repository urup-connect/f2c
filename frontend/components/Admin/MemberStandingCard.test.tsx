import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MEMBER_STANDING } from '@/lib/member-register-content'
import type { Member } from '@/lib/member-register'
import { erasedMember, member, sharingMember } from '@/test-support/members'
import { MemberStandingCard } from './MemberStandingCard'

/*
 * Whether an account may sign in, and the two acts that change the answer.
 *
 * The asymmetry between them is the thing worth guarding: suspension confirms
 * because an accidental press locks a person out of the club with no idea why,
 * and reinstatement does not, because it restores what they had.
 */

const { reinstateMember, suspendMember } = vi.hoisted(() => ({
  reinstateMember: vi.fn(),
  suspendMember: vi.fn(),
}))

vi.mock('@/lib/member-register-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/member-register-api')>()),
  reinstateMember,
  suspendMember,
}))

const onChanged = vi.fn()

const setup = (record: Member = member(), viewerId = 'admin-1') => {
  render(
    <MemberStandingCard member={record} viewerId={viewerId} onChanged={onChanged} />,
  )
}

beforeEach(() => {
  suspendMember.mockReset()
  reinstateMember.mockReset()
  onChanged.mockReset()
  suspendMember.mockResolvedValue({
    status: 'saved',
    record: member({ status: 'suspended', status_label: 'Suspended' }),
  })
  reinstateMember.mockResolvedValue({ status: 'saved', record: member() })
})

describe('before anything is pressed', () => {
  test('reports where the account stands', () => {
    setup(member({ status_label: 'Active' }))

    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  test('offers suspension for an active account, and not reinstatement', () => {
    setup()

    expect(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.reinstateLabel }),
    ).not.toBeInTheDocument()
  })

  test('offers reinstatement for a suspended account, and not suspension', () => {
    setup(member({ status: 'suspended', status_label: 'Suspended' }))

    expect(
      screen.getByRole('button', { name: MEMBER_STANDING.reinstateLabel }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).not.toBeInTheDocument()
  })

  test('offers neither on an account that is neither active nor suspended', () => {
    // Nothing records where an account sat before a suspension, so reinstatement
    // cannot restore it — and Pending payment is not a block the club placed, it
    // is an unpaid subscription.
    setup(member({ status: 'pending_payment', status_label: 'Pending payment' }))

    expect(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.reinstateLabel }),
    ).not.toBeInTheDocument()
  })
})

describe('the viewer’s own account', () => {
  test('is not offered suspension, and is told why', () => {
    /*
     * Suspension signs the caller out on the way and they cannot sign back in to
     * undo it. The API refuses it too; this is what stops the button being
     * offered at all, so nobody discovers the rule by pressing it. The sentence
     * matters as much as the absence — a control that is simply missing reads as
     * a screen that failed to draw.
     */
    setup(member({ id: 'admin-1' }), 'admin-1')

    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).not.toBeInTheDocument()
    expect(screen.getByText(MEMBER_STANDING.cannotSuspendSelf)).toBeInTheDocument()
  })
})

describe('a record that may not be written to', () => {
  test('offers no action on an erased account', () => {
    setup(erasedMember({ status: 'suspended', status_label: 'Suspended' }))

    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.reinstateLabel }),
    ).not.toBeInTheDocument()
  })

  test('offers no action on a sharing member', () => {
    // They hold stock and never sign in, and C14 has not decided whether an
    // administrator may touch one at all.
    setup(sharingMember())

    expect(
      screen.queryByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).not.toBeInTheDocument()
  })
})

describe('suspending', () => {
  test('confirms first, and does nothing until it is confirmed', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )

    expect(screen.getByText(MEMBER_STANDING.confirmSuspendHeading)).toBeInTheDocument()
    expect(screen.getByText(MEMBER_STANDING.confirmSuspendBody)).toBeInTheDocument()
    expect(suspendMember).not.toHaveBeenCalled()
  })

  test('offers a way out of the confirmation that is not the action', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.confirmCancel }),
    )

    expect(suspendMember).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    ).toBeInTheDocument()
  })

  test('acts once confirmed, and hands the new record up', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.confirmSuspendAction }),
    )

    expect(suspendMember).toHaveBeenCalledWith('member-1')
    expect(onChanged).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'suspended' }),
    )
  })

  test('announces what happened, in different words from the standing itself', async () => {
    // Both are on screen afterwards: the state, and the event. One sentence
    // doing both jobs reads as the screen having drawn something twice.
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.confirmSuspendAction }),
    )

    expect(await screen.findByRole('status')).toHaveTextContent(
      MEMBER_STANDING.suspendedNow,
    )
  })
})

describe('reinstating', () => {
  test('acts on one press, with no confirmation', async () => {
    // Not symmetrical with suspension on purpose: lifting a block restores what
    // the member had, so a confirmation step would be ceremony around an act
    // with no victim.
    setup(member({ status: 'suspended', status_label: 'Suspended' }))

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.reinstateLabel }),
    )

    expect(reinstateMember).toHaveBeenCalledWith('member-1')
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: 'active' }))
  })
})

describe('when the act is refused', () => {
  test('reports the refusal’s own sentence rather than a generic one', async () => {
    // "You cannot suspend your own account" is more use than "that could not be
    // done just now", and the API is the only thing that knows which it is.
    suspendMember.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'A sharing member cannot be suspended.', fields: {} },
    })
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.confirmSuspendAction }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A sharing member cannot be suspended.',
    )
    expect(onChanged).not.toHaveBeenCalled()
  })

  test('falls back to its own sentence when the call never reached a decision', async () => {
    suspendMember.mockResolvedValue({ status: 'failed', reason: 'down' })
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.confirmSuspendAction }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(MEMBER_STANDING.failed)
  })
})

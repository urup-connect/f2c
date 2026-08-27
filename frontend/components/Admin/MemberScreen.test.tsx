import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import {
  MEMBER_MEMBERSHIP,
  MEMBER_RECORD,
  MEMBER_STANDING,
} from '@/lib/member-register-content'
import type { Member } from '@/lib/member-register'
import { erasedMember, member, sharingMember } from '@/test-support/members'
import { MemberScreen } from './MemberScreen'

/*
 * One member's record, and the four cards that make it up.
 *
 * The cards are tested on their own beside this file. What is asserted here is
 * what only the screen can do: hold the record, hand it to each card, and redraw
 * the others when one of them changes it.
 */

const { reinstateMember, saveMember, suspendMember } = vi.hoisted(() => ({
  reinstateMember: vi.fn(),
  saveMember: vi.fn(),
  suspendMember: vi.fn(),
}))

vi.mock('@/lib/member-register-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/member-register-api')>()),
  reinstateMember,
  saveMember,
  suspendMember,
}))

const setup = (record: Member = member(), viewerId = 'admin-1') => {
  render(
    <MemberScreen initial={record} viewerId={viewerId} registerHref="/admin/members" />,
  )
}

beforeEach(() => {
  saveMember.mockReset()
  suspendMember.mockReset()
  reinstateMember.mockReset()
  saveMember.mockResolvedValue({ status: 'saved', record: member() })
  suspendMember.mockResolvedValue({
    status: 'saved',
    record: member({ status: 'suspended', status_label: 'Suspended' }),
  })
})

describe('the heading', () => {
  test('names the member and offers a way back', () => {
    setup(member({ display_name: 'Thabo' }))

    expect(screen.getByRole('heading', { level: 1, name: 'Thabo' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: MEMBER_RECORD.backLabel })).toHaveAttribute(
      'href',
      '/admin/members',
    )
  })
})

describe('the facts', () => {
  test('reports a member who has never signed in as never, not as absent', () => {
    // "Not on file" would be wrong: the club holds the fact, and the fact is
    // that they never have.
    setup(member({ last_login: null }))

    expect(screen.getByText(MEMBER_RECORD.neverSeen)).toBeInTheDocument()
  })

  test('says a date of birth has not been checked against a document', () => {
    /*
     * `date_of_birth_verified_at` is left null by registration on purpose: a
     * number that passes its check digit is not a typo, and nobody has seen an
     * ID. This is the field the club would rely on later, so the screen has to
     * say which of the two it is.
     */
    setup(member({ date_of_birth_verified_at: null }))

    expect(screen.getByText(MEMBER_RECORD.birthUnverified)).toBeInTheDocument()
  })

  test('says when it has been checked', () => {
    setup(member({ date_of_birth_verified_at: '2026-02-01T00:00:00Z' }))

    expect(screen.getByText(MEMBER_RECORD.birthVerified)).toBeInTheDocument()
  })

  test('names the cultivator who registered a sharing member', () => {
    setup(sharingMember())

    expect(screen.getByText(MEMBER_RECORD.registeredByFact)).toBeInTheDocument()
    expect(screen.getByText('Kloof')).toBeInTheDocument()
  })

  test('leaves that line out for everybody else', () => {
    setup(member({ registered_by: null }))

    expect(screen.queryByText(MEMBER_RECORD.registeredByFact)).not.toBeInTheDocument()
  })
})

describe('the subscription card', () => {
  test('shows the arrangement in force', () => {
    setup()

    expect(screen.getByText(MEMBER_MEMBERSHIP.paidUntilLabel)).toBeInTheDocument()
    expect(screen.getByText('2026-12-31')).toBeInTheDocument()
  })

  test('says there is none rather than drawing empty rows', () => {
    setup(
      member({ membership: { status: null, status_label: null, paid_until: null } }),
    )

    expect(screen.getByText(MEMBER_MEMBERSHIP.none)).toBeInTheDocument()
  })
})

describe('a record that may not be written to', () => {
  test('renders a banner instead of the form, for an erased account', () => {
    /*
     * Absent rather than disabled. A form full of inert inputs invites somebody
     * to work out how to enable them, and reads as a bug rather than as a rule.
     */
    setup(erasedMember())

    expect(screen.getByText(MEMBER_RECORD.readOnlyErased)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: MEMBER_RECORD.save }),
    ).not.toBeInTheDocument()
  })

  test('gives a sharing member its own reason, not the erasure one', () => {
    // Read-only for entirely different reasons, and one message for both would
    // explain neither.
    setup(sharingMember())

    expect(screen.getByText(MEMBER_RECORD.readOnlySharing)).toBeInTheDocument()
    expect(screen.queryByText(MEMBER_RECORD.readOnlyErased)).not.toBeInTheDocument()
  })

  test('still shows the facts and the document', () => {
    // Readable is not the same as writable. The register lists these accounts,
    // and a record screen that refused to draw one would send an administrator
    // back to the Django admin to read a row they can already see.
    setup(erasedMember())

    expect(screen.getByText(MEMBER_RECORD.factsHeading)).toBeInTheDocument()
  })
})

describe('a write from one card', () => {
  test('redraws the standing shown by another', async () => {
    // The screen owns the record and every write answers with the whole of it,
    // so a suspension moves the heading, the facts and the access card together
    // without a re-fetch.
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.suspendLabel }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_STANDING.confirmSuspendAction }),
    )

    expect(await screen.findByText(MEMBER_STANDING.suspended)).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: MEMBER_STANDING.reinstateLabel }),
    ).toBeInTheDocument()
  })

  test('does not remount the form on the form’s own save', async () => {
    /*
     * The form reconciles its own fields after a save. Remounting it there would
     * throw away the focus and the scroll position of somebody who had just
     * pressed the button — which is why `externalWrites` counts writes from the
     * *other* cards and nothing else.
     */
    saveMember.mockResolvedValue({ status: 'saved', record: member({ last_name: 'Ncube' }) })
    setup()

    const surname = screen.getByRole('textbox', {
      name: new RegExp(MEMBER_RECORD.lastNameLabel),
    })
    await userEvent.clear(surname)
    await userEvent.type(surname, 'Ncube')
    await userEvent.tab()
    await userEvent.click(screen.getByRole('button', { name: MEMBER_RECORD.save }))

    // The saved confirmation survives, which it would not through a remount.
    expect(await screen.findByText(MEMBER_RECORD.saved)).toBeInTheDocument()
  })
})

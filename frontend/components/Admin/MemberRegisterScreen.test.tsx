import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MEMBER_REGISTER } from '@/lib/member-register-content'
import type { MemberRow } from '@/lib/member-register'
import { memberRow } from '@/test-support/members'
import { MemberRegisterScreen } from './MemberRegisterScreen'

/*
 * The register: every account the club holds, narrowed by four filters.
 *
 * What is worth guarding here is mostly what the screen does *not* draw. A
 * register is the one administrative list that holds people, and three of the
 * tests below exist because the obvious implementation leaks something: an
 * identity number into a table, an erased account out of a count, or a failed
 * read reported as an empty club.
 */

const { listMembers } = vi.hoisted(() => ({ listMembers: vi.fn() }))

vi.mock('@/lib/member-register-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/member-register-api')>()),
  listMembers,
}))

const setup = (initial: readonly MemberRow[] = [memberRow()], unavailable = false) => {
  render(
    <MemberRegisterScreen
      initial={initial}
      unavailable={unavailable}
      memberHref={(id) => `/admin/members/${id}`}
    />,
  )
}

beforeEach(() => {
  listMembers.mockReset()
  listMembers.mockResolvedValue([])
})

describe('the first paint', () => {
  test('draws what the server rendered without fetching', () => {
    // The whole reason the page reads on the server: a register that arrives
    // empty and fills in a moment later is one an administrator will have typed
    // a search into before the rows land underneath them.
    setup([memberRow({ display_name: 'Thabo' })])

    expect(screen.getByRole('link', { name: 'Thabo' })).toHaveAttribute(
      'href',
      '/admin/members/member-1',
    )
    expect(listMembers).not.toHaveBeenCalled()
  })

  test('labels every column', () => {
    setup()

    for (const label of [
      MEMBER_REGISTER.columnMember,
      MEMBER_REGISTER.columnRole,
      MEMBER_REGISTER.columnStatus,
      MEMBER_REGISTER.columnMembership,
      MEMBER_REGISTER.columnContact,
      MEMBER_REGISTER.columnJoined,
    ]) {
      expect(screen.getByRole('columnheader', { name: label })).toBeInTheDocument()
    }
  })

  test('shows the standing and the subscription as two separate facts', () => {
    // They disagree often — a suspended account can be paid up, and an active
    // one can have lapsed — so one column reporting both would be wrong half the
    // time.
    setup([
      memberRow({
        status_label: 'Suspended',
        status: 'suspended',
        membership: { status: 'active', status_label: 'Active', paid_until: '2026-12-31' },
      }),
    ])

    expect(screen.getByRole('cell', { name: /Suspended/ })).toBeInTheDocument()
    expect(screen.getByText(/2026-12-31/)).toBeInTheDocument()
  })

  test('says when an account cannot sign in', () => {
    setup([memberRow({ status: 'pending_payment', status_label: 'Pending payment' })])

    expect(screen.getByText(MEMBER_REGISTER.cannotSignIn)).toBeInTheDocument()
  })

  test('says nothing about signing in for an active account', () => {
    setup()

    expect(screen.queryByText(MEMBER_REGISTER.cannotSignIn)).not.toBeInTheDocument()
  })

  test('says a member has no subscription rather than leaving the cell blank', () => {
    setup([
      memberRow({ membership: { status: null, status_label: null, paid_until: null } }),
    ])

    expect(screen.getByText(MEMBER_REGISTER.noSubscription)).toBeInTheDocument()
  })
})

describe('what the register never puts in a table', () => {
  test('draws no identity number, masked or otherwise', () => {
    /*
     * `MemberRowOut` does not send one, and the column that would show it is
     * absent rather than blank. `id_number_masked` decrypts, so a masked column
     * on a list of six hundred members is six hundred decryptions per page load
     * — and the only fact a register needs is whether one is on file.
     */
    setup([memberRow({ has_id_number: true })])

    expect(screen.queryByText(/\*{4,}/)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('columnheader', { name: /identity/i }),
    ).not.toBeInTheDocument()
  })
})

describe('an erased account', () => {
  test('is listed, and marked', () => {
    // `soft_delete` keeps the row because the club's own history points at it.
    // Hiding it would make this register disagree with every other count of how
    // many accounts exist.
    setup([memberRow({ erased: true, email: null, display_name: 'Erased member' })])

    expect(screen.getByRole('link', { name: 'Erased member' })).toBeInTheDocument()
    expect(screen.getByText(MEMBER_REGISTER.erasedBadge)).toBeInTheDocument()
  })

  test('says its contact details are gone rather than showing an empty cell', () => {
    setup([memberRow({ erased: true, email: null, mobile: '' })])

    expect(screen.getByText(MEMBER_REGISTER.noContact)).toBeInTheDocument()
  })
})

describe('the filters', () => {
  test('re-query the API rather than filtering the rows in the browser', async () => {
    /*
     * The search reaches the identity number's blind index, which the browser
     * could not perform even if it wanted to — the number is encrypted and never
     * leaves the server. A browser-side filter would silently be a different
     * search from the one the label promises.
     */
    listMembers.mockResolvedValue([memberRow({ display_name: 'Zanele' })])
    setup()

    await userEvent.type(screen.getByRole('searchbox'), 'Zan')

    await waitFor(() => {
      expect(listMembers).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'Zan' }),
      )
    })
  })

  test('combine', async () => {
    setup()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: MEMBER_REGISTER.statusLabel }),
      'suspended',
    )
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: MEMBER_REGISTER.roleLabel }),
      'member',
    )

    await waitFor(() => {
      expect(listMembers).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: 'suspended', role: 'member' }),
      )
    })
  })

  test('offer the recent sign-ups view as a window, not a separate screen', async () => {
    // The register is newest-first regardless, so a window on it already is the
    // list of who joined lately in the order somebody wants to read it.
    setup()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: MEMBER_REGISTER.joinedLabel }),
      '30',
    )

    await waitFor(() => {
      expect(listMembers).toHaveBeenLastCalledWith(
        expect.objectContaining({ joined_within: '30' }),
      )
    })
  })

  test('are clearable, and the control appears only once something is set', async () => {
    setup()

    expect(
      screen.queryByRole('button', { name: MEMBER_REGISTER.clearLabel }),
    ).not.toBeInTheDocument()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: MEMBER_REGISTER.roleLabel }),
      'cultivator',
    )
    await userEvent.click(screen.getByRole('button', { name: MEMBER_REGISTER.clearLabel }))

    await waitFor(() => {
      expect(listMembers).toHaveBeenLastCalledWith({
        status: '',
        role: '',
        search: '',
        joined_within: '',
      })
    })
  })
})

describe('emptiness', () => {
  test('an empty register and an empty filter say different things', async () => {
    // "No accounts" beside a filter somebody set is a sentence that sends an
    // administrator looking for data that is there.
    setup([])

    expect(screen.getByText(MEMBER_REGISTER.empty)).toBeInTheDocument()

    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: MEMBER_REGISTER.roleLabel }),
      'cultivator',
    )

    expect(await screen.findByText(MEMBER_REGISTER.emptyFiltered)).toBeInTheDocument()
  })
})

describe('a failed read', () => {
  test('is reported by the server render, and is not an empty club', () => {
    setup([], true)

    expect(screen.getByRole('alert')).toHaveTextContent(MEMBER_REGISTER.loadFailed)
  })

  test('keeps the rows already on screen', async () => {
    // They are stale rather than wrong, and a table replaced by an error message
    // loses the administrator's place in a list they were reading.
    listMembers.mockRejectedValue(new Error('down'))
    setup([memberRow({ display_name: 'Thabo' })])

    await userEvent.type(screen.getByRole('searchbox'), 'x')

    expect(await screen.findByRole('alert')).toHaveTextContent(MEMBER_REGISTER.loadFailed)
    expect(screen.getByRole('link', { name: 'Thabo' })).toBeInTheDocument()
  })
})

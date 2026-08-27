import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MEMBER_IDENTITY } from '@/lib/member-register-content'
import type { Member } from '@/lib/member-register'
import { disclosure, member } from '@/test-support/members'
import { MemberIdentityCard } from './MemberIdentityCard'

/*
 * The identity document: masked by default, and a recorded full read.
 *
 * `design/backend.md` section 10 makes the number write-only in the Django
 * admin. This card is the one exception to that across the whole product, so
 * most of what is asserted here is the shape of the exception: the reason is
 * asked for before the number is fetched, the number never appears without one,
 * and the read leaves a record on screen.
 */

const { discloseIdentityNumber } = vi.hoisted(() => ({
  discloseIdentityNumber: vi.fn(),
}))

vi.mock('@/lib/member-register-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/member-register-api')>()),
  discloseIdentityNumber,
}))

const setup = (record: Member = member()) => {
  render(<MemberIdentityCard member={record} />)
}

const REASON = 'Verifying against the document on file.'

beforeEach(() => {
  discloseIdentityNumber.mockReset()
  discloseIdentityNumber.mockResolvedValue({
    status: 'saved',
    record: { id_number: '9003155009088', disclosure: disclosure() },
  })
})

describe('by default', () => {
  test('shows the masked form and no number', () => {
    setup(member({ id_number_masked: '*********1234' }))

    expect(screen.getByText('*********1234')).toBeInTheDocument()
    expect(screen.queryByText('9003155009088')).not.toBeInTheDocument()
  })

  test('asks for no reason until the read is requested', () => {
    setup()

    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    ).toBeInTheDocument()
  })
})

describe('a member with no document on file', () => {
  test('says so, and offers no read', () => {
    setup(member({ has_id_number: false, id_number_masked: '' }))

    expect(screen.getByText(MEMBER_IDENTITY.none)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    ).not.toBeInTheDocument()
  })
})

describe('a document that will not decrypt', () => {
  test('is surfaced as a problem, not reported as absent', () => {
    /*
     * `UNREADABLE` is a key or an integrity problem somebody has to look at.
     * Presenting it as "no document on file" would be unrecoverable data
     * reported as missing — the one outcome worse than the problem itself,
     * because nobody would know to look.
     */
    setup(member({ has_id_number: true, id_number_masked: 'UNREADABLE' }))

    expect(screen.getByRole('alert')).toHaveTextContent(MEMBER_IDENTITY.unreadable)
    expect(screen.queryByText(MEMBER_IDENTITY.none)).not.toBeInTheDocument()
  })

  test('offers no read, because there is nothing to read', () => {
    setup(member({ has_id_number: true, id_number_masked: 'UNREADABLE' }))

    expect(
      screen.queryByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    ).not.toBeInTheDocument()
  })
})

describe('reading the number', () => {
  test('asks for a reason before it fetches anything', async () => {
    /*
     * The order is the whole design. `POST /identity-number` writes the
     * disclosure row before it decrypts, so a screen that fetched first and
     * asked afterwards would be a screen with a way to read the number and
     * abandon the form.
     */
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )

    expect(screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel })).toBeInTheDocument()
    expect(discloseIdentityNumber).not.toHaveBeenCalled()
  })

  test('will not act on a reason nobody could review', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      'ok',
    )

    expect(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    ).toBeDisabled()
    // The button being inert explains nothing on its own, so the rule is also
    // said in words.
    expect(screen.getByText(MEMBER_IDENTITY.reasonTooShort)).toBeInTheDocument()
  })

  test('sends the reason with the request', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    )

    expect(discloseIdentityNumber).toHaveBeenCalledWith('member-1', REASON)
  })

  test('shows the number, and says the read was recorded', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    )

    expect(await screen.findByText('9003155009088')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(MEMBER_IDENTITY.revealed)
  })

  test('puts the read straight into the history, newest first', async () => {
    // The endpoint answers with the row it just wrote, so the ledger on screen
    // is correct without a second round trip.
    setup(member({ disclosures: [disclosure({ id: 'older', reason: 'An older read.' })] }))

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    )

    await screen.findByText('9003155009088')
    const entries = screen.getAllByRole('listitem')
    expect(entries).toHaveLength(2)
    expect(entries[0]).toHaveTextContent(REASON)
  })

  test('can be hidden again, back to the masked form', async () => {
    setup(member({ id_number_masked: '*********1234' }))

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    )
    await screen.findByText('9003155009088')

    await userEvent.click(screen.getByRole('button', { name: MEMBER_IDENTITY.hideLabel }))

    expect(screen.queryByText('9003155009088')).not.toBeInTheDocument()
    expect(screen.getByText('*********1234')).toBeInTheDocument()
  })

  test('can be abandoned without reading anything', async () => {
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.cancelReveal }),
    )

    expect(discloseIdentityNumber).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    ).toBeInTheDocument()
  })
})

describe('when the read is refused', () => {
  test('shows no number and reports the refusal', async () => {
    discloseIdentityNumber.mockResolvedValue({
      status: 'refused',
      refusal: { detail: 'There is no identity number on file.', fields: {} },
    })
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'There is no identity number on file.',
    )
    expect(screen.queryByText('9003155009088')).not.toBeInTheDocument()
  })

  test('says nothing was recorded when the call never reached a decision', async () => {
    discloseIdentityNumber.mockResolvedValue({ status: 'failed', reason: 'down' })
    setup()

    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.revealLabel }),
    )
    await userEvent.type(
      screen.getByRole('textbox', { name: MEMBER_IDENTITY.reasonLabel }),
      REASON,
    )
    await userEvent.click(
      screen.getByRole('button', { name: MEMBER_IDENTITY.confirmReveal }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(MEMBER_IDENTITY.failed)
  })
})

describe('the history', () => {
  test('says nobody has read it, rather than showing an empty list', () => {
    setup()

    expect(screen.getByText(MEMBER_IDENTITY.historyEmpty)).toBeInTheDocument()
  })

  test('names an auditor whose account is gone rather than showing a blank', () => {
    // SET_NULL: deleting the auditor's account must not erase the fact that a
    // disclosure happened, only who made it.
    setup(member({ disclosures: [disclosure({ read_by: null })] }))

    expect(screen.getByText(new RegExp(MEMBER_IDENTITY.historyUnknown))).toBeInTheDocument()
  })
})

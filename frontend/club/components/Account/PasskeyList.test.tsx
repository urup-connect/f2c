import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { PasskeyList } from './PasskeyList'
import type { Passkey } from '@/lib/api'
import { PASSKEYS_CARD } from '@/lib/club-content'

const LAPTOP: Passkey = {
  id: 1,
  name: 'Work laptop',
  backed_up: false,
  device_type: 'single_device',
  created_at: '2026-03-15T08:00:00Z',
  last_used_at: '2026-08-01T19:30:00Z',
}

const PHONE: Passkey = {
  id: 2,
  name: 'iPhone',
  backed_up: true,
  device_type: 'multi_device',
  created_at: '2026-04-02T08:00:00Z',
  last_used_at: null,
}

describe('with no passkeys', () => {
  test('says so', () => {
    render(<PasskeyList passkeys={[]} removingId={null} busy={false} onRemove={vi.fn()} />)

    expect(screen.getByText(PASSKEYS_CARD.empty)).toBeInTheDocument()
  })

  test('offers nothing to remove', () => {
    render(<PasskeyList passkeys={[]} removingId={null} busy={false} onRemove={vi.fn()} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

describe('with passkeys', () => {
  test('names each one', () => {
    render(
      <PasskeyList
        passkeys={[LAPTOP, PHONE]}
        removingId={null}
        busy={false}
        onRemove={vi.fn()}
      />,
    )

    expect(screen.getByText('Work laptop')).toBeInTheDocument()
    expect(screen.getByText('iPhone')).toBeInTheDocument()
  })

  test('marks the ones a password manager syncs', () => {
    render(
      <PasskeyList
        passkeys={[LAPTOP, PHONE]}
        removingId={null}
        busy={false}
        onRemove={vi.fn()}
      />,
    )

    expect(screen.getAllByText(PASSKEYS_CARD.synced)).toHaveLength(1)
  })

  test('says when each was added and last used', () => {
    render(<PasskeyList passkeys={[PHONE]} removingId={null} busy={false} onRemove={vi.fn()} />)

    expect(screen.getByText(new RegExp(PASSKEYS_CARD.neverUsed))).toBeInTheDocument()
  })

  test('names the passkey in its own remove button', () => {
    // A list of controls all called "Remove" is unusable from a screen reader.
    render(
      <PasskeyList
        passkeys={[LAPTOP, PHONE]}
        removingId={null}
        busy={false}
        onRemove={vi.fn()}
      />,
    )

    expect(
      screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: Work laptop` }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: iPhone` }),
    ).toBeInTheDocument()
  })

  test('hands back the id of the one to remove', async () => {
    const onRemove = vi.fn()

    render(
      <PasskeyList passkeys={[LAPTOP, PHONE]} removingId={null} busy={false} onRemove={onRemove} />,
    )

    await userEvent.click(
      screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: iPhone` }),
    )

    expect(onRemove).toHaveBeenCalledWith(2)
  })

  test('says which one is going, not all of them', () => {
    render(
      <PasskeyList passkeys={[LAPTOP, PHONE]} removingId={2} busy onRemove={vi.fn()} />,
    )

    expect(
      screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: iPhone` }),
    ).toHaveTextContent(PASSKEYS_CARD.removing)
    expect(
      screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: Work laptop` }),
    ).toHaveTextContent(PASSKEYS_CARD.remove)
  })

  test('stands every button down while a request is in flight', () => {
    render(
      <PasskeyList passkeys={[LAPTOP, PHONE]} removingId={2} busy onRemove={vi.fn()} />,
    )

    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled()
    }
  })
})

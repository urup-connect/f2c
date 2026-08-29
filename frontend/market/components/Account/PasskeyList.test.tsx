import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import type { Passkey } from '@/lib/api'
import { PASSKEYS_CARD } from '@/lib/store-content'
import { PasskeyList } from './PasskeyList'

const passkey = (overrides: Partial<Passkey> = {}): Passkey => ({
  id: 1,
  name: 'Windows PC',
  backed_up: false,
  device_type: 'single_device',
  created_at: '2026-03-15T10:00:00Z',
  last_used_at: null,
  ...overrides,
})

const noop = () => {}

describe('PasskeyList', () => {
  test('says there are none, and that a code still works', () => {
    // Somebody told they have no passkeys must not conclude they cannot get in.
    render(<PasskeyList passkeys={[]} removingId={null} busy={false} onRemove={noop} />)

    expect(screen.getByText(PASSKEYS_CARD.empty)).toBeInTheDocument()
  })

  test('names each passkey in its own remove button', async () => {
    // A screen full of buttons all called "Remove" is unusable from a list of controls.
    render(
      <PasskeyList
        passkeys={[passkey({ id: 1, name: 'Windows PC' }), passkey({ id: 2, name: 'iPhone' })]}
        removingId={null}
        busy={false}
        onRemove={noop}
      />,
    )

    expect(screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: Windows PC` })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: iPhone` })).toBeInTheDocument()
  })

  test('marks a synced passkey as one', () => {
    render(
      <PasskeyList passkeys={[passkey({ backed_up: true })]} removingId={null} busy={false} onRemove={noop} />,
    )

    expect(screen.getByText(PASSKEYS_CARD.synced)).toBeInTheDocument()
  })

  test('says which one is being removed, and only that one', () => {
    render(
      <PasskeyList
        passkeys={[passkey({ id: 1, name: 'Windows PC' }), passkey({ id: 2, name: 'iPhone' })]}
        removingId={2}
        busy
        onRemove={noop}
      />,
    )

    const removing = screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: iPhone` })
    const other = screen.getByRole('button', { name: `${PASSKEYS_CARD.remove}: Windows PC` })

    expect(removing).toHaveTextContent(PASSKEYS_CARD.removing)
    expect(other).toHaveTextContent(PASSKEYS_CARD.remove)
  })

  test('stands every button down while a request is in flight, not just the busy one', () => {
    render(
      <PasskeyList
        passkeys={[passkey({ id: 1 }), passkey({ id: 2, name: 'iPhone' })]}
        removingId={1}
        busy
        onRemove={noop}
      />,
    )

    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled()
    }
  })

  test('asks the card to remove the passkey that was clicked', async () => {
    const onRemove = vi.fn()

    render(
      <PasskeyList passkeys={[passkey({ id: 7 })]} removingId={null} busy={false} onRemove={onRemove} />,
    )

    await userEvent.click(screen.getByRole('button'))

    expect(onRemove).toHaveBeenCalledWith(7)
  })
})

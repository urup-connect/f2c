import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import type { AccountDestination } from '@/lib/navigation'
import { DestinationTile, PLANNED_BADGE, PLANNED_DESCRIPTION } from './DestinationTile'

const ready: AccountDestination = {
  key: 'details',
  title: 'Your details',
  description: 'Your name and the number a driver can reach you on.',
  state: 'ready',
  href: '/account/details',
}

const planned: AccountDestination = {
  key: 'orders',
  title: 'Your orders',
  description: 'Nothing here yet.',
  state: 'planned',
  href: null,
}

describe('DestinationTile', () => {
  test('renders a built destination as a link', () => {
    render(<DestinationTile destination={ready} />)

    expect(screen.getByRole('link', { name: /Your details/ })).toHaveAttribute(
      'href',
      '/account/details',
    )
  })

  test('renders a planned destination as no control at all', () => {
    // Not a disabled button and not an anchor to '#': a control that looks operable and does nothing
    // costs a sighted person a click and a screen-reader user considerably more.
    render(<DestinationTile destination={planned} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  test('badges a planned destination, and describes it in a full sentence', () => {
    render(<DestinationTile destination={planned} />)

    expect(screen.getByText(PLANNED_BADGE)).toBeInTheDocument()
    expect(screen.getByText(PLANNED_DESCRIPTION)).toBeInTheDocument()
  })

  test('says what a destination is for, whether or not it is built', () => {
    render(<DestinationTile destination={planned} />)

    expect(screen.getByText('Nothing here yet.')).toBeInTheDocument()
  })

  test('treats a ready destination with no href as planned rather than linking nowhere', () => {
    render(<DestinationTile destination={{ ...ready, href: null }} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText(PLANNED_BADGE)).toBeInTheDocument()
  })
})

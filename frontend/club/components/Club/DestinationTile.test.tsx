import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { DestinationTile } from './DestinationTile'
import { DESTINATIONS } from '@/lib/club-content'
import type { ClubDestination } from '@/lib/club-navigation'

const PLANNED: ClubDestination = {
  key: 'swap-zone',
  label: 'Enter the swap zone',
  description: 'Browse what other members have offered, and make a swap.',
  permission: 'platform.use_swap_zone',
  section: 'swap',
  state: 'planned',
  href: null,
}

const READY: ClubDestination = {
  ...PLANNED,
  key: 'own-inventory',
  label: 'Your plants',
  state: 'ready',
  href: '/member/plants',
}

describe('a destination that exists', () => {
  test('is a link to it', () => {
    render(<DestinationTile destination={READY} />)

    expect(screen.getByRole('link', { name: /Your plants/ })).toHaveAttribute(
      'href',
      '/member/plants',
    )
  })

  test('carries no "not built yet" badge', () => {
    render(<DestinationTile destination={READY} />)

    expect(screen.queryByText(DESTINATIONS.planned)).not.toBeInTheDocument()
  })
})

describe('a destination that does not exist yet', () => {
  test('says what it will be', () => {
    render(<DestinationTile destination={PLANNED} />)

    expect(screen.getByText('Enter the swap zone')).toBeInTheDocument()
    expect(screen.getByText(PLANNED.description)).toBeInTheDocument()
  })

  test('is not a link, so nobody is sent to a route that answers 404', () => {
    render(<DestinationTile destination={PLANNED} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  test('is not a control of any kind, so nothing looks operable', () => {
    // Not a disabled button either: a control that looks operable and does nothing
    // costs a click, and costs a screen-reader user considerably more.
    render(<DestinationTile destination={PLANNED} />)

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  test('is marked in words', () => {
    render(<DestinationTile destination={PLANNED} />)

    expect(screen.getByText(DESTINATIONS.planned)).toBeInTheDocument()
  })

  test('carries the badge in full for anyone who cannot see where it sits', () => {
    render(<DestinationTile destination={PLANNED} />)

    const notice = screen.getByText(DESTINATIONS.plannedDescription)

    expect(notice).toBeInTheDocument()
    expect(screen.getByText('Enter the swap zone').closest('div')).toHaveAttribute(
      'aria-describedby',
      notice.getAttribute('id'),
    )
  })
})

describe('a destination that claims to be ready with nowhere to go', () => {
  test('is treated as planned rather than linked to nothing', () => {
    render(<DestinationTile destination={{ ...READY, href: null }} />)

    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText(DESTINATIONS.planned)).toBeInTheDocument()
  })
})

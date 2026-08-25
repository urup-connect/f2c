import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { DestinationSections } from './DestinationSections'
import { DESTINATIONS } from '@/lib/club-content'
import { sectionsFor } from '@/lib/club-navigation'

const MEMBER_PERMISSIONS = [
  'platform.browse_catalogue',
  'platform.purchase_plants',
  'platform.use_swap_zone',
  'platform.manage_own_profile',
]

const ADMIN_PERMISSIONS = [
  'platform.manage_cultivators',
  'platform.manage_club_rules',
  'platform.manage_own_profile',
]

describe('DestinationSections', () => {
  test('heads the whole list once', () => {
    render(<DestinationSections sections={sectionsFor(MEMBER_PERMISSIONS)} />)

    expect(screen.getByRole('heading', { level: 2, name: DESTINATIONS.heading })).toBeInTheDocument()
  })

  test('bands what a member holds by subject', () => {
    render(<DestinationSections sections={sectionsFor(MEMBER_PERMISSIONS)} />)

    expect(screen.getByRole('heading', { level: 3, name: 'Plants and orders' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'The swap zone' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'Your account' })).toBeInTheDocument()
  })

  test('shows a member nothing that belongs to an administrator', () => {
    render(<DestinationSections sections={sectionsFor(MEMBER_PERMISSIONS)} />)

    expect(screen.queryByRole('heading', { name: 'Club administration' })).not.toBeInTheDocument()
    expect(screen.queryByText('Cultivators')).not.toBeInTheDocument()
  })

  test('shows an administrator the collective records', () => {
    render(<DestinationSections sections={sectionsFor(ADMIN_PERMISSIONS)} />)

    expect(screen.getByRole('heading', { level: 3, name: 'Club administration' })).toBeInTheDocument()
    expect(screen.getByText('Cultivators')).toBeInTheDocument()
    expect(screen.getByText('Club rules and documents')).toBeInTheDocument()
  })

  test('lists one item per destination', () => {
    render(<DestinationSections sections={sectionsFor(MEMBER_PERMISSIONS)} />)

    expect(screen.getAllByRole('listitem')).toHaveLength(MEMBER_PERMISSIONS.length)
  })

  test('says so when an account holds nothing it can act on', () => {
    // A sharing member, or a suspended account: the permission set is empty.
    render(<DestinationSections sections={sectionsFor([])} />)

    expect(screen.getByText(DESTINATIONS.empty)).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })
})

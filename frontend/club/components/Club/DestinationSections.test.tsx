import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { DestinationSections } from './DestinationSections'
import { DESTINATIONS } from '@/lib/club-content'
import { sectionsFor } from '@/lib/club-navigation'

/*
 * Neither fixture carries `platform.manage_own_profile`: Django retired it, and `own-profile` is
 * offered on the session instead — see `ClubDestination.permission`. So *Your account* still bands
 * for both, on one destination neither of these lists grants.
 */
const MEMBER_PERMISSIONS = [
  'platform.browse_catalogue',
  'platform.purchase_plants',
  'platform.use_swap_zone',
]

const ADMIN_PERMISSIONS = ['platform.manage_cultivators', 'platform.manage_club_rules']

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

    // One per codename held, plus the profile, which is offered on the session and so is not in
    // the fixture. Written as the sum rather than as a bare number so the two sources stay named.
    expect(screen.getAllByRole('listitem')).toHaveLength(MEMBER_PERMISSIONS.length + 1)
  })

  test('says so when it is given no bands at all', () => {
    /*
     * Given `[]` directly, not `sectionsFor([])`, and the change is worth stating. This used to be
     * reached the second way: an empty permission set produced no bands. It cannot be any more —
     * `own-profile` is offered on the session, so every signed-in account has at least *Your
     * account* — which makes this branch unreachable from `sectionsFor` and reachable only by a
     * caller handing the component nothing.
     *
     * The branch stays and is tested from that direction, because the component does not know its
     * caller: it takes `sections` as a prop, and a component that renders an empty list as a blank
     * page is worse than one that says the list is empty. What is no longer claimed is that a real
     * account can see it.
     */
    render(<DestinationSections sections={[]} />)

    expect(screen.getByText(DESTINATIONS.empty)).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })
})

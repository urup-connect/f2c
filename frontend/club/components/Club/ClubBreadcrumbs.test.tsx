import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { ClubBreadcrumbs } from './ClubBreadcrumbs'
import type { ClubHome } from '@/lib/club-breadcrumbs'
import { CLUB_HOMES_COPY, CLUB_SHELL } from '@/lib/club-content'
import { MEMBER_RECORD, MEMBER_REGISTER } from '@/lib/member-register-content'
import { MEMBERS_PATH, memberPath } from '@/lib/member-register-routes'

/*
 * What the trail looks like once it is drawn. Which crumbs a path produces is settled in
 * `lib/club-breadcrumbs.test.ts`; this is about the markup a person and a screen reader meet.
 */

const pathname = vi.hoisted(() => ({ current: '/admin' }))

vi.mock('next/navigation', () => ({
  usePathname: () => pathname.current,
}))

const HOME: ClubHome = { href: '/admin', label: CLUB_HOMES_COPY.admin.title }

const at = (path: string) => {
  pathname.current = path
  return render(<ClubBreadcrumbs home={HOME} />)
}

describe('ClubBreadcrumbs', () => {
  test('draws no landmark at all on a home', () => {
    // Not an empty nav: a landmark holding nothing is one a screen-reader user is invited into
    // for no reason.
    const { container } = at('/admin')

    expect(container).toBeEmptyDOMElement()
  })

  test('names the landmark, so it is not a second unlabelled nav', () => {
    at(memberPath('a-member-id'))

    expect(screen.getByRole('navigation', { name: CLUB_SHELL.breadcrumbLabel })).toBeInTheDocument()
  })

  test('offers the steps above as links', () => {
    at(memberPath('a-member-id'))

    expect(screen.getByRole('link', { name: CLUB_HOMES_COPY.admin.title })).toHaveAttribute(
      'href',
      '/admin',
    )
    expect(screen.getByRole('link', { name: MEMBER_REGISTER.title })).toHaveAttribute(
      'href',
      MEMBERS_PATH,
    )
  })

  test('the screen in hand is text, not a link to itself', () => {
    at(memberPath('a-member-id'))

    expect(screen.queryByRole('link', { name: MEMBER_RECORD.heading })).not.toBeInTheDocument()
    expect(screen.getByText(MEMBER_RECORD.heading)).toHaveAttribute('aria-current', 'page')
  })

  test('never names the record it is standing on', () => {
    // The id is all the trail is given, and that is the point: a member nickname in the chrome of
    // every screen buys nothing the heading below it does not already say.
    at(memberPath('a-member-id'))

    expect(screen.queryByText(/a-member-id/)).not.toBeInTheDocument()
  })

  test('hides the separators from a screen reader', () => {
    const { container } = at(memberPath('a-member-id'))

    expect(container.querySelectorAll('[aria-hidden="true"]')).toHaveLength(2)
  })
})

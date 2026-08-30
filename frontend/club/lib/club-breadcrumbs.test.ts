import { describe, expect, test } from 'vitest'
import { crumbsFor, type ClubHome } from './club-breadcrumbs'
import { CLUB_HOMES_COPY } from './club-content'
import { CLUB_HOME_PATHS, PROFILE_PATH } from './club-roles'
import { CATALOGUE_PATH, NEW_STRAIN_PATH, TERMS_PATH, strainPath } from './catalogue-routes'
import { MEMBERS_PATH, memberPath } from './member-register-routes'
import { MEMBER_RECORD, MEMBER_REGISTER } from './member-register-content'
import { CATALOGUE_LIST, STRAIN_FORM, TERMS_SCREEN } from './strain-catalogue-content'

/*
 * The trail above the content on every signed-in screen.
 *
 * The paths are taken from the route modules rather than typed out, so a route that moves takes
 * these tests with it instead of leaving them passing against an address that no longer exists.
 */

const ADMIN_HOME: ClubHome = { href: '/admin', label: CLUB_HOMES_COPY.admin.title }

const labels = (pathname: string, home: ClubHome = ADMIN_HOME): readonly string[] =>
  crumbsFor(pathname, home).map((crumb) => crumb.label)

describe('there is no trail where the trail would start', () => {
  test.each(CLUB_HOME_PATHS)('%s is a home and shows nothing', (path) => {
    expect(crumbsFor(path, ADMIN_HOME)).toEqual([])
  })

  test('nor does the front door', () => {
    expect(crumbsFor('/', ADMIN_HOME)).toEqual([])
  })

  /*
   * A route nobody has put in the table yields the home crumb and nothing else, and a bar holding
   * one link to the place the logo already goes is furniture rather than navigation.
   */
  test('nor does a route this build knows nothing about', () => {
    expect(crumbsFor('/admin/somewhere-new', ADMIN_HOME)).toEqual([])
  })
})

describe('the trail names the screens it passes through', () => {
  test('the register is one step below the home', () => {
    expect(labels(MEMBERS_PATH)).toEqual([CLUB_HOMES_COPY.admin.title, MEMBER_REGISTER.title])
  })

  test('a member record sits below the register', () => {
    expect(labels(memberPath('a-member-id'))).toEqual([
      CLUB_HOMES_COPY.admin.title,
      MEMBER_REGISTER.title,
      MEMBER_RECORD.heading,
    ])
  })

  test('the catalogue is one step below the home', () => {
    expect(labels(CATALOGUE_PATH)).toEqual([CLUB_HOMES_COPY.admin.title, CATALOGUE_LIST.title])
  })

  test('a strain sits below the catalogue', () => {
    expect(labels(strainPath('a-strain-id'))).toEqual([
      CLUB_HOMES_COPY.admin.title,
      CATALOGUE_LIST.title,
      STRAIN_FORM.editHeading,
    ])
  })

  /*
   * `new` and `terms` are static segments beside `[id]`, and Next.js resolves a static segment
   * first. The trail has to agree with the page that actually renders, or it would call the add
   * screen a strain.
   */
  test('a static segment wins over the dynamic one it sits beside', () => {
    expect(labels(NEW_STRAIN_PATH)).toEqual([
      CLUB_HOMES_COPY.admin.title,
      CATALOGUE_LIST.title,
      STRAIN_FORM.addHeading,
    ])

    expect(labels(TERMS_PATH)).toEqual([
      CLUB_HOMES_COPY.admin.title,
      CATALOGUE_LIST.title,
      TERMS_SCREEN.title,
    ])
  })

  /* The profile is one screen for every role, so the trail is the caller's home and that screen. */
  test('the profile hangs off whichever home the account has', () => {
    const member: ClubHome = { href: '/member', label: CLUB_HOMES_COPY.member.title }

    expect(labels(PROFILE_PATH, member)).toEqual([CLUB_HOMES_COPY.member.title, 'Your profile'])
  })
})

describe('only the parents are links', () => {
  test('the screen in hand carries no href', () => {
    const trail = crumbsFor(memberPath('a-member-id'), ADMIN_HOME)

    expect(trail.at(-1)?.href).toBeNull()
  })

  test('every step above it points somewhere', () => {
    const trail = crumbsFor(memberPath('a-member-id'), ADMIN_HOME)

    expect(trail.slice(0, -1).map((crumb) => crumb.href)).toEqual(['/admin', MEMBERS_PATH])
  })

  /*
   * Built from the path in hand rather than from the table, so a parent that is itself dynamic
   * keeps the id the visitor came through instead of a pattern.
   */
  test('a parent keeps the address it was reached by', () => {
    const trail = crumbsFor(strainPath('a-strain-id'), ADMIN_HOME)

    expect(trail[1]?.href).toBe(CATALOGUE_PATH)
  })

  test('the home crumb goes to the home it was given', () => {
    expect(crumbsFor(MEMBERS_PATH, ADMIN_HOME)[0]?.href).toBe('/admin')
  })
})

describe('the shape survives the awkward paths', () => {
  test('a trailing slash reads the same as none', () => {
    expect(labels(`${MEMBERS_PATH}/`)).toEqual(labels(MEMBERS_PATH))
  })

  test('an empty pathname yields nothing rather than throwing', () => {
    expect(crumbsFor('', ADMIN_HOME)).toEqual([])
  })

  test('every crumb has a key of its own, so React can tell them apart', () => {
    const trail = crumbsFor(memberPath('a-member-id'), ADMIN_HOME)
    const keys = trail.map((crumb) => crumb.key)

    expect(new Set(keys).size).toBe(trail.length)
  })
})

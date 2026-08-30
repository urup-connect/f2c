/**
 * The trail from a signed-in account's own home down to the screen it is standing on.
 *
 * The club's geography is shallow but it is no longer flat: an administrator reaches a member's
 * record two levels below their home, and until now the only way back up was the screen's own
 * "Back to the register" link or the browser button. This turns a URL into the row of crumbs above
 * the content, and nothing else.
 *
 * ## Derived from the path, not declared by the page
 *
 * Every screen would otherwise have to remember to pass a trail, and the one that forgot would be
 * the one a person got lost on. The table below is read against the pathname instead, so a route
 * that exists has a trail whether or not anyone thought about it -- the same reasoning that has
 * `ClubHeader` read its nav from the destination catalogue rather than listing routes of its own.
 *
 * The price is that a crumb cannot name the record. `/admin/members/<id>` reads "Member record"
 * rather than the member's nickname, because the id is all this module is given. That is a cost
 * worth paying twice over here: a nickname is a member's own name, and putting it in the chrome of
 * every screen -- where it is also the first thing a shoulder or a screenshot picks up -- buys
 * nothing the heading below it does not already say.
 *
 * ## Labels are borrowed, never written
 *
 * Each label below is the string that screen already uses for its own title or heading. A crumb
 * that said something else would be a second name for the same place, and the day one of them is
 * reworded is the day they disagree. It also keeps this module out of the copy-compliance corpora:
 * there is no new member-facing copy here to hold to a rule.
 */

import { CLUB_HOME_PATHS } from './club-roles'
import { PROFILE_COPY } from './club-content'
import { MEMBER_RECORD, MEMBER_REGISTER } from './member-register-content'
import { CATALOGUE_LIST, STRAIN_FORM, TERMS_SCREEN } from './strain-catalogue-content'

/** One step of the trail. `href` is null on the screen the visitor is already on. */
export type ClubCrumb = {
  /** Stable key for React and for tests. Never shown. */
  readonly key: string
  readonly label: string
  readonly href: string | null
}

/** Where the trail starts: this account's own home, named as that home names itself. */
export type ClubHome = {
  readonly href: string
  readonly label: string
}

/**
 * A route, as segments, with `*` standing for whatever the segment happens to be.
 *
 * `*` is a single segment and never more, so `admin/members/*` matches one member's record and
 * would not match something nested under it -- a route that deep would want its own entry here
 * rather than being swept up by this one.
 */
type ClubRoute = {
  readonly key: string
  readonly segments: readonly string[]
  readonly label: string
}

/**
 * Every signed-in route that is worth a crumb, in no particular order.
 *
 * The homes are absent on purpose: the home is the first crumb of every trail and is supplied by
 * the caller, which is the only way one table can serve three roles whose homes are three
 * different routes.
 *
 * A static entry and a `*` entry may both match -- `/admin/strains/new` matches `admin/strains/new`
 * and `admin/strains/*` -- and the static one wins. Next.js resolves its own routes the same way,
 * so the trail agrees with the page that is actually rendered rather than guessing at it.
 */
const CLUB_ROUTES: readonly ClubRoute[] = [
  { key: 'profile', segments: ['profile'], label: PROFILE_COPY.title },
  { key: 'members', segments: ['admin', 'members'], label: MEMBER_REGISTER.title },
  { key: 'member', segments: ['admin', 'members', '*'], label: MEMBER_RECORD.heading },
  { key: 'strains', segments: ['admin', 'strains'], label: CATALOGUE_LIST.title },
  { key: 'strain-new', segments: ['admin', 'strains', 'new'], label: STRAIN_FORM.addHeading },
  { key: 'strain-terms', segments: ['admin', 'strains', 'terms'], label: TERMS_SCREEN.title },
  { key: 'strain', segments: ['admin', 'strains', '*'], label: STRAIN_FORM.editHeading },
]

/** The path split into segments, with the empty strings a leading or trailing slash leaves. */
const segmentsOf = (pathname: string): readonly string[] =>
  pathname.split('/').filter((segment) => segment.length > 0)

/** Whether a route describes the first `route.segments.length` segments of this path. */
const covers = (route: ClubRoute, path: readonly string[]): boolean =>
  route.segments.length <= path.length &&
  route.segments.every((segment, index) => segment === '*' || segment === path[index])

/** The one route that describes this path at this depth, preferring a literal over a `*`. */
const routeAt = (path: readonly string[], depth: number): ClubRoute | null => {
  const candidates = CLUB_ROUTES.filter(
    (route) => route.segments.length === depth && covers(route, path),
  )

  return candidates.find((route) => !route.segments.includes('*')) ?? candidates[0] ?? null
}

/**
 * The trail for this path, or nothing at all.
 *
 * **Nothing at all is the answer for a home, and for anywhere unmapped.** A home is where the trail
 * starts, so on a home there is nothing above to point at; an unmapped route yields only the home
 * crumb, and a bar holding one link to the place the logo already goes is furniture rather than
 * navigation. Both cases return an empty list, and the component renders no landmark for it -- an
 * empty `nav` is somewhere a screen-reader user is invited into for no reason.
 *
 * The href of a parent crumb is built from the path in hand rather than from the table, so a
 * dynamic parent keeps the id the visitor actually came through.
 */
export const crumbsFor = (pathname: string, home: ClubHome): readonly ClubCrumb[] => {
  const path = segmentsOf(pathname)

  if (path.length === 0) return []
  if (CLUB_HOME_PATHS.includes(`/${path.join('/')}`)) return []

  const trail: ClubCrumb[] = []

  for (let depth = 1; depth <= path.length; depth += 1) {
    const route = routeAt(path, depth)

    if (route === null) continue

    trail.push({
      key: route.key,
      label: route.label,
      href: depth === path.length ? null : `/${path.slice(0, depth).join('/')}`,
    })
  }

  if (trail.length === 0) return []

  return [{ key: 'home', label: home.label, href: home.href }, ...trail]
}

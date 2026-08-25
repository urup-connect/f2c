/**
 * Which of the four roles has a home in the club, and where that home is.
 *
 * The role itself is Django's — `accounts/roles.py` owns the column, the catalogue and the
 * enforcement. What lives here is the one thing the browser has to decide for itself: after a
 * successful sign-in, which URL does this account belong on.
 *
 * Deliberately *only* that. What a role may **do** is never derived here — it arrives on the
 * session as `permissions`, and `lib/club-navigation.ts` reads that list. A second mapping of role
 * to ability in this bundle would drift from the one the API enforces, and the drift shows up as a
 * menu offering something the API then refuses. See
 * design/features/roles-and-permissions.md section 12.
 */

import type { User } from './api'

/** The three roles that sign in and have an area of their own. */
export const CLUB_ROLES = ['admin', 'cultivator', 'member'] as const

export type ClubRole = (typeof CLUB_ROLES)[number]

/**
 * Where each role lands.
 *
 * Distinct routes rather than one `/dashboard` that branches: the three areas answer to different
 * people and will diverge, and a route each means a layout each can follow them apart without a
 * switch statement growing in the middle.
 */
export const CLUB_HOMES = {
  admin: '/admin',
  cultivator: '/cultivator',
  member: '/member',
} as const satisfies Record<ClubRole, string>

/** Every club home, for a caller that needs to recognise one. */
export const CLUB_HOME_PATHS = Object.values(CLUB_HOMES) as readonly string[]

/** How the club refers to each role on screen. */
export const ROLE_LABELS = {
  admin: 'Administrator',
  cultivator: 'Cultivator',
  member: 'Member',
} as const satisfies Record<ClubRole, string>

export const isClubRole = (value: unknown): value is ClubRole =>
  typeof value === 'string' && CLUB_ROLES.some((role): boolean => role === value)

/**
 * The home this account belongs on, or `null` when it has none.
 *
 * `null` is the answer for `sharing_member`, which is an identity rather than an actor: it holds no
 * email address and a check constraint keeps the role out of Active, so no session can belong to
 * one and this branch is unreachable in practice. It is here because the type describes the column
 * rather than the subset a browser happens to see, and because "unreachable" is a claim about
 * today's constraints that a caller should not have to take on trust — a null sends the visitor
 * back to the front door instead of somewhere they cannot use.
 */
export const clubHomeFor = (role: User['role']): string | null =>
  isClubRole(role) ? CLUB_HOMES[role] : null

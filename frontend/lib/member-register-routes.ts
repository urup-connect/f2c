/**
 * Where the administrator's membership screens live.
 *
 * A module of its own so the two routes and the navigation entry read the same
 * strings, and so no component hard-codes a path. `catalogue-routes.ts` does the
 * same job for the strain screens, for the same reason: the day one of these
 * moves, a grep for a literal is not the test that it moved everywhere.
 *
 * **A member is addressed by id, and there is no alternative.** A strain has a
 * slug and this file's sibling explains why the id wins there anyway. Here the
 * question does not arise: a nickname is the only human-readable handle a member
 * has, it is theirs to change, and putting it in a back-office URL would both
 * break every bookmark on a rename and write a member's chosen name into the
 * access log of every proxy between here and the administrator's desk.
 *
 * There is no `new` segment, and that is a decision rather than a gap. The one
 * route into the membership is `POST /api/members/register`, because an account
 * typed in by hand would have no consent ledger behind it -- see
 * `app/membership/administration_api.py`.
 */

/** The register, and the destination the navigation points at. */
export const MEMBERS_PATH = '/admin/members'

/** One member's own record. */
export const memberPath = (id: string): string => `${MEMBERS_PATH}/${id}`

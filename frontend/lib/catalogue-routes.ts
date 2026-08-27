/**
 * Where the strain catalogue's screens live.
 *
 * A module of its own so the four routes and the navigation entry read the same
 * strings, and so a component never hard-codes a path. `club-roles.ts` does the
 * same job for `PROFILE_PATH`, for the same reason: the day one of these moves,
 * a grep for a literal is not the test that it moved everywhere.
 *
 * **A strain is addressed by id, not by slug.** The slug is derived from the name
 * on every write — `Strain.save` does it unconditionally — so a rename moves the
 * URL, and an administrator's bookmark or a colleague's pasted link would 404
 * against a strain that is still there. The slug is a member-facing browse key
 * and will be the one in Block 5's public routes; this is a back-office address
 * and wants the stable identifier.
 *
 * `terms` and `new` are static segments beside `[id]`. Next.js resolves a static
 * segment before a dynamic one, so neither is reachable as a strain id — and
 * neither could be one anyway, both being UUIDs.
 */

/** The catalogue list, and the destination the navigation points at. */
export const CATALOGUE_PATH = '/admin/strains'

/** The add screen. */
export const NEW_STRAIN_PATH = `${CATALOGUE_PATH}/new`

/** The aroma and effect vocabularies. */
export const TERMS_PATH = `${CATALOGUE_PATH}/terms`

/** One strain's own screen. */
export const strainPath = (id: string): string => `${CATALOGUE_PATH}/${id}`

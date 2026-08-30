/**
 * Primitives shared by every reader of deployment configuration.
 *
 * Pure and free of side effects on purpose: importing this module reads nothing and validates
 * nothing, so a module that needs only the `AppEnv` type does not pull another module's
 * configuration check in behind it.
 *
 * A copy of the club's file rather than an import from it, which is the decision recorded in
 * `frontend/README.md`: per-application environment reading is one of the three candidates for
 * `packages/`, and the boundary is drawn once there is a second consumer to draw it against. This
 * is that consumer. What the two applications already disagree about is which *variables* are
 * required, not these primitives — see `lib/site.ts`.
 */

export type AppEnv = 'local' | 'qa' | 'production'

export const APP_ENVS = ['local', 'qa', 'production'] as const satisfies readonly AppEnv[]

/**
 * Just the variables a reader needs.
 *
 * Narrower than NodeJS.ProcessEnv on purpose, which requires NODE_ENV: process.env satisfies
 * this, and a caller passing a synthetic environment does not have to invent unrelated variables
 * to do so.
 */
export type EnvRecord = Readonly<Record<string, string | undefined>>

/** Where a deployment variable is set. Most of them are set in both places. */
const DEFAULT_REMEDY =
  'Set it in .env.local for local development, or in the App Service application settings for QA and Production.'

/**
 * The one wording for a configuration failure, so every variable fails the same way and the
 * message says where to fix it rather than only what is wrong.
 */
export const misconfigured = (variable: string, problem: string, remedy: string = DEFAULT_REMEDY) =>
  new Error(`${variable} is ${problem}. ${remedy}`)

export const readAppEnv = (value: string | undefined): AppEnv => {
  if (!value) throw misconfigured('APP_ENV', 'not set')

  const match = APP_ENVS.find((appEnv) => appEnv === value)
  if (!match) {
    throw misconfigured('APP_ENV', `set to "${value}", which is not ${APP_ENVS.join(', ')}`)
  }

  return match
}

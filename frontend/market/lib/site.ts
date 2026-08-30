/**
 * Deployment configuration this application cannot run without.
 *
 * Indexing behaviour is derived from `APP_ENV` rather than from a flag of its own, so the QA store
 * cannot be made indexable by switching one boolean. That rule is the club's and it holds here
 * too: a QA store carrying test prices against real farm names is exactly as unwelcome in a search
 * index as a QA club.
 *
 * **Two variables, where the club reads three.** The club needs a `CDN_BASE_URL` for the film on
 * its landing page. Nothing in the store is served from the static host — a document's address
 * comes from Django, because Django owns its revisions, and produce imagery will arrive the same
 * way. A variable required here for the sake of symmetry would be a deployment setting nobody
 * could give a correct value to, and the first thing a deployment engineer would paste a wrong one
 * into.
 */

import { type AppEnv, type EnvRecord, misconfigured, readAppEnv } from './env'

export type SiteConfig = {
  readonly appEnv: AppEnv
  /** Absolute origin this deployment is served from, with no trailing slash. */
  readonly siteUrl: string
  readonly isProduction: boolean
}

const readSiteUrl = (value: string | undefined): string => {
  if (!value) throw misconfigured('SITE_URL', 'not set')

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw misconfigured('SITE_URL', `set to "${value}", which is not an absolute URL`)
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw misconfigured(
      'SITE_URL',
      `set to the "${url.protocol}" scheme, which is not http or https`,
    )
  }

  if (url.pathname !== '/' || url.search || url.hash) {
    throw misconfigured('SITE_URL', 'set to more than an origin. Give the scheme and host only')
  }

  // `origin` normalises the value and drops any trailing slash, so callers can append a path.
  return url.origin
}

/** Just the variables this reader needs. See `EnvRecord`. */
export type SiteEnv = EnvRecord

/** Validates an environment and throws naming the offending variable. Pure. */
export const readSiteConfig = (env: SiteEnv): SiteConfig => {
  const appEnv = readAppEnv(env.APP_ENV)

  return {
    appEnv,
    siteUrl: readSiteUrl(env.SITE_URL),
    isProduction: appEnv === 'production',
  }
}

/**
 * The running application's configuration.
 *
 * Read once when this module is first loaded, so a misconfigured deployment fails on the way up
 * rather than at whichever request first needed the value.
 */
export const SITE_CONFIG = readSiteConfig(process.env)

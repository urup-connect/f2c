/**
 * Deployment configuration this application cannot run without.
 *
 * See design/features/public-landing-and-auth-routing.md section 6.1. Indexing behaviour is
 * derived from `APP_ENV` rather than from a flag of its own, so the QA application cannot be
 * made indexable by switching one boolean.
 */

import { type AppEnv, type EnvRecord, misconfigured, readAppEnv } from './env'

export type SiteConfig = {
  readonly appEnv: AppEnv
  /** Absolute origin this deployment is served from, with no trailing slash. */
  readonly siteUrl: string
  /**
   * Root of the static content host for this deployment, with no trailing slash.
   *
   * The CDN root rather than any one folder on it. Callers append their own path.
   *
   * Read by `lib/brand-film.ts`, which builds the address of the landing page's club film. That
   * is the only reader. The club documents were the first thing served from here and no longer
   * come from configuration: Django owns their addresses now, because it owns their versions —
   * see `lib/club-documents.ts`.
   */
  readonly cdnBaseUrl: string
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
    throw misconfigured('SITE_URL', `set to the "${url.protocol}" scheme, which is not http or https`)
  }

  if (url.pathname !== '/' || url.search || url.hash) {
    throw misconfigured('SITE_URL', 'set to more than an origin. Give the scheme and host only')
  }

  // `origin` normalises the value and drops any trailing slash, so callers can append a path.
  return url.origin
}

/**
 * The static content host.
 *
 * Unlike SITE_URL a path is allowed, because this is a prefix on a shared host rather than a bare
 * origin. And unlike SITE_URL, plain http is refused anywhere but local development: what is
 * served from here includes the documents a member agrees to, and a document fetched over plain
 * http is a document anything on the path can rewrite.
 *
 * See design/features/club-document-agreements-at-sign-up.md section 6.4.
 */
const readCdnBaseUrl = (value: string | undefined, appEnv: AppEnv): string => {
  if (!value) throw misconfigured('CDN_BASE_URL', 'not set')

  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw misconfigured('CDN_BASE_URL', `set to "${value}", which is not an absolute URL`)
  }

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw misconfigured(
      'CDN_BASE_URL',
      `set to the "${url.protocol}" scheme, which is not http or https`,
    )
  }

  if (appEnv !== 'local' && url.protocol !== 'https:') {
    throw misconfigured('CDN_BASE_URL', `set to plain http, which is only permitted locally`)
  }

  if (url.search || url.hash) {
    throw misconfigured(
      'CDN_BASE_URL',
      'set to more than a prefix. Give the scheme, host and path only',
    )
  }

  // A trailing slash here is the easiest deployment mistake to make and the dullest to debug.
  return `${url.origin}${url.pathname}`.replace(/\/+$/, '')
}

/** Just the variables this reader needs. See `EnvRecord`. */
export type SiteEnv = EnvRecord

/** Validates an environment and throws naming the offending variable. Pure. */
export const readSiteConfig = (env: SiteEnv): SiteConfig => {
  const appEnv = readAppEnv(env.APP_ENV)

  return {
    appEnv,
    siteUrl: readSiteUrl(env.SITE_URL),
    cdnBaseUrl: readCdnBaseUrl(env.CDN_BASE_URL, appEnv),
    isProduction: appEnv === 'production',
  }
}

/**
 * The running application's configuration.
 *
 * Read once when this module is first loaded, so a misconfigured deployment fails on the way
 * up rather than at whichever request first needed the value.
 */
export const SITE_CONFIG = readSiteConfig(process.env)

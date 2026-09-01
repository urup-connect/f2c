/**
 * The carrier that gets a campaign from the link somebody clicked to the member they became.
 *
 * A visitor arrives on `/join?utm_source=instagram&utm_campaign=spring-open-day`, and the club
 * wants to know weeks later that this member came from that post. Nothing in between can carry it:
 * there is no session until they register, the age gate throws its own cookie away deliberately,
 * and a redirect carries only a URL. So the campaign travels in a cookie of its own — written by
 * `proxy` on the way in, read by the sign-up action on the way out, and sent to Django once, as
 * part of the registration that finally has a record to attach it to.
 *
 * **Two touches, and only two.** `first` is the campaign that found them and `last` is the one they
 * converted on. A visitor who arrives once has the same touch as both, which is the common case.
 * A full click history was considered and not kept: see `app/core/attribution/models.py`.
 *
 * **`httpOnly`, and unsigned.** Page scripts have no use for it, so they cannot read it. A
 * signature would stop a visitor forging a campaign they could equally have produced by editing
 * the URL before they clicked, which is no protection at all — so the rule is applied on the other
 * side instead: `attribution.services` cleans, caps or drops every value it is given and never
 * refuses a registration over one. The same reasoning as `lib/age-gate-cookie.ts`.
 *
 * **POPIA.** One first-party cookie, holding campaign labels the club wrote into its own links, a
 * referring site, a path on this site and a timestamp. No visitor id, no device fingerprint, no
 * third-party pixel, nothing that identifies anybody on its own — and nothing is stored server-side
 * until somebody registers, at which point the two touches are attached to the member they explain
 * and kept for as long as `CAMPAIGN_TOUCH_RETENTION_DAYS` says. That is what makes this a
 * legitimate-interest cookie described in the privacy notice rather than one behind a consent
 * banner. Adding a visitor identifier, or a network's own pixel, changes that answer.
 */

import type { SiteConfig } from './site'

/** Names the hand-off, never what it holds: cookie names show up in developer tools and logs. */
export const CAMPAIGN_COOKIE = 'cc_campaign'

/**
 * Ninety days, which is how long the campaign that found somebody stays attributable.
 *
 * The standard window for paid-click attribution, and long enough for the club's own funnel: a
 * visitor who reads an Instagram post, thinks about it and comes back three weeks later to join is
 * exactly the member this exists to explain. Past it their first touch is forgotten and the visit
 * they eventually convert on stands as both.
 *
 * The cookie is **not** refreshed on every page view. Its life runs from the last campaign arrival,
 * for two reasons: a rolling window would let one bookmarked tab carry a campaign for ever, and a
 * `Set-Cookie` on every response is a header that makes every page uncacheable.
 */
export const CAMPAIGN_COOKIE_MAX_AGE_SECONDS = 90 * 24 * 60 * 60

/** Bumped if the value's shape ever changes, so an old cookie is refused rather than misread. */
const VERSION = '1'

/**
 * How much of a value is kept. The same cap Django applies, stated here so that a cookie cannot be
 * built which the database would then quietly cut.
 */
const LABEL_LIMIT = 200
const CLICK_ID_LIMIT = 255
const ADDRESS_LIMIT = 255

/**
 * How long the cookie value may get before it is not worth sending.
 *
 * A browser drops a cookie over about 4KB without saying so, so a value that goes past this is
 * attribution already lost — better to shed the least useful fields and keep the campaign than to
 * write something the browser refuses whole. See `serialiseCampaign`.
 */
const VALUE_LIMIT = 3500

/**
 * The ad-click parameters, and which network each belongs to.
 *
 * The values must be `ClickNetwork` in `app/core/attribution/models.py`; Django drops a network it
 * does not recognise, so a typo here costs the click id silently. Order is precedence, for the
 * rare link that carries two.
 */
export const CLICK_ID_PARAMS = [
  ['gclid', 'google'],
  ['fbclid', 'meta'],
  ['msclkid', 'microsoft'],
  ['ttclid', 'tiktok'],
] as const

export type ClickNetwork = (typeof CLICK_ID_PARAMS)[number][1]

export type CampaignTouch = {
  readonly source: string
  readonly medium: string
  readonly campaign: string
  readonly term: string
  readonly content: string
  readonly clickNetwork: ClickNetwork | ''
  readonly clickId: string
  /** Origin and path of the site that linked here. Never the query string. */
  readonly referrer: string
  readonly landingPath: string
  /** When the visit happened. UTC, ISO 8601, exactly as `toISOString` writes it. */
  readonly seenAt: string
}

export type Campaign = {
  readonly first: CampaignTouch
  readonly last: CampaignTouch
}

const EMPTY: CampaignTouch = {
  source: '',
  medium: '',
  campaign: '',
  term: '',
  content: '',
  clickNetwork: '',
  clickId: '',
  referrer: '',
  landingPath: '',
  seenAt: '',
}

/** Exactly what `Date.prototype.toISOString` produces, and nothing looser. */
const UTC_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/

const text = (value: string | null | undefined, limit: number) =>
  (value ?? '')
    .replace(/\s+/g, ' ')
    // Control characters, after the whitespace collapse rather than before it: a tab is both, and
    // stripping first would turn `cape\ttown` into one word. Django does the same in the same order.
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .trim()
    .slice(0, limit)

/** One of the five `utm_*` values. Folded, so one channel is one row in every report. */
const label = (value: string | null | undefined) => text(value, LABEL_LIMIT).toLowerCase()

/**
 * A referring URL reduced to its origin and path, or `''` for one that tells us nothing.
 *
 * Three things become `''`. Our own site, because an internal navigation is not somebody arriving.
 * An unparseable value, because there is nothing to keep. And an absent header, which is what a
 * direct arrival and most privacy settings both look like.
 *
 * The query string goes. It can carry anything the referring site put in it — a search term, a
 * session id, an address in a badly built newsletter link — and none of it is needed to know which
 * site sent the visitor.
 */
export const readReferrer = (header: string | null | undefined, siteHost: string) => {
  const raw = text(header, ADDRESS_LIMIT * 2)
  if (!raw) return ''

  let parsed: URL
  try {
    parsed = new URL(raw)
  } catch {
    /*
     * Not a URL, but still evidence: an Android app referrer (`android-app://com.whatsapp`) parses,
     * while a malformed value does not and is worth nothing. Kept as text rather than guessed at.
     */
    return text(raw.split('?')[0].split('#')[0], ADDRESS_LIMIT)
  }

  if (parsed.host === siteHost) return ''

  /*
   * Rebuilt from the protocol and host rather than from `origin`, which is the obvious choice and is
   * wrong for exactly the referrers worth keeping: a scheme the URL standard does not treat as
   * special — `android-app://com.whatsapp`, where a good share of real word-of-mouth traffic comes
   * from — has an opaque origin, and reading it gives the string "null".
   */
  return text(`${parsed.protocol}//${parsed.host}${parsed.pathname}`, ADDRESS_LIMIT)
}

/**
 * The touch this arrival represents, or `null` if it is not one.
 *
 * `null` is the answer for an ordinary visit: no campaign parameters, no ad click, and either no
 * referrer or our own. Those visitors are **not** recorded as "direct" — nothing is written for them
 * at all, here or in Django, because an absence is honest and a stored value would invite somebody
 * to add "direct" up as a channel that had been measured.
 *
 * A referring site with no parameters on it *is* a touch. It is the largest untagged slice of real
 * traffic — a news article, a WhatsApp forward, another club's links page — and losing it would
 * leave the report describing only the traffic the club paid for.
 */
export const readTouch = (
  url: URL,
  referrerHeader: string | null | undefined,
  now: Date,
): CampaignTouch | null => {
  const parameter = (name: string) => label(url.searchParams.get(name))

  const clickEntry = CLICK_ID_PARAMS.map(
    ([parameterName, network]) =>
      [network, text(url.searchParams.get(parameterName), CLICK_ID_LIMIT)] as const,
  ).find(([, id]) => id !== '')

  const touch: CampaignTouch = {
    source: parameter('utm_source'),
    medium: parameter('utm_medium'),
    campaign: parameter('utm_campaign'),
    term: parameter('utm_term'),
    content: parameter('utm_content'),
    clickNetwork: clickEntry ? clickEntry[0] : '',
    clickId: clickEntry ? clickEntry[1] : '',
    referrer: readReferrer(referrerHeader, url.host),
    landingPath: text(url.pathname, ADDRESS_LIMIT),
    seenAt: now.toISOString(),
  }

  // `landingPath` and `seenAt` are deliberately not in this test. Every arrival has both, so
  // counting them would make every visit a campaign.
  const saysSomething =
    touch.source !== '' ||
    touch.medium !== '' ||
    touch.campaign !== '' ||
    touch.term !== '' ||
    touch.content !== '' ||
    touch.clickId !== '' ||
    touch.referrer !== ''

  return saysSomething ? touch : null
}

/**
 * What the cookie should hold after this arrival: the first touch it already had, and this one as
 * the last.
 *
 * A visitor whose cookie has expired, or who has none, starts again — so their first touch is the
 * campaign they are arriving on now, not the one they saw in April and cannot be linked to any
 * more.
 */
export const mergeCampaign = (existing: Campaign | null, touch: CampaignTouch): Campaign => ({
  first: existing?.first ?? touch,
  last: touch,
})

/*
 * The wire format: one flat `application/x-www-form-urlencoded` string, `f.` for the first touch
 * and `l.` for the last.
 *
 * Flat rather than nested JSON, because `URLSearchParams` escapes every value on the way out and
 * unescapes it on the way in — so a campaign name containing `&`, `;` or a space cannot break the
 * cookie, and there is no `JSON.parse` of client-supplied text in the path. Blank values are left
 * out entirely rather than written as empty keys, which is most of what keeps the value short.
 */
const KEYS: readonly (readonly [keyof CampaignTouch, string])[] = [
  ['source', 's'],
  ['medium', 'm'],
  ['campaign', 'c'],
  ['term', 't'],
  ['content', 'o'],
  ['clickNetwork', 'n'],
  ['clickId', 'i'],
  ['referrer', 'r'],
  ['landingPath', 'p'],
  ['seenAt', 'w'],
]

/**
 * Fields shed, in order, when the value will not fit. Least useful first: a keyword and a creative
 * name are detail, a referring site is a dimension, and the three that identify the campaign are
 * never dropped.
 */
const DROPPABLE: readonly (keyof CampaignTouch)[] = ['term', 'content', 'referrer']

const write = (campaign: Campaign, omit: readonly (keyof CampaignTouch)[]) => {
  const parameters = new URLSearchParams({ v: VERSION })

  for (const [prefix, touch] of [
    ['f', campaign.first],
    ['l', campaign.last],
  ] as const) {
    for (const [field, key] of KEYS) {
      const value = omit.includes(field) ? '' : touch[field]
      if (value) parameters.set(`${prefix}.${key}`, value)
    }
  }

  return parameters.toString()
}

/**
 * The cookie value for a campaign, or `null` if it cannot be made to fit.
 *
 * Shedding beats truncating: a value cut in the middle is a campaign name that reads almost right
 * and reports wrongly, while a dropped `utm_content` is a detail nobody was going to group by. If
 * even the campaign itself will not fit, nothing is written — a browser silently drops an
 * over-sized cookie anyway, so the alternative is the same loss with a corrupt value behind it.
 */
export const serialiseCampaign = (campaign: Campaign): string | null => {
  for (let dropped = 0; dropped <= DROPPABLE.length; dropped += 1) {
    const value = write(campaign, DROPPABLE.slice(0, dropped))
    if (value.length <= VALUE_LIMIT) return value
  }

  return null
}

const readTouchFrom = (parameters: URLSearchParams, prefix: string): CampaignTouch | null => {
  const touch = { ...EMPTY } as Record<keyof CampaignTouch, string>

  for (const [field, key] of KEYS) {
    touch[field] = parameters.get(`${prefix}.${key}`) ?? ''
  }

  // Read back through the same cleaning the write used. The cookie is a value the browser sends,
  // so it is a value somebody can edit; what this refuses is a doctored cookie becoming a wider
  // column than the database has, and Django cleans it a third time regardless.
  const cleaned: CampaignTouch = {
    source: label(touch.source),
    medium: label(touch.medium),
    campaign: label(touch.campaign),
    term: label(touch.term),
    content: label(touch.content),
    clickNetwork: CLICK_ID_PARAMS.some(([, network]) => network === touch.clickNetwork)
      ? (touch.clickNetwork as ClickNetwork)
      : '',
    clickId: text(touch.clickId, CLICK_ID_LIMIT),
    referrer: text(touch.referrer, ADDRESS_LIMIT),
    landingPath: text(touch.landingPath, ADDRESS_LIMIT),
    seenAt: UTC_INSTANT.test(touch.seenAt) ? touch.seenAt : '',
  }

  const saysSomething =
    cleaned.source !== '' ||
    cleaned.medium !== '' ||
    cleaned.campaign !== '' ||
    cleaned.term !== '' ||
    cleaned.content !== '' ||
    cleaned.clickId !== '' ||
    cleaned.referrer !== ''

  return saysSomething ? cleaned : null
}

/**
 * The campaign a cookie holds, or `null` for anything that cannot be used.
 *
 * A missing cookie, a wrong version, a value that says nothing: all one answer, because the caller
 * does the same thing with each of them — registers a member with no campaign, which is what most
 * members have.
 *
 * A cookie holding only one usable touch answers with that touch as both. The alternative is a
 * first touch and no last, which would make "how many joined on the campaign that found them"
 * depend on which half happened to survive.
 */
export const readCampaign = (value: string | undefined): Campaign | null => {
  if (!value) return null

  const parameters = new URLSearchParams(value)
  if (parameters.get('v') !== VERSION) return null

  const first = readTouchFrom(parameters, 'f')
  const last = readTouchFrom(parameters, 'l')

  if (!first && !last) return null

  return { first: first ?? last!, last: last ?? first! }
}

export type CampaignCookieOptions = {
  readonly httpOnly: true
  readonly sameSite: 'lax'
  readonly path: '/'
  readonly secure: boolean
  readonly maxAge: number
}

/**
 * `sameSite: 'lax'` is load-bearing here, more than on the other two cookies.
 *
 * Every arrival this cookie exists to record is a cross-site navigation — from an Instagram post,
 * from a search result, from an ad. `strict` would withhold the cookie on exactly those requests,
 * so a returning visitor's first touch would be invisible on the visit that matters.
 *
 * `secure` follows the scheme the site is actually served on rather than the environment name.
 * Marking a cookie `Secure` on a plain-http local server means the browser never sends it back,
 * which looks exactly like attribution that does not work.
 */
export const campaignCookieOptions = ({ siteUrl }: SiteConfig): CampaignCookieOptions => ({
  httpOnly: true,
  sameSite: 'lax',
  path: '/',
  secure: siteUrl.startsWith('https:'),
  maxAge: CAMPAIGN_COOKIE_MAX_AGE_SECONDS,
})

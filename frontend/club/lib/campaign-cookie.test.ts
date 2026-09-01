import { describe, expect, test } from 'vitest'
import {
  CAMPAIGN_COOKIE,
  CAMPAIGN_COOKIE_MAX_AGE_SECONDS,
  CLICK_ID_PARAMS,
  campaignCookieOptions,
  mergeCampaign,
  readCampaign,
  readReferrer,
  readTouch,
  serialiseCampaign,
} from './campaign-cookie'
import type { Campaign, CampaignTouch } from './campaign-cookie'
import type { SiteConfig } from './site'

/*
 * Two properties run through this file.
 *
 * A tagged arrival is captured, and an ordinary visit is not. Half of these tests assert `null`,
 * which is the answer that keeps a bookmark, an internal navigation and a form submission from
 * being recorded as campaigns nobody ran.
 *
 * And a campaign survives the round trip unchanged — folded and trimmed, but not otherwise
 * rewritten — because the value that comes back out of the cookie is the value the club will read
 * in a report months later.
 */

const NOW = new Date('2026-08-20T10:00:00Z')
const SITE = 'club.example.co.za'

const config = (overrides: Partial<SiteConfig> = {}): SiteConfig => ({
  appEnv: 'local',
  siteUrl: 'http://localhost:3000',
  cdnBaseUrl: 'http://localhost:3000/static',
  supportEmail: 'hello@example.invalid',
  isProduction: false,
  ...overrides,
})

const url = (path: string) => new URL(`https://${SITE}${path}`)

const touchOf = (path: string, referrer: string | null = null) =>
  readTouch(url(path), referrer, NOW)

const campaignOf = (first: CampaignTouch, last: CampaignTouch): Campaign => ({ first, last })

describe('reading an arrival', () => {
  test('the five parameters are picked up', () => {
    const touch = touchOf(
      '/join?utm_source=instagram&utm_medium=social&utm_campaign=spring' +
        '&utm_term=cape+town&utm_content=carousel-2',
    )

    expect(touch).toMatchObject({
      source: 'instagram',
      medium: 'social',
      campaign: 'spring',
      term: 'cape town',
      content: 'carousel-2',
    })
  })

  test('a label is folded to lower case, so one channel is one row', () => {
    expect(touchOf('/?utm_source=Instagram')?.source).toBe('instagram')
  })

  test('the landing path is kept and its query string is not', () => {
    const touch = touchOf('/join?utm_source=instagram')

    expect(touch?.landingPath).toBe('/join')
  })

  test('the arrival is timed', () => {
    expect(touchOf('/?utm_source=instagram')?.seenAt).toBe(NOW.toISOString())
  })

  test('an untagged visit is not an arrival', () => {
    // No parameters, no click, no referrer. Nothing is recorded for them at all — not even a
    // campaign called "direct".
    expect(touchOf('/')).toBeNull()
  })

  test('an internal navigation is not an arrival', () => {
    expect(touchOf('/signup', `https://${SITE}/join`)).toBeNull()
  })

  test('a referring site with no parameters is an arrival', () => {
    // The largest untagged slice of real traffic: an article, a forward, another site's links page.
    const touch = touchOf('/', 'https://news24.com/health/story')

    expect(touch?.referrer).toBe('https://news24.com/health/story')
    expect(touch?.source).toBe('')
  })
})

describe('the ad click', () => {
  test.each(CLICK_ID_PARAMS.map(([parameter, network]) => ({ parameter, network })))(
    '$parameter is recorded as $network',
    ({ parameter, network }) => {
      const touch = touchOf(`/?${parameter}=XYZ123`)

      expect(touch?.clickNetwork).toBe(network)
      expect(touch?.clickId).toBe('XYZ123')
    },
  )

  test('a click id alone is an arrival', () => {
    expect(touchOf('/?gclid=abc')).not.toBeNull()
  })

  test('the id keeps its case, unlike a label', () => {
    // It is a token the network looks up, not a name somebody reads.
    expect(touchOf('/?gclid=AbCdEf')?.clickId).toBe('AbCdEf')
  })

  test('the first network in precedence order wins a link carrying two', () => {
    expect(touchOf('/?fbclid=meta-id&gclid=google-id')?.clickNetwork).toBe('google')
  })
})

describe('the referrer', () => {
  test('keeps its origin and path', () => {
    expect(readReferrer('https://news24.com/health/story', SITE)).toBe(
      'https://news24.com/health/story',
    )
  })

  test('loses its query string', () => {
    // A referring site's query can carry anything it put there, including an address in a badly
    // built newsletter link.
    expect(readReferrer('https://mail.example.com/read?to=a@b.co', SITE)).toBe(
      'https://mail.example.com/read',
    )
  })

  test('loses its fragment', () => {
    expect(readReferrer('https://news24.com/story#comments', SITE)).toBe(
      'https://news24.com/story',
    )
  })

  test('is empty for our own site', () => {
    expect(readReferrer(`https://${SITE}/join`, SITE)).toBe('')
  })

  test('is empty when the browser sent none', () => {
    expect(readReferrer(null, SITE)).toBe('')
  })

  test('keeps an app referrer, which is still evidence', () => {
    expect(readReferrer('android-app://com.whatsapp', SITE)).toBe('android-app://com.whatsapp')
  })
})

describe('keeping the first touch', () => {
  test('the arriving campaign is the last touch', () => {
    const first = touchOf('/?utm_source=instagram')!
    const second = touchOf('/?utm_source=google&utm_medium=cpc')!

    const merged = mergeCampaign(campaignOf(first, first), second)

    expect(merged.first.source).toBe('instagram')
    expect(merged.last.source).toBe('google')
  })

  test('a visitor with no cookie is their own first touch', () => {
    const touch = touchOf('/?utm_source=instagram')!

    expect(mergeCampaign(null, touch)).toEqual({ first: touch, last: touch })
  })
})

describe('the cookie value', () => {
  test('round-trips a campaign', () => {
    const touch = touchOf(
      '/join?utm_source=instagram&utm_medium=social&utm_campaign=spring&gclid=abc',
      'https://l.instagram.com/?u=x',
    )!
    const campaign = campaignOf(touch, touch)

    expect(readCampaign(serialiseCampaign(campaign)!)).toEqual(campaign)
  })

  test('round-trips two different touches', () => {
    const first = touchOf('/?utm_source=instagram')!
    const last = touchOf('/signup?utm_source=google&utm_medium=cpc')!

    const read = readCampaign(serialiseCampaign(campaignOf(first, last))!)

    expect(read?.first.source).toBe('instagram')
    expect(read?.last.source).toBe('google')
  })

  test('survives a value containing the characters a cookie cares about', () => {
    // `URLSearchParams` escapes on the way out and unescapes on the way in, which is the whole
    // reason the format is not hand-rolled.
    const touch = touchOf('/?utm_campaign=' + encodeURIComponent('a;b&c=d e'))!

    expect(readCampaign(serialiseCampaign(campaignOf(touch, touch))!)?.first.campaign).toBe(
      'a;b&c=d e',
    )
  })

  test('leaves out what a touch does not carry', () => {
    const touch = touchOf('/?utm_source=instagram')!

    expect(serialiseCampaign(campaignOf(touch, touch))).not.toContain('.t=')
  })

  test('sheds the least useful fields rather than growing past a cookie', () => {
    const long = 'x'.repeat(200)
    const touch = touchOf(
      `/?utm_source=instagram&utm_campaign=${long}&utm_term=${long}&utm_content=${long}`,
      `https://${long}.example.com/${long}`,
    )!

    const value = serialiseCampaign(campaignOf(touch, touch))!
    const read = readCampaign(value)

    // The three that identify the campaign are never dropped; the detail is.
    expect(read?.first.source).toBe('instagram')
    expect(read?.first.campaign).toBe(long)
    expect(value.length).toBeLessThanOrEqual(3500)
  })
})

describe('reading a cookie back', () => {
  test('an absent cookie is no campaign', () => {
    expect(readCampaign(undefined)).toBeNull()
  })

  test('a cookie from an older shape is refused rather than misread', () => {
    expect(readCampaign('v=0&f.s=instagram')).toBeNull()
  })

  test('a cookie saying nothing is no campaign', () => {
    expect(readCampaign('v=1&f.p=%2Fjoin')).toBeNull()
  })

  test('a doctored value is cleaned, not trusted', () => {
    // The cookie is `httpOnly`, but it is still a value the browser sends. Django cleans it a third
    // time regardless.
    const read = readCampaign(`v=1&f.s=${'x'.repeat(400)}&l.s=instagram`)

    expect(read?.first.source).toHaveLength(200)
  })

  test('an unrecognised click network is dropped', () => {
    expect(readCampaign('v=1&f.s=x&f.n=carrier-pigeon&f.i=abc')?.first.clickNetwork).toBe('')
  })

  test('a timestamp that is not one is dropped, and the campaign is not', () => {
    const read = readCampaign('v=1&f.s=instagram&f.w=yesterday')

    expect(read?.first.seenAt).toBe('')
    expect(read?.first.source).toBe('instagram')
  })

  test('one usable touch answers as both', () => {
    // Otherwise "how many joined on the campaign that found them" would depend on which half of a
    // cookie happened to survive.
    const read = readCampaign('v=1&l.s=instagram')

    expect(read?.first.source).toBe('instagram')
    expect(read?.last.source).toBe('instagram')
  })
})

describe('the cookie itself', () => {
  test('is named for the hand-off and not for what it holds', () => {
    expect(CAMPAIGN_COOKIE).toBe('cc_campaign')
  })

  test('lasts ninety days, the standard attribution window', () => {
    expect(CAMPAIGN_COOKIE_MAX_AGE_SECONDS).toBe(90 * 24 * 60 * 60)
  })

  test('cannot be read by page scripts', () => {
    expect(campaignCookieOptions(config()).httpOnly).toBe(true)
  })

  test('is sent on a cross-site arrival, which is every arrival it exists for', () => {
    // `strict` would withhold it on exactly the navigations this cookie is about.
    expect(campaignCookieOptions(config()).sameSite).toBe('lax')
  })

  test('is secure when the site is', () => {
    expect(campaignCookieOptions(config({ siteUrl: 'https://club.example.co.za' })).secure).toBe(
      true,
    )
  })

  test('is not secure on a plain-http local server, which would drop it', () => {
    expect(campaignCookieOptions(config()).secure).toBe(false)
  })
})

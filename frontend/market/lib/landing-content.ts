/**
 * Every word on the front door.
 *
 * One file, so the whole public voice of the store can be read and signed off in one sitting. The
 * page is a layout over this rather than prose interleaved with markup.
 *
 * **This copy names prices, quantities and farms outright**, which the club's does not and may not.
 * That contrast is the reason `copy-compliance.ts` stays in the club application: the store's
 * honesty about what something costs is the club's compliance failure, and one shared corpus would
 * have to be held to the stricter of the two.
 *
 * Nothing here promises a catalogue that exists. The store is not trading yet, and the front door
 * says so in `notYet` rather than inviting a shopper to browse a page that would be empty — a
 * launch banner that overstates is a support ticket on the first day.
 */

import { STORE_BRAND } from './brand'

export const LANDING = {
  /** The tab and the social title. The name alone: the description carries the sentence. */
  title: STORE_BRAND.name,
  description: STORE_BRAND.standfirst,

  hero: {
    kicker: 'Straight from the farm',
    heading: 'Produce, priced honestly, from the farm that grew it.',
    standfirst: STORE_BRAND.standfirst,
    /** The two controls in the hero. Signing in comes second: most visitors are new. */
    primary: 'Create an account',
    secondary: 'Sign in',
  },

  /** Said plainly, high up, because a shopper who cannot buy yet deserves to know immediately. */
  notYet: {
    heading: 'The store is not open yet',
    body:
      'Farms are being brought on and the catalogue is being built. Create an account now and you are ready the day it opens — there is nothing to pay and no subscription.',
  },

  howItWorks: {
    heading: 'How it will work',
    steps: [
      {
        key: 'browse',
        title: 'See what is ready',
        body:
          'Each farm lists what it has picked, what it costs, and how much of it there is. No minimum order.',
      },
      {
        key: 'buy',
        title: 'Buy by the quantity you want',
        body:
          'A kilogram, a bunch, a punnet, a dozen. You pay the farm’s price plus delivery, and nothing else.',
      },
      {
        key: 'delivered',
        title: 'Picked, packed, delivered',
        body:
          'Orders are picked against the delivery window you choose, so what arrives was in the ground this week.',
      },
    ],
  },

  why: {
    heading: 'Why buy this way',
    points: [
      {
        key: 'named',
        title: 'You know the farm',
        body:
          'Every listing carries the farm’s name, where it is, and what other buyers thought of it.',
      },
      {
        key: 'price',
        title: 'The price is the price',
        body:
          'What the farm asks is what you see. Delivery is shown separately, before you commit.',
      },
      {
        key: 'account',
        title: 'An account, not a membership',
        body:
          'An email address is all it takes. No subscription, no identity documents, nothing to renew.',
      },
    ],
  },

  footer: {
    /** The legal pages come from Django, so the footer links to the index rather than listing them. */
    legalLabel: 'Terms, privacy and data',
    /** Completed with the year at the call site: a fixed year in a copy file goes stale silently. */
    copyrightSuffix: `${STORE_BRAND.name}. All rights reserved.`,
    /** Named rather than implied. The two storefronts are separate businesses on separate domains. */
    platformNote:
      'A South African marketplace. Prices include VAT where it applies; most fresh produce is zero-rated.',
  },
} as const

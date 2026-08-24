import type { BrandImageKey } from './brand'
import type { BrandValueIconKey } from './brand-icons'

/**
 * Every word on the public landing page, in one place.
 *
 * The copy is fixed brand content rather than anything a caller varies, so the sections read it
 * from here rather than taking it as props. Keeping it together also means the client's sign-off
 * pass has one file to review, and `ALL_COPY` gives the compliance tests a corpus that cannot
 * fall out of step with the page.
 *
 * Source of each line, and what it may not say, are recorded in
 * design/features/landing-page-engagement.md section 6.1.1.
 */

export type BrandValue = {
  readonly iconKey: BrandValueIconKey
  readonly label: string
  readonly description: string
}

export type StoryStep = {
  readonly imageKey: BrandImageKey
  readonly label: string
  readonly description: string
}

/** Existing wording, already approved as the root layout's page description. */
export const HERO = {
  eyebrow: 'Cultivators Collective',
  tagline: 'Growing together. Delivering excellence.',
  proposition:
    'A cannabis club for members, by cultivators. Connecting members with trusted cultivators through a premium club experience built on quality, transparency and community.',
  signUp: 'Sign Up',
  logIn: 'Log In',
} as const

/** The strapline the guidelines deck repeats along the foot of every slide. */
export const STRAPLINE_SEGMENTS = [
  'A cannabis club for members',
  'Grown by cultivators',
  'Made for community',
] as const

/** Quoted from the guidelines deck's brand-values slide, with sentence-case labels. */
export const VALUES = {
  heading: 'What the collective stands for',
  items: [
    {
      iconKey: 'community',
      label: 'Community first',
      description: 'We grow together and succeed together.',
    },
    {
      iconKey: 'quality',
      label: 'Quality and care',
      description: 'Premium cultivators dedicated to quality.',
    },
    {
      iconKey: 'sustainability',
      label: 'Sustainable cultivation',
      description: 'Respect for the plant, people and planet.',
    },
    {
      iconKey: 'trust',
      label: 'Trust and transparency',
      description: 'Open, honest and member focused.',
    },
  ] as const satisfies readonly [BrandValue, BrandValue, BrandValue, BrandValue],
} as const

/** Written for this page from the deck's account of what the emblem means. */
export const STORY = {
  heading: 'From root to harvest',
  paragraphs: [
    'Our emblem is a cannabis leaf with its roots showing. The roots are the point. Every plant in the collective is planted, nurtured and harvested by a cultivator, never sourced anonymously.',
    'The circle around it is the collective itself — a membership built on shared standards, open information, and respect for the plant, the people who grow it and the ground it grows in.',
  ],
  imageKey: 'leafCanopy',
  steps: [
    {
      imageKey: 'handsSeedling',
      label: 'Planted',
      description: 'Every plant starts with a cultivator who chose it.',
    },
    {
      imageKey: 'glovedHarvest',
      label: 'Tended',
      description: 'Grown with care and checked by hand, season after season.',
    },
    {
      imageKey: 'fieldSunrise',
      label: 'Shared',
      description: 'Brought together as a collective, grower and member alike.',
    },
  ] as const satisfies readonly [StoryStep, StoryStep, StoryStep],
} as const satisfies { imageKey: BrandImageKey; [key: string]: unknown }

export const JOIN = {
  heading: 'Ready to grow with us?',
  body: 'Sign up to join the collective, or log in if you are already a member.',
  /*
   * Sign-up cannot work until the access mechanism is decided, so the page says so rather than
   * showing a button that leads nowhere without warning.
   * See design/features/landing-page-engagement.md risk 5.
   */
  note: 'The club is not yet open. Sign-up will follow shortly.',
  signUp: 'Sign Up',
  logIn: 'Log In',
} as const

/** No year, so nothing in a statically generated page goes stale. */
export const FOOTER = {
  rights: 'Cultivators Collective. All rights reserved.',
} as const

/**
 * Every line above, flattened. Assembled here rather than in the test, so a string cannot be
 * added to the page without the compliance tests seeing it.
 */
export const ALL_COPY: readonly string[] = [
  HERO.eyebrow,
  HERO.tagline,
  HERO.proposition,
  HERO.signUp,
  HERO.logIn,
  ...STRAPLINE_SEGMENTS,
  VALUES.heading,
  ...VALUES.items.flatMap((item) => [item.label, item.description]),
  STORY.heading,
  ...STORY.paragraphs,
  ...STORY.steps.flatMap((step) => [step.label, step.description]),
  JOIN.heading,
  JOIN.body,
  JOIN.note,
  JOIN.signUp,
  JOIN.logIn,
  FOOTER.rights,
]

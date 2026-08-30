/**
 * Every word on the create-an-account screen.
 *
 * The screen's promise is deliberately small — an account, not a membership — because that is the
 * commercial difference between the two storefronts and the reason the store can open first. Copy
 * that implied a subscription, a joining fee or an approval step would be describing the club.
 */

import { STORE_BRAND } from './brand'

export const SIGN_UP = {
  title: 'Create an account',
  standfirst:
    'An email address and a name. No subscription, no joining fee, and nothing to renew.',

  firstNameLabel: 'First name',
  lastNameLabel: 'Last name',
  emailLabel: 'Email address',
  emailHint: 'This is how you sign in, and where a delivery notice goes.',
  mobileLabel: 'Mobile number',
  mobileHint: 'Optional. A driver uses it to reach you on the day of a delivery.',

  submit: 'Create my account',
  submitting: 'Creating your account…',

  /** Under the form: somebody who already has an account is on the wrong screen. */
  haveAccount: 'Already have an account?',
  haveAccountLink: 'Sign in',

  /** Said above the button, because it is the one thing people expect and will not find. */
  noPassword:
    'There is no password to choose. You sign in with a passkey, or with a six-digit code emailed to you.',

  back: `Back to ${STORE_BRAND.name}`,
} as const

/** What the form says when it refuses a value, keyed by reason. */
export const SIGN_UP_REFUSAL_MESSAGES = {
  'name-missing': 'Please give this name.',
  'name-too-long': 'That is longer than the store can store. Please shorten it.',
  'name-unexpected-characters': 'That does not look like a name.',
  'email-missing': 'Please give an email address.',
  'email-malformed': 'That does not look like an email address.',
  'email-too-long': 'That address is longer than an email address can be.',
  'mobile-unexpected-characters': 'A mobile number is digits, and may carry + ( ) . or -',
  'mobile-length': 'A South African mobile number has ten digits, starting 0.',
  'mobile-not-a-mobile': 'That does not look like a South African mobile number.',
} as const

/**
 * What the screen says once the store has answered.
 *
 * The accepted wording is conditional in the same way the sign-in screen's is — *if that address did
 * not already have one* — because the outcome is identical for a fresh address and one already on
 * file. Saying "your account has been created" to somebody whose address was already registered
 * would be telling them something that did not happen; saying "that address already has an account"
 * would be telling anybody who asks who shops here.
 */
export const SIGN_UP_OUTCOME = {
  acceptedHeading: 'Check your email',
  /** Completed with the address at the call site. */
  acceptedBodyPrefix: 'If',
  acceptedBodySuffix:
    'did not already have an account, one has been created and a six-digit sign-in code is on its way. Enter it on the sign-in screen.',
  acceptedAction: 'Go to sign-in',

  /** The endpoint does not exist yet. Said plainly, because it is nobody's mistake. */
  unavailableHeading: 'Accounts are not open yet',
  unavailableBody:
    'The store is not taking new accounts at the moment. Nothing you typed has been kept. Please try again once the store opens for orders.',

  refusedHeading: 'Something needs correcting',
  failedHeading: 'That did not work',
  failedBody:
    'Your account could not be created just now, and the fault is ours rather than yours. Please try again shortly.',
} as const

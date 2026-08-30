/**
 * Every word on the legal index.
 *
 * The documents themselves are not here and never will be: their text lives in Django, versioned, with
 * a digest and an effective date, because what a shopper agreed to has to be reproducible years
 * later. This file is the frame around a list the API supplies.
 */

import { STORE_BRAND } from './brand'

export const LEGAL = {
  title: 'Terms, privacy and data',
  standfirst: `The documents that govern buying from ${STORE_BRAND.name}, at the revision currently in force.`,

  /** Prefixes for the line under each title. Completed with the values at the call site. */
  versionLabel: 'Revision',
  fromLabel: 'in force from',
  /** The link on each row. Named for the document, so a screen reader's link list is not "Read, Read". */
  readPrefix: 'Read',

  /**
   * Said when the storefront has nothing published.
   *
   * True today, and it must not read as an error: the endpoint works, the store's documents simply
   * have not been written. `design/todo.md` Block B carries them.
   */
  noneHeading: 'Nothing published yet',
  noneBody:
    'The store’s terms, privacy notice and data policy are being drafted. They will appear here, each with the date it took effect, before the store opens for orders.',

  /** Said when Django could not be reached. A different sentence, deliberately. */
  unavailableHeading: 'These could not be loaded',
  unavailableBody:
    'The documents could not be read just now. This is a fault on our side rather than a sign that there are none — please try again shortly.',

  back: `Back to ${STORE_BRAND.name}`,
} as const

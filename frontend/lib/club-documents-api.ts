import 'server-only'

import { apiBaseUrl } from './api'
import { readClubDocumentRevisions } from './club-documents'
import type { ClubDocumentsResult } from './club-documents'

/**
 * Reads the club documents in force from Django.
 *
 * Server-side only. The endpoint is unauthenticated — sign-up happens before an account exists —
 * so no cookies are forwarded and no session is involved.
 *
 * **Fails closed.** A network error, a 503 from Django because a document has no published
 * revision, or a body that does not carry all three documents all resolve to `unusable`. Callers
 * refuse the form rather than rendering part of it. Nothing here throws, so a route does not need
 * a try/catch around it to stay up.
 */
export const fetchClubDocumentRevisions = async (): Promise<ClubDocumentsResult> => {
  let response: Response

  try {
    response = await fetch(`${apiBaseUrl()}/api/documents/current`, {
      /*
       * Never cached. Caching is opt-in in this version of Next, so the default would already
       * read live on a route that touches cookies — but stating it means a route that stops
       * doing so cannot silently start serving a document revision from build time.
       *
       * There is nothing to gain by caching this. A revision published in the admin should be
       * what the next member reads, and a stale copy costs a member a refusal on submit for no
       * benefit at all.
       */
      cache: 'no-store',
    })
  } catch {
    return {
      status: 'unusable',
      reason: 'The club documents could not be read: the API is unreachable.',
    }
  }

  if (!response.ok) {
    return {
      status: 'unusable',
      reason: `The club documents could not be read: the API answered ${response.status}.`,
    }
  }

  let payload: unknown

  try {
    payload = await response.json()
  } catch {
    return { status: 'unusable', reason: 'The documents response was not JSON.' }
  }

  return readClubDocumentRevisions(payload)
}

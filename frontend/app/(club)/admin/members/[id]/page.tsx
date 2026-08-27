import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { MemberScreen } from '@/components/Admin/MemberScreen'
import { requireRole } from '@/lib/club-session'
import { MEMBER_RECORD } from '@/lib/member-register-content'
import { MEMBERS_PATH } from '@/lib/member-register-routes'
import { getMember } from '@/lib/server-api'

export const metadata: Metadata = {
  title: MEMBER_RECORD.heading,
}

/**
 * One member's record: their details, their standing, their subscription, their document.
 *
 * Addressed by id. A nickname is the only human-readable handle a member has,
 * it is theirs to change, and putting it in a back-office URL would break every
 * bookmark on a rename and write a member's chosen name into the access log of
 * every proxy in between — see `member-register-routes.ts`.
 *
 * `params` is a promise and is awaited. That is the Next.js 16 contract, not a
 * flourish: it was synchronous through version 14 and accessing it that way is
 * on its way out.
 *
 * ## The metadata does not name the member, and here that is not only about cost
 *
 * The strain screen leaves its title generic to avoid a second read. This one
 * would have the record in hand and still must not use it: a browser tab, a
 * window title and a session-restore list are all places a member's name would
 * end up for no operational gain. "Member record" is the title, on purpose.
 *
 * ## Three answers, one page
 *
 * A member who does not exist, an account that may not manage the membership,
 * and a session that has expired all arrive as null and all become a 404.
 * Folding them is the safer answer as well as the simpler one: a 404 and a 403
 * that rendered differently would tell somebody without the permission which
 * account ids exist.
 */
export default async function MemberPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const viewer = await requireRole('admin')

  const { id } = await params

  const member = await getMember(id)

  if (member === null) notFound()

  return (
    <MemberScreen initial={member} viewerId={viewer.id} registerHref={MEMBERS_PATH} />
  )
}

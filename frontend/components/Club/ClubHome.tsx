import Link from 'next/link'

import type { Passkey, User } from '@/lib/api'
import { detailRows, greetingName } from '@/lib/club-account'
import { CLUB_HOMES_COPY, DETAILS_CARD, MEMBERSHIP_CARD } from '@/lib/club-content'
import { sectionsFor } from '@/lib/club-navigation'
import { PROFILE_PATH, type ClubRole } from '@/lib/club-roles'
import { PasskeyCard } from '@/components/Account/PasskeyCard'
import { ClubCard } from './ClubCard'
import { DestinationSections } from './DestinationSections'
import { DetailList } from './DetailList'
import { MembershipSummary } from './MembershipSummary'

type ClubHomeProps = {
  role: ClubRole
  user: User
  passkeys: readonly Passkey[]
  /** True when the server could not read the passkey list, so the card says so. */
  passkeysUnavailable: boolean
}

/**
 * One role's home page.
 *
 * Three routes share this because the difference between them turned out to be two sentences. What
 * a member sees below the greeting comes from their permissions, not from which page they are on —
 * so an administrator's screen is not a different component, it is the same one drawing a different
 * catalogue. The alternative was three near-identical pages that would have drifted the first time
 * anybody changed one of them.
 *
 * The cards are ordered by what the club can actually do for someone today: what it holds about
 * them, how they stand, how they get back in, and then everything it intends to offer. That last
 * card is the largest and the least useful, which is why it is last.
 *
 * The details card **shows** four fields and changes none of them. It used to say that changing them
 * was not possible at all; two of the four now are, on /profile, so it links there instead — and it
 * still says which two are not, because a member who goes looking for the email address on that
 * screen and does not find it has been sent on a wasted trip.
 */
export const ClubHome = ({ role, user, passkeys, passkeysUnavailable }: ClubHomeProps) => {
  const copy = CLUB_HOMES_COPY[role]
  const name = greetingName(user)

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <div>
        <p className="font-sans text-sm uppercase tracking-label text-muted-foreground">
          {copy.title}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {name ? `${copy.greeting}, ${name}` : copy.greeting}
        </h1>
        <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
          {copy.standfirst}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <ClubCard heading={DETAILS_CARD.heading}>
          <DetailList rows={detailRows(user)} />

          {/*
            * The note is rendered here rather than passed to `note`, because it now ends in a link
            * and that prop takes a string. Two sentences, and they say different things: the first
            * is what a member can do, the second is what they cannot and who to ask. Splitting them
            * is what stops the link reading as though it led to all four fields.
            */}
          <div className="mt-6 flex flex-col gap-2">
            <p className="font-sans text-sm leading-relaxed text-muted-foreground">
              {DETAILS_CARD.note}{' '}
              <Link
                href={PROFILE_PATH}
                className="font-medium text-forest-green underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
              >
                {DETAILS_CARD.editLabel}
              </Link>
            </p>
            <p className="font-sans text-sm leading-relaxed text-muted-foreground">
              {DETAILS_CARD.fixedNote}
            </p>
          </div>
        </ClubCard>

        <ClubCard heading={MEMBERSHIP_CARD.heading}>
          <MembershipSummary role={user.role} status={user.status} />
        </ClubCard>
      </div>

      <PasskeyCard initial={passkeys} unavailable={passkeysUnavailable} />

      <DestinationSections sections={sectionsFor(user.permissions)} />
    </div>
  )
}

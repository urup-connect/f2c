import type { Passkey, User } from '@/lib/api'
import { detailRows, greetingName } from '@/lib/club-account'
import { CLUB_HOMES_COPY, DETAILS_CARD, MEMBERSHIP_CARD } from '@/lib/club-content'
import { sectionsFor } from '@/lib/club-navigation'
import type { ClubRole } from '@/lib/club-roles'
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
        <ClubCard heading={DETAILS_CARD.heading} note={DETAILS_CARD.note}>
          <DetailList rows={detailRows(user)} />
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

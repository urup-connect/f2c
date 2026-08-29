import { membershipStanding } from '@/lib/club-account'
import { MEMBERSHIP_CARD } from '@/lib/club-content'
import type { User } from '@/lib/api'
import { ROLE_LABELS, isClubRole } from '@/lib/club-roles'

type MembershipSummaryProps = {
  role: User['role']
  status: User['membership_status']
}

/**
 * What this account is, and how it stands.
 *
 * Two facts that are easy to confuse and are kept visibly apart, because the platform keeps them
 * apart: `role` says what the account *is*, and the standing says where the club membership stands.
 * They were one column until the split; the account may sign in perfectly well while the membership
 * is unpaid, which is the case this card now has to be able to show. An
 * administrator and a member are equally capable of being suspended, and a suspended account of
 * either kind holds no permissions — so the standing is not a footnote to the role, it is the other
 * half of the sentence. See design/features/roles-and-permissions.md section 1.
 *
 * A role with no label is a sharing member, which cannot hold a session. It falls back to the raw
 * value rather than rendering nothing, so an impossible state looks odd rather than looking empty.
 */
export const MembershipSummary = ({ role, status }: MembershipSummaryProps) => {
  const standing = membershipStanding(status)

  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1">
        <dt className="font-sans text-xs uppercase tracking-label text-muted-foreground">
          {MEMBERSHIP_CARD.roleLabel}
        </dt>
        <dd className="font-sans text-base text-foreground">
          {isClubRole(role) ? ROLE_LABELS[role] : role}
        </dd>
      </div>

      <div className="flex flex-col gap-1">
        <dt className="font-sans text-xs uppercase tracking-label text-muted-foreground">
          {MEMBERSHIP_CARD.statusLabel}
        </dt>
        <dd className="font-sans text-base text-foreground">
          {standing.label}
          <span className="mt-1 block font-sans text-sm text-muted-foreground">
            {standing.note}
          </span>
        </dd>
      </div>
    </dl>
  )
}

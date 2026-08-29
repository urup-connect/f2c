import { ClubCard } from '@/components/Club/ClubCard'
import { PROFILE_COPY } from '@/lib/club-content'
import { identityLines } from '@/lib/profile-display'
import type { Profile } from '@/lib/profile-api'

type IdentityCardProps = {
  profile: Profile
}

/**
 * The two fields taken from an identity document, and no way to change either.
 *
 * Not a client component and not a form: there is nothing here to submit. That is the point of
 * giving them a card of their own rather than greyed-out inputs in the form above. A disabled input
 * still looks like an input, so a member spends a moment trying to click into it before concluding
 * it is broken; a described list is unmistakably a record being shown.
 *
 * The standfirst says *why* they cannot be changed and what to do instead. A read-only field with
 * no explanation is the commonest way a screen invites a support request.
 *
 * A description list rather than a table, for the reason `DetailList` gives: each line is a term and
 * its value, and a table would claim a relationship between the two rows that does not exist. It is
 * a separate component from `DetailList` because each line here carries a note as well, and folding
 * an optional third slot into that one to serve this would complicate the four rows that do not
 * need it.
 */
export const IdentityCard = ({ profile }: IdentityCardProps) => {
  const copy = PROFILE_COPY.identity

  return (
    <ClubCard heading={copy.heading} standfirst={copy.standfirst}>
      <dl className="grid gap-6 sm:grid-cols-2">
        {identityLines(profile).map((line) => (
          <div key={line.key} className="flex flex-col gap-1">
            <dt className="font-sans text-xs uppercase tracking-label text-muted-foreground">
              {line.label}
            </dt>
            <dd
              className={
                line.value === null
                  ? 'font-sans text-base italic text-muted-foreground'
                  : 'font-sans text-base text-foreground'
              }
            >
              {/*
                * A masked number is a run of asterisks and four digits, which a screen reader
                * spells out one asterisk at a time. `tabular-nums` is for the eye; the reason the
                * note below exists is for the ear -- it says in words what the asterisks mean.
                */}
              <span className={line.key === 'idNumber' ? 'tabular-nums' : undefined}>
                {line.value ?? copy.blank}
              </span>

              {line.note ? (
                <span className="mt-1 block font-sans text-sm not-italic text-muted-foreground">
                  {line.note}
                </span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </ClubCard>
  )
}

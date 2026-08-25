'use client'

import { useState } from 'react'

import { PROFILE_COPY } from '@/lib/club-content'
import type { Profile } from '@/lib/profile-api'
import { AvatarCard } from './AvatarCard'
import { IdentityCard } from './IdentityCard'
import { ProfileDetailsForm } from './ProfileDetailsForm'

type ProfileScreenProps = {
  /** The record as the server rendered it. The starting state, not a fetch trigger. */
  initial: Profile
}

/**
 * The whole profile screen, and the one place that holds which record is current.
 *
 * A client component wrapping three cards, and the reason is the single piece of shared state:
 * every write in here — a saved form, an uploaded photograph, a removed one — answers with the whole
 * profile, and both editing cards need to see it. Without one owner, saving a surname and then
 * uploading a photograph would send the pre-rename record back to the server, because the avatar
 * card would still be holding the profile it was mounted with.
 *
 * `initial` is trusted for the first paint and nothing is fetched on mount. A member should never
 * see their own profile screen blank for a frame; that reads as though the club had lost the
 * record. The same reasoning as `PasskeyCard`'s `initial`.
 *
 * The cards are ordered by how likely a member is to be here for each: the details they came to
 * correct, the photograph they came to add, and then the two facts they can only read. The last is
 * last because nothing can be done about it.
 */
export const ProfileScreen = ({ initial }: ProfileScreenProps) => {
  const [profile, setProfile] = useState(initial)

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10">
      <div>
        <p className="font-sans text-sm uppercase tracking-label text-muted-foreground">
          {PROFILE_COPY.title}
        </p>
        <h1 className="mt-2 font-display text-4xl tracking-display text-forest-green">
          {PROFILE_COPY.heading}
        </h1>
        <p className="mt-3 max-w-2xl font-sans text-base leading-relaxed text-muted-foreground">
          {PROFILE_COPY.standfirst}
        </p>
      </div>

      <ProfileDetailsForm profile={profile} onSaved={setProfile} />

      <AvatarCard profile={profile} onChanged={setProfile} />

      <IdentityCard profile={profile} />
    </div>
  )
}

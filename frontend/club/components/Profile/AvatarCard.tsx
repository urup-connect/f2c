'use client'

import { useEffect, useRef, useState } from 'react'

import { ClubCard } from '@/components/Club/ClubCard'
import { PROFILE_COPY } from '@/lib/club-content'
import { avatarSrc, deleteAvatar, postAvatar, type Profile } from '@/lib/profile-api'
import { ApiError } from '@/lib/api'
import { initials } from '@/lib/profile-display'
import { ImageCropper } from './ImageCropper'

/**
 * What the file picker will offer, and the ceiling it is checked against here.
 *
 * The same 8MB as `AVATAR_MAX_UPLOAD_BYTES` in `app/core/accounts/avatars.py`, checked in the browser as
 * well because the alternative is uploading eight megabytes in order to be told it was too many.
 * The server checks regardless: this is a courtesy, not the rule.
 */
const MAX_BYTES = 8 * 1024 * 1024

/**
 * The types the picker suggests.
 *
 * Not a validation — a file dialog's filter is a hint, and a member can always choose "all files".
 * What decides is whether the bytes decode, in Pillow, on the server.
 */
const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif'

type AvatarCardProps = {
  profile: Profile
  /** Told the record as it now stands, whenever this card changes it. */
  onChanged: (profile: Profile) => void
}

const BUTTON =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60'

const QUIET_BUTTON =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 border-border bg-surface px-8 font-sans text-base font-medium text-foreground transition-colors hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60'

/**
 * The member's photograph: what is on file, and the two things they can do about it.
 *
 * Three decisions worth reading.
 *
 * **The object URL is revoked, and revoked in an effect rather than after the upload.** A `blob:`
 * URL is a reference the browser holds until told otherwise, and one per chosen file adds up to the
 * whole file kept alive in memory. Tying the revoke to the state it belongs to means it happens on
 * every path out — uploaded, cancelled, replaced with another choice, or the page navigated away
 * from — rather than on the one path somebody remembered.
 *
 * **The file input is hidden and driven by a button.** Not for looks: a bare `input type="file"`
 * cannot be labelled with the club's own words, and its own text is written by the browser in the
 * browser's language. The input keeps its label for a screen reader; the button is what is seen.
 *
 * **A refused file is reported before the cropper opens.** The size check is here rather than after
 * cropping, because a member who has spent a moment framing their face and is then told the file
 * was too large has been made to do the work twice.
 *
 * **Removing asks nothing.** No confirmation dialog: the action is one click to undo — choose the
 * image again — and a `confirm()` would block the whole page on a modal the club cannot style. What
 * it does do is say what happened, because a photograph vanishing with no word looks like a fault.
 */
export const AvatarCard = ({ profile, onChanged }: AvatarCardProps) => {
  const copy = PROFILE_COPY.photograph

  const [chosen, setChosen] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isRemoving, setIsRemoving] = useState(false)

  const picker = useRef<HTMLInputElement>(null)

  /*
   * One effect, keyed on the URL it owns. React runs the cleanup when `chosen` changes and when the
   * component unmounts, which between them are every way this URL stops being needed.
   */
  useEffect(() => {
    if (chosen === null) return
    return () => URL.revokeObjectURL(chosen)
  }, [chosen])

  const src = avatarSrc(profile.avatar_url)
  const busy = isUploading || isRemoving

  const choose = (file: File | undefined) => {
    if (!file) return

    setProblem(null)

    if (file.size > MAX_BYTES) {
      setProblem(copy.tooLarge)
      return
    }

    /*
     * The declared type is a hint from the operating system and is checked loosely: a HEIC from a
     * phone sometimes arrives as `application/octet-stream`, and refusing it here would refuse the
     * commonest photograph on the commonest handset. Anything that is not an image at all fails at
     * the cropper, which cannot decode it, and at the server, which will not.
     */
    if (file.type !== '' && !file.type.startsWith('image/')) {
      setProblem(copy.notAnImage)
      return
    }

    setChosen(URL.createObjectURL(file))
  }

  const upload = async (blob: Blob) => {
    setProblem(null)
    setIsUploading(true)

    try {
      onChanged(await postAvatar(blob))
      setChosen(null)
    } catch (caught) {
      // A 422 is the server's own wording about the image and is worth showing verbatim; anything
      // else is ours to phrase, because it is not about the file the member chose.
      setProblem(
        caught instanceof ApiError && caught.status === 422 ? caught.message : copy.failed,
      )
    } finally {
      setIsUploading(false)
    }
  }

  const remove = async () => {
    setProblem(null)
    setIsRemoving(true)

    try {
      onChanged(await deleteAvatar())
    } catch {
      setProblem(copy.failed)
    } finally {
      setIsRemoving(false)
    }
  }

  const cancel = () => {
    setChosen(null)
    setProblem(null)
    // The picker keeps the last file it was given, so choosing the same one again would fire no
    // change event and the cropper would never reopen.
    if (picker.current) picker.current.value = ''
  }

  return (
    <ClubCard heading={copy.heading} standfirst={copy.standfirst}>
      <div className="flex flex-col gap-6">
        {chosen === null ? (
          <div className="flex flex-wrap items-center gap-6">
            {src ? (
              /* eslint-disable-next-line @next/next/no-img-element -- the avatar endpoint is
                 session-authed, and next/image would fetch it from the server, where there is no
                 session, and get a 401. */
              <img
                src={src}
                alt={copy.imageAlt}
                width={128}
                height={128}
                className="size-32 rounded-card border-2 border-border object-cover"
              />
            ) : (
              <div
                aria-hidden="true"
                className="flex size-32 items-center justify-center rounded-card border-2 border-dashed border-border bg-surface-muted font-display text-3xl tracking-display text-muted-foreground"
              >
                {initials(profile)}
              </div>
            )}

            <div className="flex flex-col gap-3">
              {src ? null : (
                <p className="font-sans text-sm text-muted-foreground">{copy.empty}</p>
              )}

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => picker.current?.click()}
                  disabled={busy}
                  className={BUTTON}
                >
                  {src ? copy.replace : copy.choose}
                </button>

                {profile.has_avatar ? (
                  <button
                    type="button"
                    onClick={remove}
                    disabled={busy}
                    className={QUIET_BUTTON}
                  >
                    {isRemoving ? copy.removing : copy.remove}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ) : (
          <ImageCropper
            src={chosen}
            busy={isUploading}
            confirmLabel={isUploading ? copy.uploading : copy.upload}
            onCropped={upload}
            onCancel={cancel}
          />
        )}

        {/*
          * Kept in the DOM rather than mounted with the cropper, so its label survives and the
          * button above always has something to click. `sr-only` rather than `hidden`: a
          * `display: none` input cannot be focused, which in some browsers stops `click()` opening
          * the dialog at all.
          */}
        <label className="sr-only" htmlFor="avatar-file">
          {copy.choose}
        </label>
        <input
          ref={picker}
          id="avatar-file"
          name="avatar-file"
          type="file"
          accept={ACCEPT}
          disabled={busy}
          onChange={(event) => choose(event.target.files?.[0])}
          className="sr-only"
        />

        {problem ? (
          <p
            role="alert"
            className="rounded-control border-2 border-error px-4 py-3 font-sans text-sm font-medium text-error"
          >
            {problem}
          </p>
        ) : null}
      </div>
    </ClubCard>
  )
}

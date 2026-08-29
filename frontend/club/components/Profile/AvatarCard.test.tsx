import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { PROFILE_COPY } from '@/lib/club-content'
import { ApiError } from '@/lib/api'
import type { Profile } from '@/lib/profile-api'
import { AvatarCard } from './AvatarCard'

/*
 * The card holding a member's photograph.
 *
 * The two calls are mocked, and so is `URL.createObjectURL`, which jsdom does not implement. That
 * last one is not incidental — one of the properties under test is that **every object URL is
 * revoked**, and a `blob:` URL that is not is the whole chosen file kept alive in memory for as long
 * as the tab is open. It is invisible until a member has tried four photographs.
 *
 * The cropper is mocked to a button, so this file tests the card's own decisions: what is refused
 * before the cropper opens, what happens to each of the two calls' outcomes, and the revocation.
 * `ImageCropper.test.tsx` tests the cropper.
 */

const { postAvatar, deleteAvatar } = vi.hoisted(() => ({
  postAvatar: vi.fn(),
  deleteAvatar: vi.fn(),
}))

vi.mock('@/lib/profile-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/profile-api')>()),
  postAvatar,
  deleteAvatar,
}))

/**
 * A stand-in for the cropper: one button that hands back a blob, one that cancels.
 *
 * Mocked because a real crop needs a canvas with a decoded image in it, which jsdom has neither of.
 * What this file cares about is that the card opens it, and what it does with the answer.
 */
vi.mock('./ImageCropper', () => ({
  ImageCropper: ({
    onCropped,
    onCancel,
    confirmLabel,
  }: {
    onCropped: (blob: Blob) => void
    onCancel: () => void
    confirmLabel: string
  }) => (
    <div>
      <button type="button" onClick={() => onCropped(new Blob(['x'], { type: 'image/jpeg' }))}>
        {confirmLabel}
      </button>
      <button type="button" onClick={onCancel}>
        {PROFILE_COPY.photograph.cancel}
      </button>
    </div>
  ),
}))

const copy = PROFILE_COPY.photograph

const WITHOUT: Profile = {
  first_name: 'Thandi',
  last_name: 'Mokoena',
  nickname: 'greenfingers',
  email: 'thandi@example.co.za',
  mobile: '+27821234567',
  display_name: 'greenfingers',
  date_of_birth: '1980-01-01',
  date_of_birth_verified_at: null,
  has_id_number: true,
  id_number_masked: '*********9087',
  has_avatar: false,
  avatar_url: null,
  role: 'member',
  status: 'active',
}

const WITH: Profile = {
  ...WITHOUT,
  has_avatar: true,
  avatar_url: '/api/accounts/me/avatar?v=1770000000',
}

const createObjectURL = vi.fn(() => 'blob:chosen')
const revokeObjectURL = vi.fn()

/** A file of a given size, without allocating one: only `size` and `type` are ever read. */
const file = (name: string, type: string, size: number) => {
  const made = new File(['x'], name, { type })
  Object.defineProperty(made, 'size', { value: size })
  return made
}

/**
 * Choose a file, as a member who picked "all files" in the dialog.
 *
 * `applyAccept: false` is the point rather than a convenience. The input's `accept` list is a hint
 * the file dialog offers and every browser lets a member override it, so a card that relied on it
 * would be a card with no rule at all — and two of the tests below are about exactly the files it
 * would have filtered out. Left on, `user.upload` would drop them before the component saw them and
 * the tests would pass by never running.
 */
const choose = async (chosen: File) => {
  const user = userEvent.setup({ applyAccept: false })
  await user.upload(screen.getByLabelText(copy.choose), chosen)
}

beforeEach(() => {
  postAvatar.mockReset()
  deleteAvatar.mockReset()
  createObjectURL.mockClear()
  revokeObjectURL.mockClear()

  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('what the card shows', () => {
  test('is a named region', () => {
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    expect(screen.getByRole('region', { name: copy.heading })).toBeInTheDocument()
  })

  test('shows initials and says there is no photograph yet', () => {
    // A blank circle where a face should be reads as an image that failed to load.
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    expect(screen.getByText('TM')).toBeInTheDocument()
    expect(screen.getByText(copy.empty)).toBeInTheDocument()
  })

  test('offers no way to remove a photograph that does not exist', () => {
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    expect(screen.queryByRole('button', { name: copy.remove })).not.toBeInTheDocument()
  })

  test('shows the photograph at an absolute address', () => {
    // The API returns a root-relative path, which would resolve against Next.js and 404 there while
    // the image sits happily on Django.
    render(<AvatarCard profile={WITH} onChanged={vi.fn()} />)

    const image = screen.getByAltText(copy.imageAlt)
    expect(image.getAttribute('src')).toMatch(/^https?:\/\/.+\/api\/accounts\/me\/avatar\?v=/)
  })

  test('offers to replace and to remove once there is one', () => {
    render(<AvatarCard profile={WITH} onChanged={vi.fn()} />)

    expect(screen.getByRole('button', { name: copy.replace })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: copy.remove })).toBeInTheDocument()
  })
})

describe('choosing a file', () => {
  test('opens the cropper', async () => {
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))

    expect(await screen.findByRole('button', { name: copy.upload })).toBeInTheDocument()
  })

  test('refuses an oversized file before the cropper opens', async () => {
    /*
     * Checked here rather than after cropping. A member who has spent a moment framing their face
     * and is then told the file was too large has been made to do the work twice -- and the eight
     * megabytes would have been uploaded to find out.
     */
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('huge.jpg', 'image/jpeg', 9 * 1024 * 1024))

    expect(await screen.findByRole('alert')).toHaveTextContent(copy.tooLarge)
    expect(screen.queryByRole('button', { name: copy.upload })).not.toBeInTheDocument()
  })

  test('refuses a file that is plainly not an image', async () => {
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('notes.pdf', 'application/pdf', 1000))

    expect(await screen.findByRole('alert')).toHaveTextContent(copy.notAnImage)
  })

  test('accepts a file whose type the system did not name', async () => {
    /*
     * A HEIC from a phone sometimes arrives with no type at all. Refusing it here would refuse the
     * commonest photograph on the commonest handset; anything that is not an image fails at the
     * cropper, which cannot decode it, and at the server, which will not.
     */
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('IMG_0001.HEIC', '', 1000))

    expect(await screen.findByRole('button', { name: copy.upload })).toBeInTheDocument()
  })
})

describe('uploading', () => {
  test('sends the crop and reports the new record', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    postAvatar.mockResolvedValue(WITH)
    render(<AvatarCard profile={WITHOUT} onChanged={onChanged} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.upload }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(WITH))
    expect(postAvatar).toHaveBeenCalledOnce()
    expect(postAvatar.mock.calls[0][0]).toBeInstanceOf(Blob)
  })

  test('closes the cropper once it has been stored', async () => {
    const user = userEvent.setup()
    postAvatar.mockResolvedValue(WITH)
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.upload }))

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: copy.upload })).not.toBeInTheDocument(),
    )
  })

  test('shows the API’s own words about a refused image', async () => {
    // A 422 is the server's wording about the file. It is more use than ours would be, because it
    // says which of the four things was wrong with it.
    const user = userEvent.setup()
    postAvatar.mockRejectedValue(new ApiError(422, 'That image is a BMP file. Upload a JPEG.'))
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.upload }))

    expect(await screen.findByRole('alert')).toHaveTextContent('That image is a BMP file.')
  })

  test('words anything else itself, because it is not about the file', async () => {
    const user = userEvent.setup()
    postAvatar.mockRejectedValue(new ApiError(503, 'Service unavailable'))
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.upload }))

    expect(await screen.findByRole('alert')).toHaveTextContent(copy.failed)
  })

  test('leaves the cropper open after a failure, so the crop is not lost', async () => {
    const user = userEvent.setup()
    postAvatar.mockRejectedValue(new ApiError(503, 'nope'))
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.upload }))

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: copy.upload })).toBeInTheDocument()
  })
})

describe('removing', () => {
  test('takes the photograph down and reports the new record', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    deleteAvatar.mockResolvedValue(WITHOUT)
    render(<AvatarCard profile={WITH} onChanged={onChanged} />)

    await user.click(screen.getByRole('button', { name: copy.remove }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(WITHOUT))
  })

  test('asks nothing first', async () => {
    // No confirmation dialog: the action is one click to undo, and a `confirm()` would block the
    // whole page on a modal the club cannot style.
    const user = userEvent.setup()
    deleteAvatar.mockResolvedValue(WITHOUT)
    render(<AvatarCard profile={WITH} onChanged={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: copy.remove }))

    expect(deleteAvatar).toHaveBeenCalledOnce()
  })

  test('says so when it could not', async () => {
    const user = userEvent.setup()
    deleteAvatar.mockRejectedValue(new Error('offline'))
    render(<AvatarCard profile={WITH} onChanged={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: copy.remove }))

    expect(await screen.findByRole('alert')).toHaveTextContent(copy.failed)
  })
})

describe('the object URL', () => {
  /*
   * A `blob:` URL is a reference the browser holds until told otherwise, so an unrevoked one is the
   * whole chosen file kept alive. Invisible until a member has tried four photographs, which is why
   * each way out of the cropper gets its own test.
   */

  test('is revoked when the cropper is cancelled', async () => {
    const user = userEvent.setup()
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.cancel }))

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:chosen'))
  })

  test('is revoked after a successful upload', async () => {
    const user = userEvent.setup()
    postAvatar.mockResolvedValue(WITH)
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await user.click(await screen.findByRole('button', { name: copy.upload }))

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:chosen'))
  })

  test('is revoked when the card goes away with a file still chosen', async () => {
    const { unmount } = render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('face.jpg', 'image/jpeg', 1000))
    await screen.findByRole('button', { name: copy.upload })

    unmount()

    expect(revokeObjectURL).toHaveBeenCalledWith('blob:chosen')
  })

  test('is not created at all for a file that was refused', async () => {
    render(<AvatarCard profile={WITHOUT} onChanged={vi.fn()} />)

    await choose(file('huge.jpg', 'image/jpeg', 9 * 1024 * 1024))

    await screen.findByRole('alert')
    expect(createObjectURL).not.toHaveBeenCalled()
  })
})

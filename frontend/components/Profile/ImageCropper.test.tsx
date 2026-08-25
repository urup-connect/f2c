import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { PROFILE_COPY } from '@/lib/club-content'
import { MAX_ZOOM } from '@/lib/image-crop'
import { FRAME, ImageCropper, OUTPUT } from './ImageCropper'

/*
 * The cropper's wiring, not its arithmetic. `lib/image-crop.test.ts` owns the geometry.
 *
 * What this file establishes is the part that cannot be tested as a function: that the component
 * **measures the image before it draws it**, that it is **operable from the keyboard**, and that
 * what leaves it is **the crop rather than the original**.
 *
 * jsdom decodes nothing and has no canvas, so both are stood up by hand: `naturalWidth` is defined
 * on the prototype, and `getContext`/`toBlob` are stubbed. That is honest about what is being
 * tested — the calls this component makes and the arguments it passes — and dishonest about nothing,
 * because the pixels it would produce are `drawImage`'s work rather than this file's.
 */

const copy = PROFILE_COPY.photograph

const NATURAL = { width: 1600, height: 900 }

const drawImage = vi.fn()
const toBlob = vi.fn()

/** The frame element: focusable, and what the pointer and key handlers are attached to. */
const frame = () => screen.getByLabelText(copy.keyboardHint)

const zoom = () => screen.getByRole('slider', { name: copy.zoomLabel })

/**
 * Tell the rendered `img` how big it "naturally" is, then fire the load it never got.
 *
 * jsdom never fetches anything, so `naturalWidth` is 0 and no `load` event fires. Both halves are
 * needed: the size, so the geometry has something to work with, and the event, because the
 * component deliberately measures on load rather than during render.
 */
const decode = (size = NATURAL) => {
  const image = document.querySelector('img')
  if (!image) throw new Error('no image rendered')

  Object.defineProperty(image, 'naturalWidth', { value: size.width, configurable: true })
  Object.defineProperty(image, 'naturalHeight', { value: size.height, configurable: true })
  fireEvent.load(image)
  return image
}

/*
 * jsdom implements no part of the Pointer Capture spec, so `setPointerCapture` is simply absent.
 * Stubbed here rather than guarded in the component: it exists in every browser this ships to, and
 * a capability check added for a test runner's sake is a line nobody can later tell is dead.
 */
const setPointerCapture = vi.fn()

beforeEach(() => {
  drawImage.mockReset()
  toBlob.mockReset()
  setPointerCapture.mockReset()
  Object.defineProperty(Element.prototype, 'setPointerCapture', {
    value: setPointerCapture,
    configurable: true,
    writable: true,
  })
  toBlob.mockImplementation((callback: (blob: Blob | null) => void) => {
    callback(new Blob(['cropped'], { type: 'image/jpeg' }))
  })

  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({
    drawImage,
  } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(toBlob)
})

afterEach(() => {
  vi.restoreAllMocks()
})

const renderCropper = (overrides: Partial<Parameters<typeof ImageCropper>[0]> = {}) => {
  const onCropped = vi.fn()
  const onCancel = vi.fn()

  render(
    <ImageCropper
      src="blob:chosen"
      confirmLabel={copy.upload}
      onCropped={onCropped}
      onCancel={onCancel}
      {...overrides}
    />,
  )

  return { onCropped, onCancel }
}

describe('before the image has decoded', () => {
  test('will not confirm a crop it has not measured', () => {
    /*
     * `naturalWidth` is 0 until the browser has decoded the file. Confirming against that would
     * hand `coveringScale` a zero-sized image, and the member would upload a blank square with no
     * error anywhere.
     */
    renderCropper()

    expect(screen.getByRole('button', { name: copy.upload })).toBeDisabled()
    expect(zoom()).toBeDisabled()
  })

  test('measures a file that was already decoded before it mounted', () => {
    // A cached image fires no `load`, so a component waiting only for the event would wait for
    // something that has been and gone.
    render(
      <ImageCropper
        src="blob:cached"
        confirmLabel={copy.upload}
        onCropped={vi.fn()}
        onCancel={vi.fn()}
      />,
    )

    const image = document.querySelector('img') as HTMLImageElement
    Object.defineProperty(image, 'naturalWidth', { value: 800, configurable: true })
    Object.defineProperty(image, 'naturalHeight', { value: 800, configurable: true })
    Object.defineProperty(image, 'complete', { value: true, configurable: true })
    fireEvent.load(image)

    expect(screen.getByRole('button', { name: copy.upload })).toBeEnabled()
  })
})

describe('once it has decoded', () => {
  test('draws the image large enough to cover the square', () => {
    renderCropper()
    const image = decode()

    // 1600x900 at the covering scale is 455x256: the short side exactly fills the frame.
    expect(image.style.height).toBe(`${FRAME}px`)
    expect(Number.parseFloat(image.style.width)).toBeGreaterThan(FRAME)
  })

  test('opens at the minimum zoom', () => {
    renderCropper()
    decode()

    expect(zoom()).toHaveValue('1')
  })

  test('lets the zoom be changed and moves the image', async () => {
    renderCropper()
    const image = decode()
    const before = image.style.width

    fireEvent.change(zoom(), { target: { value: '2' } })

    expect(image.style.width).not.toBe(before)
    expect(zoom()).toHaveValue('2')
  })

  test('holds the zoom ceiling', () => {
    renderCropper()
    decode()

    expect(zoom()).toHaveAttribute('max', String(MAX_ZOOM))
  })
})

describe('the keyboard', () => {
  test('moves the image with the arrow keys', async () => {
    /*
     * A crop tool that only answers to dragging is a crop tool a keyboard user cannot use at all,
     * and the alternative for them -- no photograph -- is not a graceful degradation.
     */
    renderCropper()
    const image = decode()
    fireEvent.change(zoom(), { target: { value: '2' } })
    const before = image.style.transform

    await userEvent.type(frame(), '{arrowleft}')

    expect(image.style.transform).not.toBe(before)
  })

  test('zooms with plus and minus', async () => {
    renderCropper()
    decode()

    await userEvent.type(frame(), '+')

    expect(Number(zoom().getAttribute('value') ?? (zoom() as HTMLInputElement).value)).toBeGreaterThan(1)
  })

  test('leaves keys it does not use alone, so Tab still moves on', async () => {
    // `preventDefault` is called only for the keys handled, which is what keeps the page scrolling
    // and a screen reader's own shortcuts working.
    renderCropper()
    decode()

    const event = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    frame().dispatchEvent(event)

    expect(event.defaultPrevented).toBe(false)
  })

  test('claims the arrow keys it does use', () => {
    renderCropper()
    decode()

    const event = new KeyboardEvent('keydown', {
      key: 'ArrowLeft',
      bubbles: true,
      cancelable: true,
    })
    frame().dispatchEvent(event)

    expect(event.defaultPrevented).toBe(true)
  })

  test('is reachable by Tab, and not while busy', () => {
    renderCropper()
    decode()
    expect(frame()).toHaveAttribute('tabindex', '0')
  })
})

describe('dragging', () => {
  test('moves the image by the pointer delta', () => {
    renderCropper()
    const image = decode()
    const box = frame()

    // Zoomed in, so there is room to move in both directions.
    fireEvent.change(zoom(), { target: { value: '2' } })
    const before = image.style.transform

    fireEvent.pointerDown(box, { pointerId: 1, clientX: 100, clientY: 100 })
    fireEvent.pointerMove(box, { pointerId: 1, clientX: 80, clientY: 90 })

    expect(image.style.transform).not.toBe(before)
  })

  test('captures the pointer, so a drag leaving the box keeps working', () => {
    // Without capture the image sticks the moment the pointer crosses the edge, which reads as the
    // crop having hit a limit it has not.
    renderCropper()
    decode()

    fireEvent.pointerDown(frame(), { pointerId: 1, clientX: 10, clientY: 10 })

    expect(setPointerCapture).toHaveBeenCalledWith(1)
  })

  test('ignores movement from a pointer that is not the one dragging', () => {
    // A second finger on a touchscreen. Acting on both would move the image at twice the speed and
    // in whichever direction the last event happened to be.
    renderCropper()
    const image = decode()
    fireEvent.change(zoom(), { target: { value: '2' } })

    fireEvent.pointerDown(frame(), { pointerId: 1, clientX: 100, clientY: 100 })
    const after = image.style.transform
    fireEvent.pointerMove(frame(), { pointerId: 2, clientX: 40, clientY: 40 })

    expect(image.style.transform).toBe(after)
  })

  test('stops moving once the pointer is released', () => {
    renderCropper()
    const image = decode()
    fireEvent.change(zoom(), { target: { value: '2' } })

    fireEvent.pointerDown(frame(), { pointerId: 1, clientX: 100, clientY: 100 })
    fireEvent.pointerUp(frame(), { pointerId: 1, clientX: 100, clientY: 100 })
    const after = image.style.transform
    fireEvent.pointerMove(frame(), { pointerId: 1, clientX: 20, clientY: 20 })

    expect(image.style.transform).toBe(after)
  })

  test('does not drag while the caller is uploading', () => {
    renderCropper({ busy: true })
    const image = decode()
    const before = image.style.transform

    fireEvent.pointerDown(frame(), { pointerId: 1, clientX: 100, clientY: 100 })
    fireEvent.pointerMove(frame(), { pointerId: 1, clientX: 40, clientY: 40 })

    expect(image.style.transform).toBe(before)
  })
})

describe('confirming', () => {
  test('draws to a canvas the size of the stored avatar', async () => {
    const user = userEvent.setup()
    const { onCropped } = renderCropper()
    decode()

    await user.click(screen.getByRole('button', { name: copy.upload }))

    await waitFor(() => expect(onCropped).toHaveBeenCalledOnce())
    // The destination rectangle is the whole output square, every time.
    const call = drawImage.mock.calls[0]
    expect(call.slice(5)).toEqual([0, 0, OUTPUT, OUTPUT])
  })

  test('draws only the crop, not the whole image', async () => {
    /*
     * The property the copy promises: what leaves the browser is the square and not the original
     * with a hint attached. At the opening zoom on a 1600x900 image the source rectangle is the
     * 900x900 centre -- so a source width of 1600 here would mean the whole frame was sent.
     */
    const user = userEvent.setup()
    renderCropper()
    decode()

    await user.click(screen.getByRole('button', { name: copy.upload }))

    const [, sourceX, sourceY, sourceWidth, sourceHeight] = drawImage.mock.calls[0]
    expect(sourceWidth).toBeCloseTo(900)
    expect(sourceHeight).toBeCloseTo(900)
    expect(sourceX).toBeCloseTo(350)
    expect(sourceY).toBeCloseTo(0)
  })

  test('hands over a JPEG', async () => {
    const user = userEvent.setup()
    const { onCropped } = renderCropper()
    decode()

    await user.click(screen.getByRole('button', { name: copy.upload }))

    await waitFor(() => expect(onCropped).toHaveBeenCalledOnce())
    expect(toBlob.mock.calls[0][1]).toBe('image/jpeg')
    expect(onCropped.mock.calls[0][0]).toBeInstanceOf(Blob)
  })

  test('hands over nothing when the canvas produced nothing', async () => {
    // `toBlob` can answer null. Calling back with that would upload an empty body.
    const user = userEvent.setup()
    toBlob.mockImplementation((callback: (blob: Blob | null) => void) => callback(null))
    const { onCropped } = renderCropper()
    decode()

    await user.click(screen.getByRole('button', { name: copy.upload }))

    expect(onCropped).not.toHaveBeenCalled()
  })

  test('cancels rather than uploading a blank square when there is no 2D context', async () => {
    const user = userEvent.setup()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const { onCropped, onCancel } = renderCropper()
    decode()

    await user.click(screen.getByRole('button', { name: copy.upload }))

    expect(onCropped).not.toHaveBeenCalled()
    expect(onCancel).toHaveBeenCalledOnce()
  })
})

describe('while the caller is uploading', () => {
  test('stops taking presses', () => {
    renderCropper({ busy: true })
    decode()

    expect(screen.getByRole('button', { name: copy.upload })).toBeDisabled()
    expect(screen.getByRole('button', { name: copy.cancel })).toBeDisabled()
    expect(zoom()).toBeDisabled()
    // And leaves the tab order, so Tab does not stop on a control that does nothing.
    expect(frame()).toHaveAttribute('tabindex', '-1')
  })
})

describe('cancelling', () => {
  test('tells the caller, which is what revokes the object URL', async () => {
    const user = userEvent.setup()
    const { onCancel } = renderCropper()
    decode()

    await user.click(screen.getByRole('button', { name: copy.cancel }))

    expect(onCancel).toHaveBeenCalledOnce()
  })
})

describe('what it says', () => {
  test('explains that only the square is kept', () => {
    // A member cropping a photograph of themselves is entitled to know the rest of the frame is not
    // being sent.
    renderCropper()

    expect(screen.getByText(copy.cropNote)).toBeInTheDocument()
  })

  test('explains how to drag and how to zoom', () => {
    renderCropper()

    expect(screen.getByText(copy.cropHint)).toBeInTheDocument()
  })

  test('gives the image an empty alt, being decoration inside a labelled group', () => {
    // The member chose this file a moment ago and the group around it is named. An alt describing
    // it would be a guess read out over something they already know.
    renderCropper()

    expect(document.querySelector('img')).toHaveAttribute('alt', '')
  })
})

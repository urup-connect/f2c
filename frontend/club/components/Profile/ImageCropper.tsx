'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

import { PROFILE_COPY } from '@/lib/club-content'
import {
  MAX_ZOOM,
  NUDGE_STEP,
  ZOOM_STEP,
  drawnSize,
  initialCrop,
  pannedCrop,
  sourceRect,
  zoomedCrop,
  type CropState,
  type ImageSize,
} from '@/lib/image-crop'

/**
 * The side of the square the cropper draws, in CSS pixels.
 *
 * Fixed rather than measured, and the reason is `lib/image-crop.ts`: every offset in a `CropState`
 * is in these units, so a frame that changed size would silently reinterpret a crop the member had
 * already set. 256 fits inside a 320-pixel viewport with the card's padding still on it, which is
 * the narrowest phone worth designing for.
 */
export const FRAME = 256

/**
 * The side of the square that is uploaded, in image pixels.
 *
 * The same number as `AVATAR_SIZE` in `app/core/accounts/avatars.py`, and it does not have to be — the
 * API re-encodes to its own size whatever arrives. Matching it means the upload is the size that
 * will be stored, so nothing is sent that the server then throws away, and nothing is upscaled
 * twice.
 */
export const OUTPUT = 512

/** JPEG quality for the uploaded crop. Higher than the server's, so its re-encode is the only loss. */
const OUTPUT_QUALITY = 0.92

type ImageCropperProps = {
  /** An object URL for the chosen file. The caller owns it and revokes it. */
  src: string
  /** Called with the cropped square. Never called with anything else. */
  onCropped: (blob: Blob) => void
  onCancel: () => void
  /** True while the caller is uploading, so the buttons stop taking presses. */
  busy?: boolean
  confirmLabel: string
}

/**
 * Choose which square of an image is kept.
 *
 * A client component because it is nothing but pointer events and a canvas, neither of which exists
 * on the server.
 *
 * Four things here are decisions rather than implementation.
 *
 * **The geometry is not in this file.** Every pan, zoom and clamp goes through `lib/image-crop.ts`,
 * which is pure and tested. What is left here is listening — and that split is what stops the one
 * invariant that matters (the square is always inside the image) from being re-derived inside an
 * event handler where nothing can check it.
 *
 * **It is operable without a pointer.** The image is focusable, the arrow keys move it and plus and
 * minus zoom, and the zoom is a real `range` input rather than two buttons. A crop tool that only
 * answers to dragging is a crop tool a keyboard user cannot use at all, and the alternative — no
 * photograph — is not a graceful degradation.
 *
 * **Nothing but the square is ever uploaded.** The canvas is drawn from `sourceRect`, so the bytes
 * that leave the browser are the crop and not the original with a hint attached. The copy says so,
 * because a member cropping a photograph of themselves is entitled to know the rest of the frame is
 * not being sent.
 *
 * **`img` rather than `next/image`.** Two reasons, and both are about what the optimiser would do:
 * this src is an object URL for a local file, which has nothing to optimise, and the same component
 * shape is used for the saved avatar, whose URL is session-authed — the optimiser fetches from the
 * server, where there is no session, and would get a 401.
 */
export const ImageCropper = ({
  src,
  onCropped,
  onCancel,
  busy = false,
  confirmLabel,
}: ImageCropperProps) => {
  const copy = PROFILE_COPY.photograph

  const [size, setSize] = useState<ImageSize | null>(null)
  const [crop, setCrop] = useState<CropState>({ x: 0, y: 0, scale: 1 })

  const image = useRef<HTMLImageElement | null>(null)
  /** The pointer that is currently dragging, and where it last was. Null when nothing is. */
  const drag = useRef<{ id: number; x: number; y: number } | null>(null)

  /*
   * The natural size is read when the browser has decoded the file, which is an event rather than a
   * render: `naturalWidth` is 0 until then. Reading it during render would give a zero-sized image
   * and `coveringScale` would answer 1, which draws a one-pixel picture with no error anywhere.
   */
  const measure = useCallback(() => {
    const element = image.current
    if (!element || element.naturalWidth === 0) return

    const natural = { width: element.naturalWidth, height: element.naturalHeight }
    setSize(natural)
    setCrop(initialCrop(natural, FRAME))
  }, [])

  useEffect(() => {
    // Covers the cached case: an image already decoded fires no `load`, so a component mounting
    // against a complete element would wait for an event that has been and gone.
    if (image.current?.complete) measure()
  }, [measure, src])

  const drawn = size ? drawnSize(size, FRAME, crop.scale) : { width: FRAME, height: FRAME }

  const move = (dx: number, dy: number) => {
    if (!size) return
    setCrop((current) => pannedCrop(current, size, FRAME, dx, dy))
  }

  const zoomTo = (scale: number) => {
    if (!size) return
    setCrop((current) => zoomedCrop(current, size, FRAME, scale))
  }

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!size || busy) return
    // Capture, so a drag that leaves the box keeps being reported. Without it the image sticks the
    // moment the pointer crosses the edge, which reads as the crop having hit a limit it has not.
    event.currentTarget.setPointerCapture(event.pointerId)
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
  }

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const active = drag.current
    if (!active || active.id !== event.pointerId) return

    move(event.clientX - active.x, event.clientY - active.y)
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
  }

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (drag.current?.id !== event.pointerId) return
    drag.current = null
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!size || busy) return

    const step = event.shiftKey ? NUDGE_STEP * 3 : NUDGE_STEP

    switch (event.key) {
      case 'ArrowLeft':
        move(-step, 0)
        break
      case 'ArrowRight':
        move(step, 0)
        break
      case 'ArrowUp':
        move(0, -step)
        break
      case 'ArrowDown':
        move(0, step)
        break
      case '+':
      case '=':
        zoomTo(crop.scale + ZOOM_STEP * (MAX_ZOOM - 1))
        break
      case '-':
      case '_':
        zoomTo(crop.scale - ZOOM_STEP * (MAX_ZOOM - 1))
        break
      default:
        // Anything else is left alone, so Tab still moves on and a screen reader's own keys work.
        return
    }

    // Only for the keys handled above, so the page still scrolls when the cropper is not using the
    // arrow keys for anything.
    event.preventDefault()
  }

  /**
   * Draw the crop to a canvas and hand over the bytes.
   *
   * `toBlob` rather than `toDataURL`: a data URL is base64, so it is a third larger and it is a
   * string the whole of which has to exist in memory before anything can be sent.
   */
  const confirm = () => {
    const element = image.current
    if (!element || !size) return

    const canvas = document.createElement('canvas')
    canvas.width = OUTPUT
    canvas.height = OUTPUT

    const context = canvas.getContext('2d')
    if (!context) {
      // No 2D context at all. Rather than fail silently, hand back nothing and let the caller keep
      // its own error on screen -- there is no crop to send and pretending otherwise would upload
      // a blank square.
      onCancel()
      return
    }

    const rect = sourceRect(crop, size, FRAME)
    context.drawImage(
      element,
      rect.x,
      rect.y,
      rect.width,
      rect.height,
      0,
      0,
      OUTPUT,
      OUTPUT,
    )

    canvas.toBlob(
      (blob) => {
        if (blob) onCropped(blob)
      },
      'image/jpeg',
      OUTPUT_QUALITY,
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h3 className="font-sans text-base font-medium text-foreground">{copy.cropHeading}</h3>
        <p className="mt-1 font-sans text-sm leading-relaxed text-muted-foreground">
          {copy.cropHint}
        </p>
      </div>

      {/*
        * `role="application"` is deliberately *not* used. This is a group with a focusable control
        * in it, and claiming an application role would suppress the screen reader's own navigation
        * for the sake of arrow keys that are an addition here rather than the only way in.
        */}
      <div
        role="group"
        aria-label={copy.cropHeading}
        className="flex flex-col items-center gap-3"
      >
        <div
          tabIndex={busy ? -1 : 0}
          aria-label={copy.keyboardHint}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          onKeyDown={handleKeyDown}
          style={{ width: FRAME, height: FRAME }}
          /*
           * `touch-none` matters more than it looks: without it a drag on a phone scrolls the page
           * instead of moving the image, and the cropper appears not to respond to touch at all.
           * `overflow-hidden` is what makes the box the crop -- everything outside it is clipped,
           * which is the same rectangle `sourceRect` computes.
           */
          className="relative touch-none overflow-hidden rounded-card border-2 border-border bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- an object URL has nothing for
              next/image to optimise, and the optimiser is a server fetch with no session. */}
          <img
            ref={image}
            src={src}
            alt=""
            onLoad={measure}
            draggable={false}
            style={{
              width: drawn.width,
              height: drawn.height,
              transform: `translate(${crop.x}px, ${crop.y}px)`,
            }}
            className="absolute left-0 top-0 max-w-none select-none"
          />
        </div>

        <label className="flex w-full max-w-xs items-center gap-3">
          <span className="font-sans text-sm text-muted-foreground">{copy.zoomLabel}</span>
          <input
            type="range"
            min={1}
            max={MAX_ZOOM}
            step={0.01}
            value={crop.scale}
            disabled={busy || size === null}
            onChange={(event) => zoomTo(Number(event.target.value))}
            className="flex-1 accent-forest-green"
          />
        </label>

        <p className="font-sans text-sm text-muted-foreground">{copy.cropNote}</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={confirm}
          disabled={busy || size === null}
          className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-transparent bg-primary px-8 font-sans text-base font-medium text-primary-foreground transition-colors hover:bg-forest-green-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
        >
          {confirmLabel}
        </button>

        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="inline-flex h-12 items-center justify-center rounded-pill border-2 border-border bg-surface px-8 font-sans text-base font-medium text-foreground transition-colors hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green disabled:opacity-60"
        >
          {copy.cancel}
        </button>
      </div>
    </div>
  )
}

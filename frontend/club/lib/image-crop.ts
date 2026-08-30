/**
 * The geometry behind the cropper, with no canvas and no DOM in it.
 *
 * A crop UI is two things wearing one coat: a pile of pointer arithmetic, and a rule about what a
 * pan and a zoom are allowed to produce. The second is the part that goes wrong, and it goes wrong
 * silently — a member drags past the edge, the square fills with blank, and what uploads is a
 * photograph of a corner. So the rule lives here, as functions over numbers, and
 * `ImageCropper.tsx` is left holding only the events.
 *
 * **One invariant, and everything here exists to hold it: the crop square is always entirely
 * inside the image.** Not clamped after the fact when it looks wrong — clamped on every change, so
 * there is no state in which it is not true. That is what makes "what you see is what is kept" a
 * fact rather than a hope.
 *
 * The model is deliberately the smaller of the two obvious ones. Rather than track the square's
 * position over the image, it tracks the *image's* offset behind a fixed square, which is what a
 * pointer event naturally gives: a delta in screen pixels. `scale` is the multiplier applied to the
 * image, floored at whatever makes it exactly cover the square — so scale 1 is "as zoomed out as
 * this image can go", and no zoom-out can uncover a corner.
 *
 * Nothing here is React-aware and nothing mutates. The component holds one `CropState` and replaces
 * it; every function below takes one and returns the next.
 */

/** How far in the cropper will let a member zoom, as a multiple of the covering scale. */
export const MAX_ZOOM = 4

/** How much one press of an arrow key moves the image, in cropper pixels. */
export const NUDGE_STEP = 12

/** How much one press of plus or minus changes the zoom, as a fraction of the range. */
export const ZOOM_STEP = 0.08

/** The natural dimensions of the image being cropped. */
export type ImageSize = {
  readonly width: number
  readonly height: number
}

/**
 * Where the image sits behind the square, and how big it is drawn.
 *
 * `x` and `y` are the offset of the image's top-left corner from the square's, in the square's own
 * pixels, and both are always negative or zero — a positive value would mean the image starts
 * inside the square and has therefore left a gap. `scale` is relative to the covering scale, so it
 * is never below 1.
 */
export type CropState = {
  readonly x: number
  readonly y: number
  readonly scale: number
}

/**
 * The scale at which this image exactly covers a square of `frame` pixels.
 *
 * The larger of the two ratios, not the smaller: the smaller would fit the whole image inside the
 * square and leave two bars, which for an avatar is worse than losing the edges. This is the floor
 * every other function measures from, which is why `scale` is a multiple of it rather than an
 * absolute size — a member zooming out lands exactly on "covered" and cannot go past it.
 *
 * Guards against a zero dimension by answering 1. A zero-sized image cannot be cropped, and
 * returning `Infinity` here would put `NaN` into every later calculation and render an empty box
 * with no error anywhere.
 */
export const coveringScale = (image: ImageSize, frame: number): number => {
  if (image.width <= 0 || image.height <= 0 || frame <= 0) return 1

  return Math.max(frame / image.width, frame / image.height)
}

/** The image's drawn size at a given state. */
export const drawnSize = (image: ImageSize, frame: number, scale: number): ImageSize => {
  const base = coveringScale(image, frame)

  return {
    width: image.width * base * scale,
    height: image.height * base * scale,
  }
}

const clamp = (value: number, low: number, high: number) =>
  Math.min(high, Math.max(low, value))

/**
 * The nearest state to the one asked for that still satisfies the invariant.
 *
 * Every change goes through this — a drag, a zoom, a keyboard nudge, and the initial state. That is
 * the whole reason the invariant holds: there is no path that sets `x`, `y` or `scale` without
 * passing here, so no intermediate state can be invalid even for a frame.
 *
 * The order matters. `scale` is clamped first, because the bounds on `x` and `y` depend on how big
 * the image is drawn — clamping the offsets against the old scale and then changing it is exactly
 * how a zoom-out ends up showing a gap.
 */
export const clampCrop = (state: CropState, image: ImageSize, frame: number): CropState => {
  const scale = clamp(state.scale, 1, MAX_ZOOM)
  const drawn = drawnSize(image, frame, scale)

  /*
   * `Math.min(0, ...)` on the low bound, not just the subtraction. At scale exactly 1 one dimension
   * is precisely `frame` and the other is larger; floating-point arithmetic can make the equal one
   * come out a hair under, which would give a low bound above the high one and let `clamp` return
   * the wrong end. Pinning it at zero keeps a square image centred rather than jittering.
   */
  return {
    scale,
    x: clamp(state.x, Math.min(0, frame - drawn.width), 0),
    y: clamp(state.y, Math.min(0, frame - drawn.height), 0),
  }
}

/**
 * Where an image starts: zoomed out as far as it goes, and centred on its long axis.
 *
 * Centred rather than at a corner because the subject of a photograph is very nearly always nearer
 * the middle than the edge, and a cropper that opens on somebody's shoulder is a cropper every
 * member has to fix before they can use it.
 */
export const initialCrop = (image: ImageSize, frame: number): CropState => {
  const drawn = drawnSize(image, frame, 1)

  return clampCrop(
    { x: (frame - drawn.width) / 2, y: (frame - drawn.height) / 2, scale: 1 },
    image,
    frame,
  )
}

/** The state after dragging by `dx`, `dy` cropper pixels. */
export const pannedCrop = (
  state: CropState,
  image: ImageSize,
  frame: number,
  dx: number,
  dy: number,
): CropState => clampCrop({ ...state, x: state.x + dx, y: state.y + dy }, image, frame)

/**
 * The state after zooming to `scale`, keeping the centre of the square where it was.
 *
 * The correction is the point of this function. Changing `scale` alone grows the image from its
 * top-left corner, so the square appears to slide towards whatever was in the bottom-right — which
 * is why a naive zoom feels like the image is running away. Holding the square's centre fixed
 * instead is what makes a slider feel like a magnifier.
 *
 * Derived rather than remembered: the centre is recomputed from the incoming state each time, so a
 * clamp that moved the image between two zooms is accounted for instead of accumulating.
 */
export const zoomedCrop = (
  state: CropState,
  image: ImageSize,
  frame: number,
  scale: number,
): CropState => {
  const next = clamp(scale, 1, MAX_ZOOM)
  const ratio = next / state.scale

  const centre = frame / 2

  return clampCrop(
    {
      scale: next,
      x: centre - (centre - state.x) * ratio,
      y: centre - (centre - state.y) * ratio,
    },
    image,
    frame,
  )
}

/** The rectangle of the *source* image that the square is showing. */
export type SourceRect = {
  readonly x: number
  readonly y: number
  readonly width: number
  readonly height: number
}

/**
 * The crop, in the source image's own pixels, ready to hand to `drawImage`.
 *
 * This is the translation the whole module exists to make: the state above is in cropper pixels,
 * which depend on how large the box happens to be rendered, and a crop expressed in those is a crop
 * that changes when the window is resized. Converting through `coveringScale * scale` gives a
 * rectangle that means the same thing at any box size.
 *
 * The result is clamped to the image's own bounds as well. The invariant should make that
 * unnecessary, and it is kept because `drawImage` with a source rectangle even slightly outside the
 * image samples transparent black along that edge — a one-pixel dark line down the side of an
 * avatar, which is the sort of defect that gets noticed and never diagnosed.
 */
export const sourceRect = (
  state: CropState,
  image: ImageSize,
  frame: number,
): SourceRect => {
  const factor = coveringScale(image, frame) * state.scale

  if (factor <= 0) return { x: 0, y: 0, width: image.width, height: image.height }

  const size = frame / factor
  const width = Math.min(size, image.width)
  const height = Math.min(size, image.height)

  return {
    x: clamp(-state.x / factor, 0, Math.max(0, image.width - width)),
    y: clamp(-state.y / factor, 0, Math.max(0, image.height - height)),
    width,
    height,
  }
}

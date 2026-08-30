import { describe, expect, test } from 'vitest'
import {
  MAX_ZOOM,
  clampCrop,
  coveringScale,
  drawnSize,
  initialCrop,
  pannedCrop,
  sourceRect,
  zoomedCrop,
  type CropState,
  type ImageSize,
} from './image-crop'

/*
 * The cropper's geometry.
 *
 * Almost every test here is the same assertion wearing a different hat: **the square is inside the
 * image**. That is the invariant the whole module exists to hold, and it is the one that fails
 * silently — a member drags too far, the square fills with blank, and what uploads is a photograph
 * of a corner with no error anywhere.
 *
 * So rather than test each function's arithmetic, the tests drive each function to its limit and
 * then assert the invariant still holds. `covers` below is that assertion, written once.
 */

const LANDSCAPE: ImageSize = { width: 1600, height: 900 }
const PORTRAIT: ImageSize = { width: 900, height: 1600 }
const SQUARE: ImageSize = { width: 800, height: 800 }
const FRAME = 256

/**
 * The invariant: the image, drawn at this state, covers the whole frame.
 *
 * A tolerance of a thousandth of a pixel, because the bounds are computed by subtraction and a
 * value clamped to exactly its limit can land a floating-point hair beyond it. A gap that small is
 * not a gap; a gap of one pixel is.
 */
const covers = (state: CropState, image: ImageSize, frame = FRAME) => {
  const drawn = drawnSize(image, frame, state.scale)
  const epsilon = 0.001

  expect(state.x, 'left edge').toBeLessThanOrEqual(epsilon)
  expect(state.y, 'top edge').toBeLessThanOrEqual(epsilon)
  expect(state.x + drawn.width, 'right edge').toBeGreaterThanOrEqual(frame - epsilon)
  expect(state.y + drawn.height, 'bottom edge').toBeGreaterThanOrEqual(frame - epsilon)
}

describe('coveringScale', () => {
  test('takes the larger ratio, so the image covers rather than fits', () => {
    // The smaller ratio would fit the whole image inside the square and leave two bars, which for
    // an avatar is worse than losing the edges of the frame.
    expect(coveringScale(LANDSCAPE, FRAME)).toBeCloseTo(FRAME / 900)
    expect(coveringScale(PORTRAIT, FRAME)).toBeCloseTo(FRAME / 900)
  })

  test('is exactly the frame over the side for a square image', () => {
    expect(coveringScale(SQUARE, FRAME)).toBeCloseTo(FRAME / 800)
  })

  test('answers 1 rather than Infinity for an image with no size', () => {
    // A zero dimension cannot be cropped. Answering Infinity would put NaN into every later
    // calculation and render an empty box with no error anywhere.
    expect(coveringScale({ width: 0, height: 100 }, FRAME)).toBe(1)
    expect(coveringScale({ width: 100, height: 0 }, FRAME)).toBe(1)
    expect(coveringScale(LANDSCAPE, 0)).toBe(1)
  })
})

describe('initialCrop', () => {
  test('opens zoomed out as far as it goes', () => {
    expect(initialCrop(LANDSCAPE, FRAME).scale).toBe(1)
  })

  test('opens centred rather than in a corner', () => {
    // The subject of a photograph is nearly always nearer the middle than the edge. A cropper that
    // opens on somebody's shoulder is one every member has to fix before they can use it.
    const state = initialCrop(LANDSCAPE, FRAME)
    const drawn = drawnSize(LANDSCAPE, FRAME, 1)

    expect(state.x).toBeCloseTo((FRAME - drawn.width) / 2)
    expect(state.y).toBeCloseTo(0)
  })

  test('covers the frame for every shape of image', () => {
    for (const image of [LANDSCAPE, PORTRAIT, SQUARE]) {
      covers(initialCrop(image, FRAME), image)
    }
  })

  test('leaves a square image exactly filling the frame with no jitter', () => {
    // The floating-point case `clampCrop` pins at zero: at scale 1 a square image is precisely
    // `frame` on both sides, and a low bound computed a hair above zero would push it off centre.
    const state = initialCrop(SQUARE, FRAME)

    expect(state.x).toBe(0)
    expect(state.y).toBe(0)
  })
})

describe('clampCrop', () => {
  test('refuses a scale below the covering one', () => {
    // Zooming out past `covering` is the one move that can uncover a corner, so 1 is the floor and
    // it is not negotiable.
    expect(clampCrop({ x: 0, y: 0, scale: 0.2 }, LANDSCAPE, FRAME).scale).toBe(1)
  })

  test('refuses a scale above the ceiling', () => {
    expect(clampCrop({ x: 0, y: 0, scale: 99 }, LANDSCAPE, FRAME).scale).toBe(MAX_ZOOM)
  })

  test('refuses a positive offset, which would leave a gap', () => {
    const state = clampCrop({ x: 50, y: 50, scale: 1 }, LANDSCAPE, FRAME)

    expect(state.x).toBeLessThanOrEqual(0)
    expect(state.y).toBeLessThanOrEqual(0)
  })

  test('clamps the scale before the offsets, not after', () => {
    /*
     * The ordering bug this exists to catch. Offsets valid at scale 3 are far out of bounds at
     * scale 1, so clamping them against the old scale and *then* changing it leaves a state that
     * shows blank. Asked for a large offset and a zoom-out in one go, the result must still cover.
     */
    const zoomedIn = zoomedCrop(initialCrop(LANDSCAPE, FRAME), LANDSCAPE, FRAME, 3)
    const panned = pannedCrop(zoomedIn, LANDSCAPE, FRAME, -400, -400)

    covers(clampCrop({ ...panned, scale: 1 }, LANDSCAPE, FRAME), LANDSCAPE)
  })

  test('is idempotent', () => {
    const once = clampCrop({ x: -9999, y: 42, scale: 7 }, PORTRAIT, FRAME)

    expect(clampCrop(once, PORTRAIT, FRAME)).toEqual(once)
  })
})

describe('pannedCrop', () => {
  test('moves by the delta when there is room', () => {
    const start = zoomedCrop(initialCrop(SQUARE, FRAME), SQUARE, FRAME, 2)
    const moved = pannedCrop(start, SQUARE, FRAME, -10, -10)

    expect(moved.x).toBeCloseTo(start.x - 10)
    expect(moved.y).toBeCloseTo(start.y - 10)
  })

  test('stops at the edge rather than past it', () => {
    const state = pannedCrop(initialCrop(LANDSCAPE, FRAME), LANDSCAPE, FRAME, -100_000, -100_000)

    covers(state, LANDSCAPE)
  })

  test('cannot be walked out of bounds by repeated drags', () => {
    // The realistic failure: one drag clamps correctly and a hundred accumulate an error.
    let state = initialCrop(PORTRAIT, FRAME)

    for (let i = 0; i < 100; i += 1) {
      state = pannedCrop(state, PORTRAIT, FRAME, -50, 37)
      covers(state, PORTRAIT)
    }
  })

  test('does not move a square image at minimum zoom, in any direction', () => {
    // There is nowhere to go: the image is exactly the frame. A drag that appeared to do something
    // would be showing a gap.
    const start = initialCrop(SQUARE, FRAME)

    for (const [dx, dy] of [[20, 0], [-20, 0], [0, 20], [0, -20]]) {
      expect(pannedCrop(start, SQUARE, FRAME, dx, dy)).toEqual(start)
    }
  })
})

describe('zoomedCrop', () => {
  test('keeps the centre of the square where it was', () => {
    /*
     * The correction that makes a slider feel like a magnifier. Changing `scale` alone grows the
     * image from its top-left corner, so the square slides towards whatever was bottom-right --
     * which reads as the image running away from the pointer.
     *
     * Checked by asking what source pixel is at the centre before and after.
     */
    const before = zoomedCrop(initialCrop(LANDSCAPE, FRAME), LANDSCAPE, FRAME, 1.5)
    const after = zoomedCrop(before, LANDSCAPE, FRAME, 3)

    const centreOf = (state: CropState) => {
      const rect = sourceRect(state, LANDSCAPE, FRAME)
      return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 }
    }

    expect(centreOf(after).x).toBeCloseTo(centreOf(before).x, 0)
    expect(centreOf(after).y).toBeCloseTo(centreOf(before).y, 0)
  })

  test('covers the frame at every zoom between the two limits', () => {
    let state = initialCrop(LANDSCAPE, FRAME)

    for (let scale = 1; scale <= MAX_ZOOM; scale += 0.25) {
      state = zoomedCrop(state, LANDSCAPE, FRAME, scale)
      covers(state, LANDSCAPE)
    }

    // And all the way back down, which is the direction that uncovers a corner.
    for (let scale = MAX_ZOOM; scale >= 1; scale -= 0.25) {
      state = zoomedCrop(state, LANDSCAPE, FRAME, scale)
      covers(state, LANDSCAPE)
    }
  })

  test('holds the limits', () => {
    const start = initialCrop(LANDSCAPE, FRAME)

    expect(zoomedCrop(start, LANDSCAPE, FRAME, -5).scale).toBe(1)
    expect(zoomedCrop(start, LANDSCAPE, FRAME, 1000).scale).toBe(MAX_ZOOM)
  })
})

describe('sourceRect', () => {
  test('is the whole short side at minimum zoom', () => {
    // Zoomed out, the square shows all 900 pixels of the landscape image's height and a 900-wide
    // slice of its width.
    const rect = sourceRect(initialCrop(LANDSCAPE, FRAME), LANDSCAPE, FRAME)

    expect(rect.width).toBeCloseTo(900)
    expect(rect.height).toBeCloseTo(900)
    expect(rect.y).toBeCloseTo(0)
    expect(rect.x).toBeCloseTo((1600 - 900) / 2)
  })

  test('halves as the zoom doubles', () => {
    const state = zoomedCrop(initialCrop(LANDSCAPE, FRAME), LANDSCAPE, FRAME, 2)
    const rect = sourceRect(state, LANDSCAPE, FRAME)

    expect(rect.width).toBeCloseTo(450)
    expect(rect.height).toBeCloseTo(450)
  })

  test('never leaves the image, however far the state is pushed', () => {
    /*
     * `drawImage` with a source rectangle even slightly outside the image samples transparent black
     * along that edge -- a one-pixel dark line down the side of an avatar, which is the sort of
     * defect that gets noticed and never diagnosed.
     */
    for (const image of [LANDSCAPE, PORTRAIT, SQUARE]) {
      for (const scale of [1, 1.7, MAX_ZOOM]) {
        for (const [dx, dy] of [[-9999, -9999], [9999, 9999], [0, -9999], [-9999, 0]]) {
          const state = pannedCrop(
            zoomedCrop(initialCrop(image, FRAME), image, FRAME, scale),
            image,
            FRAME,
            dx,
            dy,
          )
          const rect = sourceRect(state, image, FRAME)

          expect(rect.x).toBeGreaterThanOrEqual(0)
          expect(rect.y).toBeGreaterThanOrEqual(0)
          expect(rect.x + rect.width).toBeLessThanOrEqual(image.width + 0.001)
          expect(rect.y + rect.height).toBeLessThanOrEqual(image.height + 0.001)
        }
      }
    }
  })

  test('is always square, because the frame is', () => {
    const state = pannedCrop(
      zoomedCrop(initialCrop(PORTRAIT, FRAME), PORTRAIT, FRAME, 2.3),
      PORTRAIT,
      FRAME,
      -30,
      -70,
    )
    const rect = sourceRect(state, PORTRAIT, FRAME)

    expect(rect.width).toBeCloseTo(rect.height)
  })

  test('answers the whole image rather than NaN when there is no scale to divide by', () => {
    const rect = sourceRect({ x: 0, y: 0, scale: 0 }, LANDSCAPE, FRAME)

    expect(rect).toEqual({ x: 0, y: 0, width: 1600, height: 900 })
  })
})

import Image from 'next/image'
import { BRAND_IMAGERY, type BrandImageKey } from '@/lib/brand'

type BrandImageProps = {
  imageKey: BrandImageKey
  /** Rendered CSS width. Must not exceed the entry's `maxRenderedWidth`. */
  width: number
  /**
   * Rendered CSS height, when the caller is cropping to a shape of its own. Omit to keep the
   * source file's aspect ratio.
   *
   * Given explicitly, this becomes the reserved box exactly, which is what keeps the rendered
   * height and the declared height in step — a derived height rounds to a whole pixel while the
   * browser lays out the half, and the two then disagree by one. Pair it with `object-cover` so
   * the difference crops rather than stretches.
   */
  height?: number
  /** 'eager' for above-the-fold use. Defaults to lazy. */
  loading?: 'lazy' | 'eager'
  className?: string
}

/**
 * A photograph from the guidelines deck, drawn no larger than its source file can carry.
 *
 * The deck's photographs are small. Rather than trusting every future caller to check the
 * manifest, this refuses a width above the declared ceiling — the failure is loud, at the call
 * site, instead of a blurred image nobody notices.
 * See design/features/landing-page-engagement.md sections 6.2 and 6.4.
 */
export const BrandImage = ({
  imageKey,
  width,
  height,
  loading = 'lazy',
  className,
}: BrandImageProps) => {
  const image = BRAND_IMAGERY[imageKey]

  if (width > image.maxRenderedWidth) {
    throw new Error(
      `BrandImage: ${imageKey} may be rendered at up to ${image.maxRenderedWidth}px wide, not ${width}px. ` +
        `The source file is ${image.width}px, and anything wider would draw it below 2x.`,
    )
  }

  return (
    <Image
      src={image.src}
      alt={image.alt}
      width={width}
      height={height ?? Math.round((width * image.height) / image.width)}
      loading={loading}
      className={className}
    />
  )
}

import Image from 'next/image'
import { BRAND_LOGOS, type BrandLogoVariant } from '@/lib/brand'

type LogoProps = {
  /** Which supplied artwork to use, keyed to the ground it sits on. */
  variant: BrandLogoVariant
  /** Rendered width in pixels. Height follows the artwork's aspect ratio. */
  width: number
  /** 'eager' for above-the-fold use. Defaults to lazy. */
  loading?: 'lazy' | 'eager'
  className?: string
}

/**
 * The brand badge, drawn from the artwork the 2026 guidelines supply.
 *
 * `loading` rather than the `priority` prop: `priority` is deprecated in Next.js 16, and the
 * documentation prefers `loading="eager"` over its `preload` replacement in most cases.
 */
export const Logo = ({ variant, width, loading = 'lazy', className }: LogoProps) => {
  const logo = BRAND_LOGOS[variant]

  return (
    <Image
      src={logo.src}
      alt={logo.alt}
      width={width}
      height={Math.round((width * logo.height) / logo.width)}
      loading={loading}
      className={className}
    />
  )
}

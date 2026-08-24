import { VALUE_ICONS, type BrandValueIconKey } from '@/lib/brand-icons'

type ValueIconProps = {
  iconKey: BrandValueIconKey
  /** Rendered square size in pixels. The artwork scales to fit inside it. */
  size: number
  className?: string
}

/**
 * One of the four brand value icons.
 *
 * Hidden from assistive technology: the label beside the icon carries the meaning, so
 * announcing the icon would only repeat it. Drawn in `currentColor` so the same artwork works
 * on the cream ground and on the green.
 * See design/features/landing-page-engagement.md criterion 11.
 */
export const ValueIcon = ({ iconKey, size, className }: ValueIconProps) => {
  const icon = VALUE_ICONS[iconKey]

  return (
    <svg
      viewBox={icon.viewBox}
      width={size}
      height={size}
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <path d={icon.path} fill="currentColor" />
    </svg>
  )
}

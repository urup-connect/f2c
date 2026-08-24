import { ValueIcon } from '@/components/Brand/ValueIcon'
import type { BrandValueIconKey } from '@/lib/brand-icons'

type BrandValueCardProps = {
  iconKey: BrandValueIconKey
  label: string
  description: string
}

/**
 * One of the club's four values, as a card.
 *
 * A list item, because four values are a list. The icon is decorative — the label beside it
 * carries the meaning.
 */
export const BrandValueCard = ({ iconKey, label, description }: BrandValueCardProps) => (
  <li className="flex flex-col gap-5 rounded-card bg-surface-muted p-6 transition-colors hover:bg-white">
    <ValueIcon iconKey={iconKey} size={40} className="text-forest-green" />

    <div className="flex flex-col gap-2">
      <h3 className="font-display text-xl text-forest-green">{label}</h3>
      <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
    </div>
  </li>
)

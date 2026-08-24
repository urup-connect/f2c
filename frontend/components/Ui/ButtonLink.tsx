import Link from 'next/link'
import type { ReactNode } from 'react'

type ButtonLinkProps = {
  href: string
  children: ReactNode
  tone?: 'primary' | 'secondary'
  /** The ground the control sits on. Decides its palette and its focus ring. */
  ground?: 'cream' | 'green'
}

const BASE =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 px-8 font-sans text-base font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2'

/*
 * Ground and tone rather than a colour override at the call site: a forest-green focus ring on
 * the forest-green hero is invisible, so the focus colour has to travel with the ground.
 * Every pairing here appears in design/features/landing-page-engagement.md section 8.
 */
const VARIANTS = {
  cream: {
    primary:
      'border-transparent bg-primary text-primary-foreground hover:bg-forest-green-deep focus-visible:outline-forest-green',
    secondary:
      'border-primary bg-transparent text-primary hover:bg-sage-green focus-visible:outline-forest-green',
  },
  green: {
    primary:
      'border-transparent bg-cream-warm text-forest-green hover:bg-white focus-visible:outline-cream-warm',
    secondary:
      'border-cream-warm bg-transparent text-cream-warm hover:bg-cream-warm/15 focus-visible:outline-cream-warm',
  },
} as const

/**
 * A navigation control that looks like a button.
 *
 * An anchor, not a button with a click handler, because it navigates — which keeps the middle
 * click, the context menu and the screen reader's link list all working.
 */
export const ButtonLink = ({
  href,
  children,
  tone = 'primary',
  ground = 'cream',
}: ButtonLinkProps) => (
  <Link href={href} className={`${BASE} ${VARIANTS[ground][tone]}`}>
    {children}
  </Link>
)

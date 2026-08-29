import Link from 'next/link'
import type { ReactNode } from 'react'

type ButtonLinkProps = {
  href: string
  children: ReactNode
  tone?: 'primary' | 'secondary'
  /** The ground the control sits on. Decides its palette and its focus ring. */
  ground?: 'paper' | 'leaf'
}

const BASE =
  'inline-flex h-12 items-center justify-center rounded-pill border-2 px-8 font-sans text-base font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2'

/*
 * Ground and tone rather than a colour override at the call site: a leaf-green focus ring on a
 * leaf-green hero is invisible, so the focus colour has to travel with the ground.
 */
const VARIANTS = {
  paper: {
    primary:
      'border-transparent bg-primary text-primary-foreground hover:bg-leaf-deep focus-visible:outline-leaf',
    secondary:
      'border-primary bg-transparent text-primary hover:bg-leaf-pale focus-visible:outline-leaf',
  },
  leaf: {
    primary:
      'border-transparent bg-paper text-leaf hover:bg-white focus-visible:outline-paper',
    secondary:
      'border-paper bg-transparent text-paper hover:bg-paper/15 focus-visible:outline-paper',
  },
} as const

/**
 * A navigation control that looks like a button.
 *
 * An anchor, not a button with a click handler, because it navigates — which keeps the middle click,
 * the context menu and the screen reader's link list all working.
 */
export const ButtonLink = ({
  href,
  children,
  tone = 'primary',
  ground = 'paper',
}: ButtonLinkProps) => (
  <Link href={href} className={`${BASE} ${VARIANTS[ground][tone]}`}>
    {children}
  </Link>
)

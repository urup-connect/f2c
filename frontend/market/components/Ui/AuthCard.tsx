import type { ReactNode } from 'react'

type AuthCardProps = {
  children: ReactNode
  /**
   * `narrow` for a screen that is a sentence and a button. `wide` for one that is a form.
   *
   * Alignment travels with the width rather than being a second prop, because there is no sensible
   * combination of the two that anyone would ask for: a narrow card holds centred prose, and a
   * two-column form with centred labels puts every label above the middle of its own input.
   */
  width?: 'narrow' | 'wide'
}

const CARD = 'w-full rounded-card bg-surface p-8 shadow-sm'

/*
 * `max-w-3xl` against `max-w-md` — 48rem and 28rem — and only from the medium breakpoint up, so a
 * phone gets one column at the same width on every signed-out screen.
 */
const WIDTHS = {
  narrow: 'max-w-md text-center',
  wide: 'max-w-md text-left md:max-w-3xl',
} as const

/**
 * The card the signed-out screens sit in.
 *
 * The width is the page's decision rather than the layout's: sign-up is a four-field form and
 * sign-in is one field, and a child cannot exceed its parent's maximum width. The layout owns
 * `<main>` and this adds no landmark of its own.
 */
export const AuthCard = ({ children, width = 'narrow' }: AuthCardProps) => (
  <div className={`${CARD} ${WIDTHS[width]}`}>{children}</div>
)

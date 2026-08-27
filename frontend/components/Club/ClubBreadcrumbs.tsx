'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

import { crumbsFor, type ClubHome } from '@/lib/club-breadcrumbs'
import { CLUB_SHELL } from '@/lib/club-content'

type ClubBreadcrumbsProps = {
  /** Where the trail starts. Passed in, because only the layout knows whose home it is. */
  home: ClubHome
}

/**
 * The row of crumbs between the green bar and the content.
 *
 * A client component for one reason: the trail comes from the URL, and `usePathname` is the only
 * thing that knows the URL inside a layout that does not re-render per route. Everything it decides
 * lives in `club-breadcrumbs.ts` and is tested there without a browser; what is left here is the
 * markup.
 *
 * **It renders nothing on a home.** Not a bar with one crumb in it -- `crumbsFor` returns an empty
 * trail and this returns null, so the layout collapses and the heading sits where it always did.
 * The alternative was a permanent strip that says "you are here" on the screen a person just chose
 * to be on.
 *
 * The current screen is the last crumb, carries no `href`, and is marked `aria-current="page"`. It
 * is a `span` rather than a link to itself: a link that goes nowhere is a link a keyboard user has
 * to tab past for nothing.
 *
 * The separators are `aria-hidden`. A screen reader announces the list and its items, which is the
 * structure; the chevrons are how the same structure is drawn for everybody else.
 */
export const ClubBreadcrumbs = ({ home }: ClubBreadcrumbsProps) => {
  const pathname = usePathname()
  const crumbs = crumbsFor(pathname ?? '', home)

  if (crumbs.length === 0) return null

  return (
    <nav
      aria-label={CLUB_SHELL.breadcrumbLabel}
      className="border-b border-border bg-surface-muted"
    >
      <ol className="mx-auto flex max-w-6xl list-none flex-wrap items-center gap-2 px-6 py-3">
        {crumbs.map((crumb, index) => (
          <li key={crumb.key} className="flex items-center gap-2">
            {index > 0 ? (
              <span aria-hidden="true" className="font-sans text-sm text-muted-foreground">
                ›
              </span>
            ) : null}

            {crumb.href === null ? (
              <span aria-current="page" className="font-sans text-sm text-foreground">
                {crumb.label}
              </span>
            ) : (
              <Link
                href={crumb.href}
                className="rounded-control font-sans text-sm text-muted-foreground underline-offset-4 hover:text-forest-green hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest-green"
              >
                {crumb.label}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}

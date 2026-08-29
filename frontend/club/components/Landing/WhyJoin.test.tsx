import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { WHY_JOIN } from '@/lib/landing-content'
import { WhyJoin } from './WhyJoin'

/* design/features/landing.md sections 2 and 4. */

describe('WhyJoin', () => {
  test('is headed at level two, below the page heading', () => {
    render(<WhyJoin />)

    expect(screen.getByRole('heading', { level: 2, name: WHY_JOIN.heading })).toBeInTheDocument()
  })

  test('heads the benefits at level three, inside the section rather than beside it', () => {
    render(<WhyJoin />)

    expect(
      screen.getByRole('heading', { level: 3, name: WHY_JOIN.benefitsHeading }),
    ).toBeInTheDocument()
  })

  test('says what the collective is before listing what it gives a member', () => {
    const { container } = render(<WhyJoin />)
    const text = container.textContent ?? ''

    expect(text.indexOf(WHY_JOIN.body)).toBeGreaterThan(-1)
    expect(text.indexOf(WHY_JOIN.body)).toBeLessThan(text.indexOf(WHY_JOIN.benefits[0]))
  })

  test('marks the benefits up as a list, so a reader is told how many there are', () => {
    render(<WhyJoin />)

    const items = screen.getAllByRole('listitem')

    expect(items.map((item) => item.textContent)).toEqual([...WHY_JOIN.benefits])
  })

  test('is a landmark named by its own heading', () => {
    render(<WhyJoin />)

    expect(screen.getByRole('region', { name: WHY_JOIN.heading })).toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { ClubCard, cardHeadingId } from './ClubCard'

describe('cardHeadingId', () => {
  test('makes an id out of the heading', () => {
    expect(cardHeadingId('Your details')).toBe('club-your-details')
  })

  test('drops punctuation rather than putting it in an attribute', () => {
    expect(cardHeadingId('How you sign in?')).toBe('club-how-you-sign-in')
  })

  test('leaves no trailing separator', () => {
    expect(cardHeadingId('Plants and orders ')).toBe('club-plants-and-orders')
  })
})

describe('ClubCard', () => {
  test('shows the heading', () => {
    render(
      <ClubCard heading="Your membership">
        <p>Contents</p>
      </ClubCard>,
    )

    expect(screen.getByRole('heading', { name: 'Your membership' })).toBeInTheDocument()
  })

  test('names its region after the heading, so a landmark list reads as the page', () => {
    render(
      <ClubCard heading="Your membership">
        <p>Contents</p>
      </ClubCard>,
    )

    expect(screen.getByRole('region', { name: 'Your membership' })).toBeInTheDocument()
  })

  test('renders what it was given', () => {
    render(
      <ClubCard heading="Your details">
        <p>Thandi Mokoena</p>
      </ClubCard>,
    )

    expect(screen.getByText('Thandi Mokoena')).toBeInTheDocument()
  })

  test('shows a standfirst when there is one', () => {
    render(
      <ClubCard heading="How you sign in" standfirst="A passkey uses this device.">
        <p>Contents</p>
      </ClubCard>,
    )

    expect(screen.getByText('A passkey uses this device.')).toBeInTheDocument()
  })

  test('shows a note when there is one', () => {
    render(
      <ClubCard heading="Your details" note="Ask the club to amend the record.">
        <p>Contents</p>
      </ClubCard>,
    )

    expect(screen.getByText('Ask the club to amend the record.')).toBeInTheDocument()
  })

  test('renders neither when there is neither', () => {
    const { container } = render(
      <ClubCard heading="Your details">
        <p>Only this</p>
      </ClubCard>,
    )

    expect(container.querySelectorAll('p')).toHaveLength(1)
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { SignInFeedback } from './SignInFeedback'

describe('SignInFeedback', () => {
  test('renders nothing when there is nothing to say', () => {
    const { container } = render(<SignInFeedback />)

    expect(container).toBeEmptyDOMElement()
  })

  test('interrupts for a refusal, which the member has to act on', () => {
    render(<SignInFeedback problem="That code is not valid." />)

    expect(screen.getByRole('alert')).toHaveTextContent('That code is not valid.')
  })

  test('announces a notice politely, because nothing is wrong', () => {
    // Interrupting a member who is about to type six digits is worse than telling
    // them a moment later.
    render(<SignInFeedback notice="A code is on its way." />)

    expect(screen.getByRole('status')).toHaveTextContent('A code is on its way.')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('shows both at once, so asking for a code keeps the reason on screen', () => {
    render(
      <SignInFeedback
        problem="Passkey sign-in was cancelled."
        notice="A code is on its way."
      />,
    )

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  test('treats an empty string as nothing to say', () => {
    const { container } = render(<SignInFeedback problem="" notice="" />)

    expect(container).toBeEmptyDOMElement()
  })
})

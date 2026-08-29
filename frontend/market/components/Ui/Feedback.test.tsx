import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { Feedback } from './Feedback'

describe('Feedback', () => {
  test('renders nothing when there is nothing to say', () => {
    const { container } = render(<Feedback />)

    expect(container).toBeEmptyDOMElement()
  })

  test('interrupts for a refusal, which the customer has to act on', () => {
    render(<Feedback problem="That code is not valid." />)

    expect(screen.getByRole('alert')).toHaveTextContent('That code is not valid.')
  })

  test('announces a notice politely, because nothing is wrong', () => {
    // Interrupting somebody who is about to type six digits is worse than telling them a moment later.
    render(<Feedback notice="A code is on its way." />)

    expect(screen.getByRole('status')).toHaveTextContent('A code is on its way.')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  test('shows both at once, so asking for a code keeps the reason on screen', () => {
    render(<Feedback problem="Passkey sign-in was cancelled." notice="A code is on its way." />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  test('treats an empty string as nothing to say', () => {
    const { container } = render(<Feedback problem="" notice="" />)

    expect(container).toBeEmptyDOMElement()
  })
})

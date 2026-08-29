import { render, screen } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, test } from 'vitest'
import { ConsentCheckbox } from './ConsentCheckbox'
import { CLUB_CONSENT_VALUE } from '@/lib/club-documents'

/*
 * design/features/club-document-agreements-at-sign-up.md criteria 2 to 5 and 10.
 *
 * The component in isolation: props in, nothing else. It knows no environment, no route and no
 * document — the href it is handed is the href it renders.
 */

const PROPS = {
  name: 'agreeConstitution',
  label: 'I have read and agree to the Constitution',
  linkText: 'Read the Constitution (PDF, opens in a new tab)',
  href: 'https://static.example.invalid/collective/documents/constitution/2/doc.pdf',
  versionName: 'version-constitution',
  version: '2',
}

const box = () => screen.getByRole('checkbox', { name: PROPS.label })

describe('an agreement checkbox', () => {
  test('is named by the sentence a member is agreeing to', () => {
    // Criterion 5.
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).toBeInTheDocument()
  })

  test('starts unticked', () => {
    // Criterion 2. Nothing pre-agrees on a member's behalf.
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).not.toBeChecked()
  })

  test('posts a value the rule accepts, under the field name it was given', () => {
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).toHaveAttribute('name', 'agreeConstitution')
    expect(box()).toHaveAttribute('value', CLUB_CONSENT_VALUE)
  })

  test('can be ticked and unticked by keyboard alone', async () => {
    render(<ConsentCheckbox {...PROPS} />)

    box().focus()
    await userEvent.keyboard(' ')
    expect(box()).toBeChecked()

    await userEvent.keyboard(' ')
    expect(box()).not.toBeChecked()
  })

  test('carries the id the error summary links to', () => {
    // The summary's anchors are #member-<field>, the same shape the text fields use.
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).toHaveAttribute('id', 'member-agreeConstitution')
  })
})

describe('the document link', () => {
  test('opens the document it was handed', () => {
    render(<ConsentCheckbox {...PROPS} />)

    expect(screen.getByRole('link', { name: PROPS.linkText })).toHaveAttribute('href', PROPS.href)
  })

  test('opens in a new tab, without handing the document host our page', () => {
    /*
     * Criterion 4. `noopener` because a page opened this way can otherwise reach back into the one
     * that opened it; `noreferrer` so the document host is not told which page the reader came from.
     */
    const link = () => screen.getByRole('link', { name: PROPS.linkText })

    render(<ConsentCheckbox {...PROPS} />)

    expect(link()).toHaveAttribute('target', '_blank')
    expect(link()).toHaveAttribute('rel', 'noopener noreferrer')
  })

  test('describes the checkbox rather than sitting inside its label', () => {
    /*
     * Criterion 3, and the reason this component exists rather than a link in a label: a link
     * inside a checkbox label both follows the link and toggles the box, so a member who opens the
     * rules comes back to a box that has ticked itself.
     */
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).toHaveAccessibleDescription(expect.stringContaining(PROPS.linkText))
    expect(box().closest('label')).toBeNull()
  })

  test('does not tick the box when it is followed', async () => {
    render(<ConsentCheckbox {...PROPS} />)

    await userEvent.click(screen.getByRole('link', { name: PROPS.linkText }))

    expect(box()).not.toBeChecked()
  })
})

describe('a refused agreement', () => {
  const REFUSED = { ...PROPS, error: 'Tick this to confirm you have read and agree.' }

  test('is marked as needing attention', () => {
    // Criterion 10.
    render(<ConsentCheckbox {...REFUSED} />)

    expect(box()).toHaveAttribute('aria-invalid', 'true')
  })

  test('says what is wrong, beside the box and in its description', () => {
    render(<ConsentCheckbox {...REFUSED} />)

    expect(screen.getByText(REFUSED.error)).toBeVisible()
    expect(box()).toHaveAccessibleDescription(expect.stringContaining(REFUSED.error))
  })

  test('still describes the document, so the message does not replace the link', () => {
    render(<ConsentCheckbox {...REFUSED} />)

    expect(box()).toHaveAccessibleDescription(expect.stringContaining(PROPS.linkText))
  })
})

describe('an agreement not refused', () => {
  test('is not marked, and says nothing about being wrong', () => {
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).not.toHaveAttribute('aria-invalid')
  })
})

describe('the revision the box was rendered against', () => {
  test('is posted in a hidden field of its own', () => {
    /*
     * The server compares it to whatever is in force when the submission arrives. Without it there
     * is nothing to compare, and a tick beside the old wording is indistinguishable from a tick
     * beside the new.
     */
    render(<ConsentCheckbox {...PROPS} />)

    const hidden = document.querySelector(`input[name="${PROPS.versionName}"]`)

    expect(hidden).toHaveAttribute('type', 'hidden')
    expect(hidden).toHaveValue(PROPS.version)
  })

  test('is posted whether or not the box is ticked', async () => {
    // The comparison has to be possible on a refused submission too.
    render(<ConsentCheckbox {...PROPS} />)

    const hidden = document.querySelector(`input[name="${PROPS.versionName}"]`)

    expect(hidden).toHaveValue(PROPS.version)

    await userEvent.click(box())

    expect(hidden).toHaveValue(PROPS.version)
  })

  test('is not the checkbox, and does not take its name', () => {
    // Two fields, two names. One posts consent, the other posts what was consented to.
    render(<ConsentCheckbox {...PROPS} />)

    expect(box()).toHaveAttribute('name', PROPS.name)
    expect(box()).toHaveAttribute('value', CLUB_CONSENT_VALUE)
    expect(PROPS.versionName).not.toBe(PROPS.name)
  })
})

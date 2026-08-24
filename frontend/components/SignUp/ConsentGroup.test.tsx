import { render, screen } from '@testing-library/react'
import { describe, expect, test } from 'vitest'
import { ConsentGroup } from './ConsentGroup'
import { MEMBER_DETAILS_COPY } from '@/lib/member-details-content'
import { CLUB_DOCUMENT_IDS, clubVersionField } from '@/lib/club-documents'
import { clubDocumentRevisions } from '@/test-support/club-documents'

/*
 * design/features/sign-up.md section 5.
 *
 * The revisions are a prop: the address, the version and the sentence beside each box all come from
 * Django, and this component knows nothing about which environment it is in.
 */

const REVISIONS = clubDocumentRevisions({ constitution: '3' })

const { legend, notice, agreements } = MEMBER_DETAILS_COPY.consents

describe('the agreement group', () => {
  test('is one named group rather than three loose sentences', () => {
    // Criterion 6: a screen reader announces the group before the first box.
    render(<ConsentGroup revisions={REVISIONS} />)

    expect(screen.getByRole('group', { name: new RegExp(legend) })).toBeInTheDocument()
  })

  test('says that the agreement is not recorded', () => {
    // Criterion 6, and the honest half of section 9.
    render(<ConsentGroup revisions={REVISIONS} />)

    expect(screen.getByText(notice)).toBeVisible()
  })

  test('offers one box per document, in document order', () => {
    // Criterion 1.
    render(<ConsentGroup revisions={REVISIONS} />)

    expect(screen.getAllByRole('checkbox').map((box) => box.getAttribute('name'))).toEqual([
      'agreeClubRules',
      'agreeAnnexures',
      'agreeConstitution',
    ])
  })

  test('starts with none of them ticked', () => {
    // Criterion 2.
    render(<ConsentGroup revisions={REVISIONS} />)

    for (const box of screen.getAllByRole('checkbox')) expect(box).not.toBeChecked()
  })

  test('points each link at its own document', () => {
    /*
     * The pairing that matters: a box saying "the constitution" that opens the annexures is not a
     * consent to anything.
     */
    render(<ConsentGroup revisions={REVISIONS} />)

    expect(screen.getByRole('link', { name: agreements.agreeClubRules.link })).toHaveAttribute(
      'href',
      REVISIONS['club-rules'].url,
    )
    expect(screen.getByRole('link', { name: agreements.agreeAnnexures.link })).toHaveAttribute(
      'href',
      REVISIONS.annexures.url,
    )
    expect(screen.getByRole('link', { name: agreements.agreeConstitution.link })).toHaveAttribute(
      'href',
      REVISIONS.constitution.url,
    )
  })

  test('has a link for every document the club holds', () => {
    render(<ConsentGroup revisions={REVISIONS} />)

    expect(screen.getAllByRole('link')).toHaveLength(CLUB_DOCUMENT_IDS.length)
  })
})

describe('a refusal on one agreement', () => {
  test('marks that box and leaves the other two alone', () => {
    // Criterion 10.
    render(
      <ConsentGroup
        revisions={REVISIONS}
        messages={new Map([['agreeAnnexures', 'Tick this to confirm you have read and agree.']])}
      />,
    )

    expect(screen.getByRole('checkbox', { name: REVISIONS.annexures.consentText })).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    expect(
      screen.getByRole('checkbox', { name: REVISIONS['club-rules'].consentText }),
    ).not.toHaveAttribute('aria-invalid')
  })

  test('shows the message once, against the box it belongs to', () => {
    const message = 'Tick this to confirm you have read and agree.'

    render(<ConsentGroup revisions={REVISIONS} messages={new Map([['agreeConstitution', message]])} />)

    expect(screen.getByText(message)).toBeVisible()
    expect(
      screen.getByRole('checkbox', { name: REVISIONS.constitution.consentText }),
    ).toHaveAccessibleDescription(expect.stringContaining(message))
  })
})

describe('the wording and the revision', () => {
  test('name each box with the sentence the API sent, not with local copy', () => {
    /*
     * Django records a digest of this sentence against every agreement. If this component rendered
     * its own wording, the record would be of words the member never read. See documents/models.py.
     */
    render(<ConsentGroup revisions={REVISIONS} />)

    for (const id of CLUB_DOCUMENT_IDS) {
      expect(
        screen.getByRole('checkbox', { name: REVISIONS[id].consentText }),
      ).toBeInTheDocument()
    }
  })

  test('post the revision each box was rendered against', () => {
    render(<ConsentGroup revisions={REVISIONS} />)

    for (const id of CLUB_DOCUMENT_IDS) {
      expect(document.querySelector(`input[name="${clubVersionField(id)}"]`)).toHaveValue(
        REVISIONS[id].version,
      )
    }
  })

  test('keep each version with its own document', () => {
    // A version landing on the wrong box would file an agreement against the wrong revision.
    render(<ConsentGroup revisions={REVISIONS} />)

    expect(document.querySelector('input[name="version-constitution"]')).toHaveValue('3')
    expect(document.querySelector('input[name="version-club-rules"]')).toHaveValue('1')
  })
})

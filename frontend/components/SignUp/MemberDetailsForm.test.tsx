import { render, screen, within } from '@testing-library/react'
import { userEvent } from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { MemberDetailsForm } from './MemberDetailsForm'
import { MEMBER_DETAILS_COPY, memberDetailsRefusalMessage } from '@/lib/member-details-content'
import type { CalendarDate } from '@/lib/age-gate'
import { CLUB_DOCUMENT_IDS, clubVersionField } from '@/lib/club-documents'
import { clubDocumentRevisions } from '@/test-support/club-documents'

/*
 * design/features/member-details-at-sign-up.md criteria 2, 32, 38, 39 and 41, and
 * design/features/club-document-agreements-at-sign-up.md criteria 1, 7, 8, 10, 11 and 13.
 *
 * Every value typed here is invented, and the ID number's check digit is computed.
 */

const DATE_OF_BIRTH: CalendarDate = { year: 1990, month: 3, day: 15 }

/**
 * Invented, like every value here. The real addresses and versions are published in the admin, not
 * held as constants anywhere.
 */
const REVISIONS = clubDocumentRevisions()

const AGREEMENTS = MEMBER_DETAILS_COPY.consents.agreements

/** Which document each agreement field stands for, so a box can be found by its sentence. */
const DOCUMENT_OF = {
  agreeClubRules: 'club-rules',
  agreeAnnexures: 'annexures',
  agreeConstitution: 'constitution',
} as const

const VALID = {
  'First name': 'Thandiwe',
  'Last name': 'Nkosi',
  Nickname: 'GreenThumb',
  'Email address': 'thandiwe@example.com',
  'Mobile number': '082 123 4567',
  'South African ID number': '9003155009082',
} as const

type AgreementField = keyof typeof AGREEMENTS

const box = (field: AgreementField) =>
  screen.getByRole('checkbox', { name: REVISIONS[DOCUMENT_OF[field]].consentText })

/**
 * Ticks the three agreements, skipping any the caller wants left alone.
 *
 * Idempotent, because `fill` is called twice in the test that fixes a refusal and a second click
 * would untick what the first ticked.
 */
const agree = async (except: readonly AgreementField[] = []) => {
  for (const field of Object.keys(AGREEMENTS) as AgreementField[]) {
    if (except.includes(field)) continue

    const control = box(field)

    if (!(control as HTMLInputElement).checked) await userEvent.click(control)
  }
}

const fill = async (
  overrides: Readonly<Record<string, string>> = {},
  unticked: readonly AgreementField[] = [],
) => {
  for (const [label, value] of Object.entries({ ...VALID, ...overrides })) {
    const field = screen.getByLabelText(label)

    await userEvent.clear(field)
    if (value.length > 0) await userEvent.type(field, value)
  }

  await agree(unticked)
}

const submit = async () => {
  await userEvent.click(screen.getByRole('button', { name: MEMBER_DETAILS_COPY.submit }))
}

const renderForm = (props: Partial<Parameters<typeof MemberDetailsForm>[0]> = {}) => {
  const action = vi.fn()

  render(
    <MemberDetailsForm
      action={action}
      dateOfBirth={DATE_OF_BIRTH}
      revisions={REVISIONS}
      {...props}
    />,
  )

  return action
}

describe('the fields', () => {
  // Criterion 2.
  test('are the six the club asks for, in order', () => {
    renderForm()

    const labels = Object.values(MEMBER_DETAILS_COPY.fields).map(({ label }) => label)

    expect(screen.getAllByRole('textbox').map((field) => field.getAttribute('name'))).toEqual([
      'firstName',
      'lastName',
      'nickname',
      'email',
      'mobile',
      'idNumber',
    ])

    for (const label of labels) expect(screen.getByLabelText(label)).toBeInTheDocument()
  })

  test('let a browser fill the ones it knows', () => {
    renderForm()

    const expected = [
      ['First name', 'given-name'],
      ['Last name', 'family-name'],
      ['Nickname', 'nickname'],
      ['Email address', 'email'],
      ['Mobile number', 'tel-national'],
    ] as const

    for (const [label, token] of expected) {
      expect(screen.getByLabelText(label)).toHaveAttribute('autocomplete', token)
    }
  })

  test('never offer to remember the ID number', () => {
    renderForm()

    expect(screen.getByLabelText('South African ID number')).toHaveAttribute('autocomplete', 'off')
  })

  test('are tabbed through in reading order, whatever the columns do', async () => {
    // Criterion 52. A visual order that disagrees with the tab order is a WCAG failure.
    renderForm()

    const order = Object.values(MEMBER_DETAILS_COPY.fields).map(({ label }) => label)

    for (const label of order) {
      await userEvent.tab()
      expect(screen.getByLabelText(label)).toHaveFocus()
    }
  })

  test('show a number keypad for the ID number and the mobile number', () => {
    renderForm()

    for (const label of ['South African ID number', 'Mobile number']) {
      expect(screen.getByLabelText(label)).toHaveAttribute('inputmode', 'numeric')
    }
  })
})

describe('the mobile number on screen', () => {
  // Criterion 53.
  test('is regrouped when the field loses focus', async () => {
    renderForm()

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, '+27821234567')
    await userEvent.tab()

    expect(field).toHaveValue('082 123 4567')
  })

  test('is left as typed while the field still has focus', async () => {
    // Nothing moves under the caret. Criterion 53 is about blur, deliberately.
    renderForm()

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, '+27821234567')

    expect(field).toHaveValue('+27821234567')
  })

  // Criterion 54.
  test('is left exactly as typed when the rule does not accept it', async () => {
    renderForm()

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, '0861234567')
    await userEvent.tab()

    expect(field).toHaveValue('0861234567')
  })

  test('still submits after being regrouped', async () => {
    const action = renderForm()

    await fill({ 'Mobile number': '+27821234567' })
    await userEvent.tab()
    await submit()

    expect(action).toHaveBeenCalledTimes(1)
    expect((action.mock.calls[0][0] as FormData).get('mobile')).toBe('082 123 4567')
  })

  test('is the only field rewritten on blur', async () => {
    renderForm()

    const name = screen.getByLabelText('First name')

    await userEvent.type(name, '  Thandiwe  ')
    await userEvent.tab()

    // The name rule trims when it validates; the field itself leaves what was typed alone.
    expect(name).toHaveValue('  Thandiwe  ')
  })
})

describe('what the two number fields let through', () => {
  // Criterion 57.
  test('the mobile number ignores letters entirely', async () => {
    renderForm()

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, 'abc')

    expect(field).toHaveValue('')
  })

  test('the mobile number keeps the punctuation people write numbers with', async () => {
    renderForm()

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, '+27 82 123-4567')

    expect(field).toHaveValue('+27 82 123-4567')
  })

  test('the mobile number drops a plus that is not at the start', async () => {
    renderForm()

    const field = screen.getByLabelText('Mobile number')

    await userEvent.type(field, '082+1234567')

    expect(field).toHaveValue('0821234567')
  })

  // Criterion 58.
  test('the ID number ignores everything but digits', async () => {
    renderForm()

    const field = screen.getByLabelText('South African ID number')

    await userEvent.type(field, '9003a15 5009-082')

    expect(field).toHaveValue('9003155009082')
  })

  // Criterion 59.
  test('the ID number stops at thirteen digits', async () => {
    renderForm()

    const field = screen.getByLabelText('South African ID number')

    await userEvent.type(field, '90031550090821234')

    expect(field).toHaveValue('9003155009082')
  })

  test('a pasted ID number written with spaces still lands as thirteen digits', async () => {
    renderForm()

    const field = screen.getByLabelText('South African ID number')

    field.focus()
    await userEvent.paste('900315 5009 082')

    expect(field).toHaveValue('9003155009082')
  })

  // Criterion 60.
  test('the name fields are left alone, so a name is never filtered', async () => {
    renderForm()

    const field = screen.getByLabelText('Last name')

    await userEvent.type(field, "Nkosi-van der Merwe")

    expect(field).toHaveValue('Nkosi-van der Merwe')
  })

  test('the nickname is left alone, so its own rule is what refuses a bad one', async () => {
    renderForm()

    const field = screen.getByLabelText('Nickname')

    await userEvent.type(field, 'green thumb!')

    expect(field).toHaveValue('green thumb!')
  })
})

describe('a submission the browser can already see is wrong', () => {
  test('is not sent to the server', async () => {
    const action = renderForm()

    await fill({ 'First name': '' })
    await submit()

    expect(action).not.toHaveBeenCalled()
  })

  // Criterion 38.
  test('reports every failing field at once', async () => {
    renderForm()

    await fill({ 'First name': '', 'South African ID number': '1234' })
    await submit()

    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  test('marks each failing field and names the problem beside it', async () => {
    renderForm()

    await fill({ Nickname: 'ab' })
    await submit()

    expect(screen.getByLabelText('Nickname')).toHaveAttribute('aria-invalid', 'true')
    expect(
      screen.getByText(memberDetailsRefusalMessage('nickname-length', '15 March 1990')),
    ).toBeInTheDocument()
  })

  // Criterion 39.
  test('keeps every value the visitor typed', async () => {
    renderForm()

    await fill({ 'South African ID number': '1234' })
    await submit()

    expect(screen.getByLabelText('First name')).toHaveValue('Thandiwe')
    expect(screen.getByLabelText('Email address')).toHaveValue('thandiwe@example.com')
    expect(screen.getByLabelText('South African ID number')).toHaveValue('1234')
  })

  test('leaves a field alone when nothing is wrong with it', async () => {
    renderForm()

    await fill({ 'First name': '' })
    await submit()

    expect(screen.getByLabelText('Last name')).not.toHaveAttribute('aria-invalid')
  })

  test('clears a refusal once the visitor fixes it', async () => {
    renderForm()

    await fill({ 'First name': '' })
    await submit()

    expect(screen.getByRole('alert')).toBeInTheDocument()

    await fill()
    await submit()

    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('an ID number that disagrees with the date of birth', () => {
  // Criterion 32, and the product owner's decision in section 6.3.
  test('is refused against the ID number field, naming the date on file', async () => {
    renderForm()

    // A number whose own checksum is sound, for 29 February 2004 rather than 15 March 1990.
    await fill({ 'South African ID number': '0402295009086' })
    await submit()

    expect(screen.getByLabelText('South African ID number')).toHaveAttribute(
      'aria-invalid',
      'true',
    )
    /*
     * Matched exactly, not by pattern: the message appears twice on purpose — once in the summary
     * at the top and once beside the field — and the summary entry reads "<label> — <message>".
     */
    expect(
      screen.getByText(memberDetailsRefusalMessage('id-date-mismatch', '15 March 1990')),
    ).toBeInTheDocument()
  })

  test('offers nothing that would change the date of birth', async () => {
    renderForm()

    await fill({ 'South African ID number': '0402295009086' })
    await submit()

    // No link anywhere on the form goes back to the gate. The date is not editable from here.
    for (const link of screen.getAllByRole('link')) {
      expect(link.getAttribute('href')).not.toContain('age-check')
    }

    // The summary's own links each point at a field, and nowhere else.
    for (const link of within(screen.getByRole('alert')).getAllByRole('link')) {
      expect(link.getAttribute('href')).toMatch(/^#member-/)
    }
  })

  test('does not report the date when the number itself does not add up', async () => {
    // Criterion 35: a fumbled digit is a typo, not a disagreement.
    renderForm()

    await fill({ 'South African ID number': '9002155009082' })
    await submit()

    expect(
      screen.getByText(memberDetailsRefusalMessage('id-checksum', '15 March 1990')),
    ).toBeInTheDocument()
    expect(
      screen.queryByText(memberDetailsRefusalMessage('id-date-mismatch', '15 March 1990')),
    ).not.toBeInTheDocument()
  })
})

describe('a submission the browser is happy with', () => {
  // Criterion 41: the browser check is a courtesy; the server decides.
  test('goes to the server', async () => {
    const action = renderForm()

    await fill()
    await submit()

    expect(action).toHaveBeenCalledTimes(1)
  })

  test('sends every field', async () => {
    const action = renderForm()

    await fill()
    await submit()

    const formData = action.mock.calls[0][0] as FormData

    expect(formData.get('firstName')).toBe('Thandiwe')
    expect(formData.get('idNumber')).toBe('9003155009082')
  })
})

describe('a refusal the server sent back', () => {
  /*
   * The no-JavaScript path: the server redirects with reason codes and the page renders them on
   * first paint. Criterion 40 — codes only, never a typed value.
   */
  test('is shown without the visitor submitting anything', () => {
    renderForm({ refusals: [{ field: 'nickname', reason: 'nickname-unavailable' }] })

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByLabelText('Nickname')).toHaveAttribute('aria-invalid', 'true')
  })

  test('leaves the fields empty, because no value came back with it', () => {
    renderForm({ refusals: [{ field: 'nickname', reason: 'nickname-unavailable' }] })

    expect(screen.getByLabelText('Nickname')).toHaveValue('')
  })
})

describe('the three club document agreements', () => {
  test('sit below the six details and above the submit control', () => {
    // Club documents criterion 1, as the DOM orders it.
    renderForm()

    const controls = Array.from(
      document.querySelectorAll('input[name="idNumber"], input[type="checkbox"], button'),
    ).map((element) => element.getAttribute('name') ?? element.tagName)

    expect(controls).toEqual([
      'idNumber',
      'agreeClubRules',
      'agreeAnnexures',
      'agreeConstitution',
      'BUTTON',
    ])
  })

  test('are reached by keyboard from the ID number, each box then its own document', async () => {
    /*
     * Club documents criterion 7. Reading order and tab order are the same order, and each link is
     * keyboard reachable immediately after the box it belongs to — which is the whole reason the
     * link is a sibling of the label rather than inside it.
     */
    renderForm()

    screen.getByLabelText('South African ID number').focus()

    for (const field of ['agreeClubRules', 'agreeAnnexures', 'agreeConstitution'] as const) {
      await userEvent.tab()
      expect(box(field)).toHaveFocus()

      await userEvent.tab()
      expect(screen.getByRole('link', { name: AGREEMENTS[field].link })).toHaveFocus()
    }

    await userEvent.tab()
    expect(screen.getByRole('button', { name: MEMBER_DETAILS_COPY.submit })).toHaveFocus()
  })

  test('let a submission through once all three are ticked', async () => {
    const action = renderForm()

    await fill()
    await submit()

    expect(action).toHaveBeenCalledTimes(1)

    const formData = action.mock.calls[0][0] as FormData

    expect(formData.get('agreeClubRules')).toBe('yes')
    expect(formData.get('agreeAnnexures')).toBe('yes')
    expect(formData.get('agreeConstitution')).toBe('yes')
  })

  test.each(['agreeClubRules', 'agreeAnnexures', 'agreeConstitution'] as const)(
    'stop a submission when %s is left unticked',
    async (field) => {
      // Club documents criterion 8, and criterion 13: nothing reaches the server.
      const action = renderForm()

      await fill({}, [field])
      await submit()

      expect(action).not.toHaveBeenCalled()
      expect(box(field)).toHaveAttribute('aria-invalid', 'true')
    },
  )

  test('stop a submission when a box is ticked and then unticked again', async () => {
    const action = renderForm()

    await fill()
    await userEvent.click(box('agreeAnnexures'))
    await submit()

    expect(action).not.toHaveBeenCalled()
  })

  test('say what is wrong beside the box that is wrong', async () => {
    // Club documents criterion 10.
    renderForm()

    await fill({}, ['agreeConstitution'])
    await submit()

    expect(box('agreeConstitution')).toHaveAccessibleDescription(
      expect.stringContaining(memberDetailsRefusalMessage('consent-required', '15 March 1990')),
    )
    expect(box('agreeClubRules')).not.toHaveAttribute('aria-invalid')
  })

  test('are listed in the summary after the fields, each linking to its own box', async () => {
    // Club documents criterion 11.
    renderForm()

    await fill({ 'First name': '' }, ['agreeAnnexures'])
    await submit()

    const links = within(screen.getByRole('alert')).getAllByRole('link')

    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '#member-firstName',
      '#member-agreeAnnexures',
    ])
  })

  test('are refused one line each when none of them is ticked', async () => {
    // Club documents criterion 9, on the screen rather than in the rules.
    renderForm()

    await fill({}, ['agreeClubRules', 'agreeAnnexures', 'agreeConstitution'])
    await submit()

    expect(within(screen.getByRole('alert')).getAllByRole('listitem')).toHaveLength(3)
  })

  test('keep everything the member typed when one of them is refused', async () => {
    // Club documents criterion 13. Nine things to fill in is too many to retype for one tick.
    renderForm()

    await fill({}, ['agreeClubRules'])
    await submit()

    expect(screen.getByLabelText('First name')).toHaveValue('Thandiwe')
    expect(screen.getByLabelText('South African ID number')).toHaveValue('9003155009082')
  })

  test('keep the two ticks that were made', async () => {
    renderForm()

    await fill({}, ['agreeClubRules'])
    await submit()

    expect(box('agreeAnnexures')).toBeChecked()
    expect(box('agreeConstitution')).toBeChecked()
    expect(box('agreeClubRules')).not.toBeChecked()
  })

  test('show a refusal the server sent back, against the right box', () => {
    // Club documents criterion 14, arriving as a code on first paint.
    renderForm({ refusals: [{ field: 'agreeConstitution', reason: 'consent-required' }] })

    expect(box('agreeConstitution')).toHaveAttribute('aria-invalid', 'true')
    expect(box('agreeClubRules')).not.toHaveAttribute('aria-invalid')
  })

  test('open each document where the page was told it lives', () => {
    renderForm()

    expect(screen.getByRole('link', { name: AGREEMENTS.agreeClubRules.link })).toHaveAttribute(
      'href',
      REVISIONS['club-rules'].url,
    )
  })

  test('post the revision the form was rendered against, one field per document', () => {
    /*
     * What lets the server tell a tick beside the current wording from a tick beside wording that
     * was replaced while the form was open. Without it the two are indistinguishable.
     */
    renderForm()

    for (const id of CLUB_DOCUMENT_IDS) {
      expect(document.querySelector(`input[name="${clubVersionField(id)}"]`)).toHaveValue(
        REVISIONS[id].version,
      )
    }
  })
})

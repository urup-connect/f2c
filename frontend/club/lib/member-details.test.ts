import { describe, expect, test } from 'vitest'
import {
  MEMBER_CONSENT_FIELDS,
  MEMBER_DETAILS_FIELDS,
  MEMBER_DETAILS_REFUSALS,
  isMemberDetailsRefusal,
  mergeMemberDetailsRefusals,
  parseMemberDetailsRefusals,
  readMemberDetailsInput,
  serialiseMemberDetailsRefusals,
  validateMemberDetails as validateAgainst,
} from './member-details'
import type { MemberDetailsInput, MemberDetailsOutcome } from './member-details'
import { CLUB_CONSENT_VALUE, CLUB_DOCUMENT_IDS, clubVersionField } from './club-documents'
import type { CalendarDate } from './age-gate'
import { clubDocumentRevisions } from '@/test-support/club-documents'

/*
 * design/features/member-details-at-sign-up.md criteria 37, 38, 42, 44 and 45, and
 * design/features/club-document-agreements-at-sign-up.md criteria 8, 9, 11, 12, 24 and 25.
 *
 * The field rules themselves are tested in the module that owns each one. What is tested here is
 * the composition: that every failing field is reported at once, that an absent field is missing
 * rather than acceptable, and that the accepted result is the normalised form and nothing else.
 *
 * All values are invented. The ID number's check digit is computed, not sourced.
 */

const DOB: CalendarDate = { year: 1990, month: 3, day: 15 }

/** The revisions in force for these cases. All at version 1 unless a case says otherwise. */
const REVISIONS = clubDocumentRevisions()

/**
 * The rule with the revisions in force supplied.
 *
 * `validateMemberDetails` takes what Django says is published, because a document's version is no
 * longer a constant in this codebase. Wrapped here so the cases below read as they did: what they
 * are about is the six fields and the three boxes, not which revision happens to be live. The cases
 * that *are* about the revision call `validateAgainst` directly.
 */
const validateMemberDetails = (
  input: MemberDetailsInput,
  dateOfBirth: CalendarDate,
  takenNicknameKeys: readonly string[] = [],
) => validateAgainst(input, dateOfBirth, REVISIONS, takenNicknameKeys)

/** Every name the form posts, the hidden version fields included. */
const VALID_FORM: Readonly<Record<string, string>> = {
  firstName: 'Thandiwe',
  lastName: 'Nkosi',
  nickname: 'GreenThumb',
  email: 'thandiwe@example.com',
  mobile: '082 123 4567',
  idNumber: '9003155009082',
  agreeClubRules: CLUB_CONSENT_VALUE,
  agreeAnnexures: CLUB_CONSENT_VALUE,
  agreeConstitution: CLUB_CONSENT_VALUE,
  ...Object.fromEntries(CLUB_DOCUMENT_IDS.map((id) => [clubVersionField(id), '1'])),
}

const VALID: MemberDetailsInput = {
  firstName: 'Thandiwe',
  lastName: 'Nkosi',
  nickname: 'GreenThumb',
  email: 'thandiwe@example.com',
  mobile: '082 123 4567',
  idNumber: '9003155009082',
  agreeClubRules: CLUB_CONSENT_VALUE,
  agreeAnnexures: CLUB_CONSENT_VALUE,
  agreeConstitution: CLUB_CONSENT_VALUE,
  versions: Object.fromEntries(CLUB_DOCUMENT_IDS.map((id) => [id, '1'])),
}

const refusals = (outcome: MemberDetailsOutcome) =>
  outcome.status === 'refused' ? outcome.refusals : []

const reasonFor = (outcome: MemberDetailsOutcome, field: string) =>
  refusals(outcome).find((entry) => entry.field === field)?.reason ?? null

const accepted = (outcome: MemberDetailsOutcome) =>
  outcome.status === 'accepted' ? outcome.details : null

describe('the fields', () => {
  test('are the six details and the three agreements, in the order the form shows them', () => {
    /*
     * The agreements sit in the same list as the details on purpose: refusal serialisation, the
     * one-message-per-field rule, the error summary and the no-script path already work for
     * anything in it, and a second mechanism for three checkboxes would be a second thing to keep
     * in step. Club documents criterion 11.
     */
    expect([...MEMBER_DETAILS_FIELDS]).toEqual([
      'firstName',
      'lastName',
      'nickname',
      'email',
      'mobile',
      'idNumber',
      'agreeClubRules',
      'agreeAnnexures',
      'agreeConstitution',
    ])
  })

  test('give every club document a box of its own to tick', () => {
    /*
     * The guard against a fourth document arriving with nowhere to agree to it: the mapping is
     * written out by hand, so nothing else would notice.
     */
    expect(MEMBER_CONSENT_FIELDS.map(({ document }) => document)).toEqual([...CLUB_DOCUMENT_IDS])
  })

  test('narrow a refusal code from an arbitrary string', () => {
    expect(isMemberDetailsRefusal('id-checksum')).toBe(true)
    expect(isMemberDetailsRefusal('id-nearly-right')).toBe(false)
    expect(isMemberDetailsRefusal(null)).toBe(false)
  })

  test('name every refusal the six rules between them can produce', () => {
    expect([...MEMBER_DETAILS_REFUSALS]).toEqual([
      'name-missing',
      'name-too-long',
      'name-unexpected-characters',
      'nickname-missing',
      'nickname-length',
      'nickname-unexpected-characters',
      'nickname-shape',
      'nickname-unavailable',
      'email-missing',
      'email-malformed',
      'email-too-long',
      'mobile-missing',
      'mobile-unexpected-characters',
      'mobile-length',
      'mobile-not-a-mobile',
      'id-missing',
      'id-length',
      'id-not-digits',
      'id-checksum',
      'id-date-mismatch',
      'id-not-recognised',
      'consent-required',
      'consent-superseded',
    ])
  })
})

describe('a submission with every field valid', () => {
  test('is accepted', () => {
    expect(validateMemberDetails(VALID, DOB).status).toBe('accepted')
  })

  // Criterion 37: the accepted result is the normalised form, ready to store and stored nowhere.
  test('carries the normalised form of every value', () => {
    expect(accepted(validateMemberDetails(VALID, DOB))).toEqual({
      firstName: 'Thandiwe',
      lastName: 'Nkosi',
      nickname: 'GreenThumb',
      nicknameKey: 'greenthumb',
      email: 'thandiwe@example.com',
      mobile: '+27821234567',
      idNumber: '9003155009082',
      dateOfBirth: DOB,
      consents: [
        { document: 'club-rules', version: '1' },
        { document: 'annexures', version: '1' },
        { document: 'constitution', version: '1' },
      ],
    })
  })

  test('normalises each field the way its own rule does', () => {
    const details = accepted(
      validateMemberDetails(
        {
          ...VALID,
          firstName: '  Thandiwe   Nomsa ',
          email: 'Thandiwe@Example.COM',
          mobile: '+27 (82) 123-4567',
          idNumber: '900315 5009 082',
        },
        DOB,
      ),
    )

    expect(details).toMatchObject({
      firstName: 'Thandiwe Nomsa',
      email: 'thandiwe@example.com',
      mobile: '+27821234567',
      idNumber: '9003155009082',
    })
  })
})

describe('a submission with more than one field wrong', () => {
  // Criterion 38.
  test('reports every failing field at once', () => {
    const outcome = validateMemberDetails(
      {
        ...VALID,
        firstName: '',
        lastName: 'Nkosi9',
        nickname: 'ab',
        email: 'nope',
        mobile: '',
        idNumber: '',
      },
      DOB,
    )

    expect(refusals(outcome)).toEqual([
      { field: 'firstName', reason: 'name-missing' },
      { field: 'lastName', reason: 'name-unexpected-characters' },
      { field: 'nickname', reason: 'nickname-length' },
      { field: 'email', reason: 'email-malformed' },
      { field: 'mobile', reason: 'mobile-missing' },
      { field: 'idNumber', reason: 'id-missing' },
    ])
  })

  test('reports them in the order the form shows the fields', () => {
    const outcome = validateMemberDetails({ ...VALID, firstName: '', idNumber: '' }, DOB)

    expect(refusals(outcome).map((entry) => entry.field)).toEqual(['firstName', 'idNumber'])
  })

  test('carries the field and the reason and nothing else', () => {
    // The typed value never travels with a refusal. An ID number least of all.
    const outcome = validateMemberDetails({ ...VALID, idNumber: '1234567890123' }, DOB)

    for (const entry of refusals(outcome)) {
      expect(Object.keys(entry).sort()).toEqual(['field', 'reason'])
    }
  })
})

describe('the refusal each rule contributes', () => {
  test.each([
    ['firstName', '', 'name-missing'],
    ['firstName', 'A'.repeat(71), 'name-too-long'],
    ['lastName', 'Nkosi!', 'name-unexpected-characters'],
    ['nickname', '', 'nickname-missing'],
    ['nickname', 'ab', 'nickname-length'],
    ['nickname', 'green thumb', 'nickname-unexpected-characters'],
    ['nickname', '7grower', 'nickname-shape'],
    ['nickname', 'admin', 'nickname-unavailable'],
    ['email', '', 'email-missing'],
    ['email', 'thandiwe@example', 'email-malformed'],
    ['email', `${'a'.repeat(65)}@example.com`, 'email-too-long'],
    ['mobile', '', 'mobile-missing'],
    ['mobile', 'call me', 'mobile-unexpected-characters'],
    ['mobile', '082123456', 'mobile-length'],
    ['mobile', '0861234567', 'mobile-not-a-mobile'],
    ['idNumber', '', 'id-missing'],
    ['idNumber', '900315500908', 'id-length'],
    ['idNumber', '90031550090X2', 'id-not-digits'],
    ['idNumber', '9003155009083', 'id-checksum'],
    ['idNumber', '0402295009086', 'id-date-mismatch'],
    ['idNumber', '9003155009280', 'id-not-recognised'],
    ['agreeClubRules', '', 'consent-required'],
    ['agreeAnnexures', '', 'consent-required'],
    ['agreeConstitution', '', 'consent-required'],
  ])('maps %s of "%s" to %s', (field, value, expected) => {
    const outcome = validateMemberDetails({ ...VALID, [field]: value }, DOB)

    expect(reasonFor(outcome, field)).toBe(expected)
  })
})

describe('a nickname already held by another member', () => {
  // Criterion 44.
  test('is refused as unavailable', () => {
    const outcome = validateMemberDetails(VALID, DOB, ['greenthumb'])

    expect(reasonFor(outcome, 'nickname')).toBe('nickname-unavailable')
  })

  test('is matched without regard to letter case', () => {
    const outcome = validateMemberDetails({ ...VALID, nickname: 'GREENTHUMB' }, DOB, ['greenthumb'])

    expect(reasonFor(outcome, 'nickname')).toBe('nickname-unavailable')
  })

  test('does not refuse a nickname nobody holds', () => {
    expect(validateMemberDetails(VALID, DOB, ['someoneelse']).status).toBe('accepted')
  })

  test('is unaffected by an empty list of held nicknames', () => {
    expect(validateMemberDetails(VALID, DOB, []).status).toBe('accepted')
  })
})

describe('reading the submission', () => {
  const formData = (entries: Readonly<Record<string, string>>) => {
    const data = new FormData()

    for (const [name, value] of Object.entries(entries)) data.append(name, value)

    return data
  }

  test('reads every field the form sends, the hidden version fields included', () => {
    expect(readMemberDetailsInput(formData(VALID_FORM))).toEqual(VALID)
  })

  // Criterion 42.
  test('reads an absent field as empty, so it is refused as missing', () => {
    const input = readMemberDetailsInput(formData({ firstName: 'Thandiwe' }))

    expect(input.idNumber).toBe('')
    expect(reasonFor(validateMemberDetails(input, DOB), 'idNumber')).toBe('id-missing')
  })

  test('reads a file in a text field as no answer at all', () => {
    const data = new FormData()
    data.append('idNumber', new File(['9003155009082'], 'id.txt'))

    expect(readMemberDetailsInput(data).idNumber).toBe('')
  })

  test('refuses an entirely empty submission on every field', () => {
    const outcome = validateMemberDetails(readMemberDetailsInput(new FormData()), DOB)

    expect(refusals(outcome)).toHaveLength(MEMBER_DETAILS_FIELDS.length)
  })
})

describe('refusals travelling in the query string', () => {
  /*
   * Criterion 40. The no-script path sends the visitor back with reason codes and nothing else:
   * never a name, never an email address, and above all never an identity number, which would
   * otherwise land in every access log between the browser and the server.
   */
  test('are written as field and reason pairs', () => {
    expect(
      serialiseMemberDetailsRefusals([
        { field: 'firstName', reason: 'name-missing' },
        { field: 'idNumber', reason: 'id-checksum' },
      ]),
    ).toBe('firstName:name-missing,idNumber:id-checksum')
  })

  test('come back as they went out', () => {
    const refusals = [
      { field: 'nickname', reason: 'nickname-unavailable' },
      { field: 'mobile', reason: 'mobile-not-a-mobile' },
    ] as const

    expect(parseMemberDetailsRefusals(serialiseMemberDetailsRefusals(refusals))).toEqual(refusals)
  })

  test('are empty when there is no parameter', () => {
    expect(parseMemberDetailsRefusals(undefined)).toEqual([])
    expect(parseMemberDetailsRefusals('')).toEqual([])
  })

  test('drop anything that is not a field this form has', () => {
    expect(parseMemberDetailsRefusals('password:name-missing')).toEqual([])
  })

  test('drop anything that is not a refusal this form can produce', () => {
    expect(parseMemberDetailsRefusals('firstName:not-good-enough')).toEqual([])
  })

  test('drop a malformed pair rather than guessing at it', () => {
    expect(parseMemberDetailsRefusals('firstName,idNumber:id-checksum')).toEqual([
      { field: 'idNumber', reason: 'id-checksum' },
    ])
  })

  test('ignore a repeated parameter, which arrives as a list rather than a string', () => {
    expect(parseMemberDetailsRefusals(['firstName:name-missing'])).toEqual([])
  })

  test('report each field once, however many times it appears', () => {
    expect(parseMemberDetailsRefusals('firstName:name-missing,firstName:name-too-long')).toEqual([
      { field: 'firstName', reason: 'name-missing' },
    ])
  })
})

describe('the three club document agreements', () => {
  const CONSENT_FIELDS = ['agreeClubRules', 'agreeAnnexures', 'agreeConstitution'] as const

  test('are each refused when the box was not ticked', () => {
    // Club documents criterion 8.
    for (const field of CONSENT_FIELDS) {
      const outcome = validateMemberDetails({ ...VALID, [field]: '' }, DOB)

      expect(reasonFor(outcome, field)).toBe('consent-required')
      expect(outcome.status).toBe('refused')
    }
  })

  test('are refused one by one rather than as a single objection', () => {
    // Club documents criterion 9. Three documents, three things to do about it.
    const outcome = validateMemberDetails(
      { ...VALID, agreeClubRules: '', agreeAnnexures: '', agreeConstitution: '' },
      DOB,
    )

    expect(refusals(outcome)).toEqual([
      { field: 'agreeClubRules', reason: 'consent-required' },
      { field: 'agreeAnnexures', reason: 'consent-required' },
      { field: 'agreeConstitution', reason: 'consent-required' },
    ])
  })

  test('are reported after the six details, which is the order the form reads', () => {
    // Club documents criterion 11.
    const outcome = validateMemberDetails({ ...VALID, firstName: '', agreeAnnexures: '' }, DOB)

    expect(refusals(outcome).map((entry) => entry.field)).toEqual(['firstName', 'agreeAnnexures'])
  })

  test.each(['on', 'true', '1', 'YES'])('are refused for a posted value of %o', (value) => {
    // Club documents criterion 12: refused rather than interpreted.
    expect(reasonFor(validateMemberDetails({ ...VALID, agreeClubRules: value }, DOB), 'agreeClubRules')).toBe(
      'consent-required',
    )
  })

  test('are carried on an accepted submission, naming the document and the revision', () => {
    // Club documents criterion 24.
    expect(accepted(validateMemberDetails(VALID, DOB))?.consents).toEqual([
      { document: 'club-rules', version: '1' },
      { document: 'annexures', version: '1' },
      { document: 'constitution', version: '1' },
    ])
  })

  test('carry no timestamp, because the moment of agreement is the moment of the write', () => {
    /*
     * Club documents criterion 25. A time stamped by the rules and a time written to the row are
     * two times that will eventually disagree, and this function is pure.
     */
    for (const consent of accepted(validateMemberDetails(VALID, DOB))?.consents ?? []) {
      expect(Object.keys(consent).sort()).toEqual(['document', 'version'])
    }
  })

  test('carry nothing at all when one of them was refused', () => {
    expect(accepted(validateMemberDetails({ ...VALID, agreeConstitution: '' }, DOB))).toBeNull()
  })

  test('record the revision in force, not the one the form carried', () => {
    /*
     * The version is read from the revisions the caller was given rather than echoed back from the
     * submission, so a forged hidden field cannot file an agreement against a version of its own
     * choosing. It has to match the live one to be accepted at all — the case below.
     */
    const outcome = validateAgainst(
      { ...VALID, versions: { 'club-rules': '4', annexures: '4', constitution: '4' } },
      DOB,
      clubDocumentRevisions({ 'club-rules': '4', annexures: '4', constitution: '4' }),
    )

    expect(accepted(outcome)?.consents).toEqual([
      { document: 'club-rules', version: '4' },
      { document: 'annexures', version: '4' },
      { document: 'constitution', version: '4' },
    ])
  })

  test('are refused when the document was revised while the form was open', () => {
    /*
     * The member did tick the box, and the box was beside different words. Refused rather than
     * quietly recorded against the new revision, which would attribute an agreement to text they
     * never read — the one thing the whole ledger exists to prevent.
     */
    const outcome = validateAgainst(VALID, DOB, clubDocumentRevisions({ constitution: '2' }))

    expect(reasonFor(outcome, 'agreeConstitution')).toBe('consent-superseded')
    expect(accepted(outcome)).toBeNull()
  })

  test('leave the documents that did not move alone', () => {
    // One stale document is one refusal, not three.
    const outcome = validateAgainst(VALID, DOB, clubDocumentRevisions({ annexures: '2' }))

    expect(refusals(outcome).map((entry) => entry.field)).toEqual(['agreeAnnexures'])
  })

  test('are refused as unticked before they are refused as stale', () => {
    /*
     * An unticked box is what the member has to do something about. Telling them the document
     * changed as well would be true and useless.
     */
    const outcome = validateAgainst(
      { ...VALID, agreeAnnexures: '' },
      DOB,
      clubDocumentRevisions({ annexures: '2' }),
    )

    expect(reasonFor(outcome, 'agreeAnnexures')).toBe('consent-required')
  })

  test('are refused when the form carried no version at all', () => {
    // A hand-crafted POST, or a form served before the hidden fields existed.
    const outcome = validateAgainst({ ...VALID, versions: {} }, DOB, REVISIONS)

    expect(refusals(outcome).map((entry) => entry.reason)).toEqual([
      'consent-superseded',
      'consent-superseded',
      'consent-superseded',
    ])
  })

  test('travel back through the query string like any other refusal', () => {
    // Club documents criterion 14: the no-script path, and still no value the member typed.
    const round = parseMemberDetailsRefusals(
      serialiseMemberDetailsRefusals([
        { field: 'agreeConstitution', reason: 'consent-required' },
      ]),
    )

    expect(round).toEqual([{ field: 'agreeConstitution', reason: 'consent-required' }])
  })
})

describe('refusals from two sources', () => {
  /*
   * The rules decide most of them; a question put to the API while the form was open decides one.
   * The error summary reads as a list of what to fix, so they have to arrive as one ordered list.
   */
  test('are merged in the order the form shows the fields', () => {
    const merged = mergeMemberDetailsRefusals(
      [{ field: 'agreeAnnexures', reason: 'consent-required' }],
      [{ field: 'nickname', reason: 'nickname-unavailable' }],
      [{ field: 'firstName', reason: 'name-missing' }],
    )

    expect(merged.map((entry) => entry.field)).toEqual([
      'firstName',
      'nickname',
      'agreeAnnexures',
    ])
  })

  test('give a field one message, and it is the earlier argument’s', () => {
    /*
     * A nickname that is malformed *and* reported taken is malformed. Fixing the shape is the
     * instruction that makes sense, and "that nickname is taken" about a value nobody could hold
     * is untrue.
     */
    const merged = mergeMemberDetailsRefusals(
      [{ field: 'nickname', reason: 'nickname-shape' }],
      [{ field: 'nickname', reason: 'nickname-unavailable' }],
    )

    expect(merged).toEqual([{ field: 'nickname', reason: 'nickname-shape' }])
  })

  test('are nothing when neither source refused anything', () => {
    expect(mergeMemberDetailsRefusals([], [])).toEqual([])
  })

  test('survive a source being the only one with anything to say', () => {
    expect(mergeMemberDetailsRefusals([], [{ field: 'nickname', reason: 'nickname-unavailable' }]))
      .toEqual([{ field: 'nickname', reason: 'nickname-unavailable' }])
  })
})

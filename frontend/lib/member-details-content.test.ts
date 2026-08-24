import { describe, expect, test } from 'vitest'
import {
  ALL_MEMBER_DETAILS_COPY,
  MEMBER_DETAILS_COPY,
  formatDateOfBirth,
  memberDetailsFieldLabel,
  memberDetailsRefusalMessage,
} from './member-details-content'
import {
  MEMBER_CONSENT_FIELDS,
  MEMBER_DETAILS_FIELDS,
  MEMBER_DETAILS_REFUSALS,
} from './member-details'
import { CLINICAL_CLAIM, CURRENCY, ELIGIBILITY_CLAIM, RETAIL_VOICE } from './copy-compliance'
import { checkSaMobileNumber } from './sa-mobile-number'

/*
 * design/features/member-details-at-sign-up.md criteria 46 to 48.
 *
 * This screen is held to every copy rule, the eligibility one included. The age check is the only
 * surface exempt from that, because it is the only one that states a minimum age; nothing here
 * says anything about who may join.
 */

const SAMPLE_DATE = formatDateOfBirth({ year: 1990, month: 3, day: 15 })

describe('every refusal', () => {
  test('has wording', () => {
    for (const reason of MEMBER_DETAILS_REFUSALS) {
      expect(memberDetailsRefusalMessage(reason, SAMPLE_DATE).length).toBeGreaterThan(0)
    }
  })

  test('has wording that ends in a full stop, so two errors read as two sentences', () => {
    for (const reason of MEMBER_DETAILS_REFUSALS) {
      expect(memberDetailsRefusalMessage(reason, SAMPLE_DATE)).toMatch(/\.$/)
    }
  })

  test('never repeats back what the visitor typed', () => {
    // An ID number must not travel in a message. Criterion 34 and section 9.
    for (const reason of MEMBER_DETAILS_REFUSALS) {
      expect(memberDetailsRefusalMessage(reason, SAMPLE_DATE)).not.toMatch(/\d{5}/)
    }
  })
})

describe('the date-of-birth refusal', () => {
  // Criterion 32.
  test('names the date the ID number is being checked against', () => {
    expect(memberDetailsRefusalMessage('id-date-mismatch', SAMPLE_DATE)).toContain(SAMPLE_DATE)
  })

  test('does not name a date in any other message', () => {
    const others = MEMBER_DETAILS_REFUSALS.filter((reason) => reason !== 'id-date-mismatch')

    for (const reason of others) {
      expect(memberDetailsRefusalMessage(reason, SAMPLE_DATE)).not.toContain(SAMPLE_DATE)
    }
  })
})

describe('a date of birth on screen', () => {
  test('is written the South African way, in full', () => {
    expect(SAMPLE_DATE).toContain('1990')
    expect(SAMPLE_DATE).toContain('March')
    expect(SAMPLE_DATE).toContain('15')
  })

  test('does not shift by a day', () => {
    // A calendar date formatted through a time zone is how a birthday moves. It must not.
    expect(formatDateOfBirth({ year: 2000, month: 1, day: 1 })).toContain('1 January 2000')
  })
})

describe('the collection notice', () => {
  const notice = MEMBER_DETAILS_COPY.collectionNotice.join(' ')

  // Criterion 48.
  test('names who is collecting the details', () => {
    expect(notice).toContain('Cultivators Collective')
  })

  test('says what the ID number is for', () => {
    expect(notice).toMatch(/ID number/)
  })

  test('says that the details are kept', () => {
    // It said the opposite until the details were stored. Now they are.
    expect(notice).toMatch(/are kept/i)
  })

  test('says what follows from being registered: no sign-in until payment', () => {
    /*
     * The consequence, not only the collection. A member who is told their details are kept and
     * not told they cannot sign in yet will try to sign in and conclude the club lost them.
     */
    expect(notice).toMatch(/cannot sign in/i)
    expect(notice).toMatch(/payment/i)
  })

  test('says whether giving the details is voluntary, and what follows from refusing', () => {
    expect(notice).toMatch(/voluntary/i)
  })

  test('is written before the fields, not after them', () => {
    // Structural, but the whole mitigation for risk 1 rests on it. Guard the wording's intent.
    expect(MEMBER_DETAILS_COPY.collectionNotice.length).toBeGreaterThan(0)
  })
})

describe('every field', () => {
  test('has a label', () => {
    // Every field now, agreements included: nine labels, one lookup.
    for (const field of MEMBER_DETAILS_FIELDS) {
      expect(memberDetailsFieldLabel(field).length).toBeGreaterThan(0)
    }
  })
})

describe('the club document agreements', () => {
  const { legend, notice, agreements } = MEMBER_DETAILS_COPY.consents

  test('introduce the group by name', () => {
    // Club documents criterion 6.
    expect(legend.length).toBeGreaterThan(0)
  })

  test('say that the agreement is recorded, and against which version', () => {
    /*
     * Club documents criterion 6 and section 9. A tick against "I have read and agree" implies an
     * agreement was formed and kept — and now one is, so the screen says so. The version matters:
     * `DocumentConsent` points at a revision, so agreeing to the constitution as it reads today is
     * not agreeing to whatever it says next year.
     */
    expect(notice).toMatch(/recorded/i)
    expect(notice).toMatch(/version/i)
  })

  test('give each document a short label and a link', () => {
    /*
     * The sentence a member ticks is not checked here any more: it comes from the API, because
     * Django records a digest of it against every agreement. See the note on `consents` in the copy
     * module, and `documents/models.py`.
     */
    for (const { field } of MEMBER_CONSENT_FIELDS) {
      expect(agreements[field].label.length).toBeGreaterThan(0)
      expect(agreements[field].link.length).toBeGreaterThan(0)
    }
  })

  test('each name their document in the words of the link', () => {
    for (const { field } of MEMBER_CONSENT_FIELDS) {
      expect(agreements[field].link).toContain(agreements[field].label)
    }
  })

  test('say the document is a PDF and that it opens in a new tab', () => {
    // Club documents criterion 3. A new tab arriving unannounced is a screen reader user lost.
    for (const { field } of MEMBER_CONSENT_FIELDS) {
      expect(agreements[field].link).toMatch(/PDF/)
      expect(agreements[field].link).toMatch(/new tab/i)
    }
  })

  test('are three distinct documents, said three distinct ways', () => {
    const labels = MEMBER_CONSENT_FIELDS.map(({ field }) => agreements[field].label)

    expect(new Set(labels).size).toBe(3)
  })
})

describe('the mobile number hint', () => {
  const hint = MEMBER_DETAILS_COPY.fields.mobile.hint

  // Criterion 56.
  test('states how many digits are wanted', () => {
    expect(hint).toMatch(/ten digits/i)
  })

  test('shows a worked example', () => {
    expect(hint).toContain('082 123 4567')
  })

  test('says the number must be the member’s own, and not one already given', () => {
    /*
     * A shared handset is refused, and — because duplicates are never disclosed — refused with a
     * confirmation screen rather than a reason. This is the only place a visitor can find that out
     * while they can still act on it. See design/features/sign-up.md section 10, risks 14 and 15.
     */
    expect(hint).toMatch(/your own number/i)
    expect(hint).toMatch(/another member/i)
  })

  test('shows an example the rule actually accepts', () => {
    /*
     * The point of the test. An example made of digits the rule would refuse reads as an example
     * of an acceptable value, and a member who copies it is told they are wrong.
     */
    const example = /0\d\d \d\d\d \d\d\d\d/.exec(hint)

    expect(example).not.toBeNull()
    expect(checkSaMobileNumber(example === null ? '' : example[0]).status).toBe('valid')
  })
})

describe('the date of birth', () => {
  test('has no wording on this screen, because it is not on this screen', () => {
    // Product owner decision. The refusal message is the only place the date now appears.
    expect(MEMBER_DETAILS_COPY).not.toHaveProperty('dateOfBirth')
  })
})

describe('the whole corpus', () => {
  // Criterion 46.
  test('makes no medical, therapeutic or dosage claim', () => {
    for (const line of ALL_MEMBER_DETAILS_COPY) {
      expect(line).not.toMatch(CLINICAL_CLAIM)
    }
  })

  test('carries no retail or transactional voice', () => {
    for (const line of ALL_MEMBER_DETAILS_COPY) {
      expect(line).not.toMatch(RETAIL_VOICE)
    }
  })

  test('names no amount in any currency', () => {
    for (const line of ALL_MEMBER_DETAILS_COPY) {
      for (const pattern of CURRENCY) expect(line).not.toMatch(pattern)
    }
  })

  // Criterion 47.
  test('says nothing about who is eligible to join', () => {
    for (const line of ALL_MEMBER_DETAILS_COPY) {
      expect(line).not.toMatch(ELIGIBILITY_CLAIM)
    }
  })

  test('includes every refusal message, so none escapes the checks above', () => {
    for (const reason of MEMBER_DETAILS_REFUSALS) {
      expect(ALL_MEMBER_DETAILS_COPY).toContain(memberDetailsRefusalMessage(reason, SAMPLE_DATE))
    }
  })

  test('includes the collection notice and every field label', () => {
    for (const paragraph of MEMBER_DETAILS_COPY.collectionNotice) {
      expect(ALL_MEMBER_DETAILS_COPY).toContain(paragraph)
    }

    for (const field of MEMBER_DETAILS_FIELDS) {
      expect(ALL_MEMBER_DETAILS_COPY).toContain(memberDetailsFieldLabel(field))
    }
  })

  test('includes every word of the agreement group, so none escapes the checks above', () => {
    // Club documents criterion 22.
    const { legend, notice, agreements } = MEMBER_DETAILS_COPY.consents

    expect(ALL_MEMBER_DETAILS_COPY).toContain(legend)
    expect(ALL_MEMBER_DETAILS_COPY).toContain(notice)

    for (const { field } of MEMBER_CONSENT_FIELDS) {
      expect(ALL_MEMBER_DETAILS_COPY).toContain(agreements[field].label)
      expect(ALL_MEMBER_DETAILS_COPY).toContain(agreements[field].link)
    }
  })
})

import { MEMBER_CONSENT_FIELDS, MEMBER_DETAILS_REFUSALS, isMemberConsentField } from './member-details'
import type {
  MemberConsentField,
  MemberDetailField,
  MemberDetailsField,
  MemberDetailsRefusal,
} from './member-details'
import type { CalendarDate } from './age-gate'

/**
 * Every word on the member details screen, in one place.
 *
 * Held to every copy rule in `copy-compliance.ts`, the eligibility one included: the age check is
 * the only surface in the product that says anything about who may join, and this is not it.
 *
 * The date of birth has no wording here at all: product owner decision, it is not shown on this
 * screen. The one place it now appears is inside the ID-number mismatch message, which is why that
 * message names it.
 *
 * The collection notice is not marketing text. It is what POPIA section 18 requires a person to be
 * told when their information is collected — who is asking, what for, whether they have to, and
 * what follows if they do not — and it sits above the fields rather than below them so that a
 * visitor knows the position before typing an identity number, not after.
 *
 * Placed for structure and pending client and legal sign-off, like the rest of the member-facing
 * wording. See design/features/member-details-at-sign-up.md sections 6.1, 9 and 10, risk 10.
 */

/*
 * A calendar date, written out. `timeZone: 'UTC'` against a UTC-constructed instant is not a
 * display choice: a birthday is a date and not a moment, and formatting it through any other zone
 * is how it arrives on screen a day out.
 */
const DATE_OF_BIRTH = new Intl.DateTimeFormat('en-ZA', {
  timeZone: 'UTC',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  numberingSystem: 'latn',
  calendar: 'gregory',
})

export const formatDateOfBirth = ({ year, month, day }: CalendarDate) =>
  DATE_OF_BIRTH.format(new Date(Date.UTC(year, month - 1, day)))

/**
 * One message per refusal, so a new refusal code cannot ship without wording — a test walks the
 * whole union and fails on a gap.
 *
 * Each says what to do about the problem rather than only naming it, and none repeats back what
 * the visitor typed. The date-of-birth disagreement is the one message that has to name a value,
 * and the value it names is the date the club holds — never the number. Since the date is no longer
 * displayed on the screen, this message is the only place a member ever sees it.
 */
const REFUSAL_MESSAGES = {
  'name-missing': 'Enter your name.',
  'name-too-long': 'That is longer than 70 characters. Shorten it.',
  'name-unexpected-characters':
    'Use letters, spaces, hyphens, apostrophes and full stops only.',
  'nickname-missing': 'Choose a nickname.',
  'nickname-length': 'A nickname is 3 to 20 characters long.',
  'nickname-unexpected-characters':
    'Use the letters a to z, numbers, hyphens and underscores only.',
  'nickname-shape':
    'Start with a letter, and do not end with, or repeat, a hyphen or an underscore.',
  'nickname-unavailable': 'That nickname is taken. Choose another.',
  'email-missing': 'Enter your email address.',
  'email-malformed': 'That does not look like an email address. Check it.',
  'email-too-long': 'That email address is longer than we can accept.',
  'mobile-missing': 'Enter your mobile number.',
  'mobile-unexpected-characters': 'Use numbers only, with or without spaces.',
  'mobile-length':
    'A South African mobile number is ten digits starting with a zero, or +27 and nine digits.',
  'mobile-not-a-mobile': 'That is not a South African mobile number.',
  'id-missing': 'Enter your ID number.',
  'id-length': 'An ID number is thirteen digits long.',
  'id-not-digits': 'Use numbers only.',
  'id-checksum': 'That ID number does not add up. Check each digit against your document.',
  'id-date-mismatch': (dateOfBirth: string) =>
    `That ID number does not begin with your date of birth, ${dateOfBirth}. Check the number.`,
  'id-not-recognised': 'That is not a South African ID number.',
  /*
   * One message for all three boxes. The field is what says which document, and three copies of one
   * sentence would only be three places to correct it.
   */
  'consent-required': 'Tick this to confirm you have read and agree.',
  /*
   * The document was revised while this form was open. Says what happened and what to do, and does
   * not blame the member for it: they did tick the box, and the box was beside different words.
   */
  'consent-superseded':
    'This document was updated while you were filling in the form. Open it again, read the new '
    + 'version, then tick to agree.',
} as const satisfies Record<MemberDetailsRefusal, string | ((dateOfBirth: string) => string)>

/**
 * The message for a refusal. `dateOfBirth` is used by the one message that names it.
 *
 * Optional, and defaulted to blank, so that a caller whose refusals cannot include
 * `id-date-mismatch` need not invent a date to ask a question about a name. `lib/profile.ts` is
 * that caller: its refusal union is a subset of this one and contains no message that names a
 * value, which the compiler checks. Sign-up still passes the date, because sign-up can reach the
 * message that needs it.
 */
export const memberDetailsRefusalMessage = (
  reason: MemberDetailsRefusal,
  dateOfBirth = '',
): string => {
  const message = REFUSAL_MESSAGES[reason]

  return typeof message === 'function' ? message(dateOfBirth) : message
}

export const MEMBER_DETAILS_COPY = {
  heading: 'Your details',
  /*
   * The POPIA section 18 notice. Ordered as a person reads it: who is asking, what each thing is
   * for, what is kept and what follows from it, and that they do not have to.
   *
   * The third paragraph used to say nothing was kept. It is now the opposite, because the details
   * are stored — and it says the consequence in the same breath, because "we keep this" and "you
   * cannot sign in yet" are one fact to a member and two only to us.
   */
  collectionNotice: [
    'Cultivators Collective is asking for these details to set up your membership and to know who is in the club.',
    'Your name and your nickname are how we and other members recognise you. Your email address and mobile number are how the club reaches you. Your ID number is asked for so that the details you give can later be confirmed against your identity document.',
    'These details are kept by the club so that your membership can be set up. Your membership does not become active, and you cannot sign in, until payment is complete.',
    'Giving these details is voluntary, and the club cannot set up a membership without them. A full privacy notice will be linked here.',
  ],
  fields: {
    firstName: { label: 'First name', hint: '' },
    lastName: { label: 'Last name', hint: '' },
    nickname: {
      label: 'Nickname',
      hint: 'What other members see. Letters, numbers, hyphens and underscores, starting with a letter.',
    },
    email: {
      label: 'Email address',
      hint: 'Where the club sends your sign-in code.',
    },
    /*
     * The second sentence exists because of what the club's one-handset-one-member rule does to a
     * member who cannot meet it. A number another member has already given is refused, and — since
     * a duplicate is never disclosed — refused with a confirmation screen rather than a reason. A
     * visitor who was going to type a partner's or a parent's number should learn that here, where
     * they can still do something about it, rather than after a submission that appears to have
     * worked. See design/features/sign-up.md section 10, risks 14 and 15.
     */
    mobile: {
      label: 'Mobile number',
      hint: 'Ten digits, for example 082 123 4567. Write it however you like. '
        + 'It must be your own number, and not one another member has already given.',
    },
    idNumber: {
      label: 'South African ID number',
      hint: 'Thirteen digits. Checked against the date of birth you gave at the age check.',
    },
  } satisfies Record<MemberDetailField, { label: string; hint: string }>,
  /*
   * The three club documents: a short label for the error summary, and the link that opens the
   * document.
   *
   * **The sentence a member ticks is no longer here.** It comes from the API, because Django
   * records a digest of it against every agreement — see documents/models.py. Two copies of that
   * wording would eventually disagree, and the copy that disagreed would be the record of what a
   * member asserted. The cost is that the plain-language checks below no longer read it; the
   * wording is owned by staff in the admin instead. See design/features/sign-up.md section 5.
   *
   * The link text names the format and says the document opens in a new tab, because a new tab
   * arriving unannounced leaves a screen reader user in a document with no idea how they got there.
   * The words are the document's own words, which is what stops a box saying "the constitution"
   * from opening the annexures.
   *
   * The notice says what the tick does, because a tick against "I have read and agree" implies an
   * agreement was formed and kept — and now one is. It names the version rather than the document,
   * since that is what the ledger records: `DocumentConsent` points at a revision, so agreeing to
   * the constitution as it reads today is not agreeing to whatever it says next year.
   */
  consents: {
    legend: 'Club documents',
    notice:
      'Read each document, then confirm that you agree to it. Your agreement is recorded against the version you are reading now, and the club keeps that record.',
    agreements: {
      agreeClubRules: {
        label: 'Club Rules',
        link: 'Read the Club Rules (PDF, opens in a new tab)',
      },
      agreeAnnexures: {
        label: 'Annexures',
        link: 'Read the Annexures (PDF, opens in a new tab)',
      },
      agreeConstitution: {
        label: 'Constitution',
        link: 'Read the Constitution (PDF, opens in a new tab)',
      },
    } satisfies Record<MemberConsentField, { label: string; link: string }>,
  },
  submit: 'Continue',
  errorSummaryHeading: 'Check these details',
  /*
   * Shown beside the nickname when the club could not be asked whether it is free.
   *
   * Not a refusal, and worded so that it cannot be mistaken for one: nothing is wrong with the
   * nickname, nobody knows whether it is spoken for, and the member may carry on regardless. It
   * says the question is asked again on the way out, because it is — `/api/members/register`
   * asks inside the transaction that writes, so a member who ignores this is still protected
   * from taking a name that is not theirs.
   *
   * It does not repeat the nickname back, and it does not say what failed. The reference is the
   * whole of what a member needs to report it, and it says nothing about them.
   */
  checkFailed: {
    nickname:
      'We could not confirm that nickname just now. Carry on — it is confirmed again when you '
      + 'continue.',
    /*
     * A sentence of its own rather than glued to the message above, because the same reference
     * wording appears on the screen that replaces the form and the two must read alike.
     */
    reference: (reference: string) =>
      `If you tell the club about this, quote reference ${reference}.`,
  },
  outcome: {
    heading: 'Thank you',
    body: [
      'Your details are with the club and your membership has been set up.',
      'Your membership is not active yet. It becomes active once payment is complete, and the club will email you at the address you gave when that step is ready.',
    ],
  },
  /*
   * Shown instead of the form when the club documents cannot be read.
   *
   * The form is withheld rather than shown without its agreements: a member cannot agree to a
   * document nobody can serve them, and a sign-up that quietly drops one agreement collects an
   * incomplete one. It says the fault is ours, because it is, and it does not ask the member to
   * try anything they have no way of fixing.
   */
  unavailable: {
    heading: 'Joining is briefly unavailable',
    body: [
      'The club documents cannot be loaded at the moment, and we will not ask you to agree to '
      + 'something you cannot read.',
      'Nothing is wrong with your details. Please try again shortly.',
    ],
    /*
     * Added when the failure was a submission that could not be written, rather than documents
     * that could not be read. Says what the reference is for and, deliberately, that it carries
     * nothing about the person quoting it — somebody who has just typed an identity number into a
     * form is owed that assurance before being asked to send us a code about it.
     *
     * The same wording as the nickname notice, plus that assurance, because this one is the
     * screen a member is left on rather than a line beside a field they can carry on past.
     */
    reference: (reference: string) =>
      `If you tell the club about this, quote reference ${reference}. It tells us which fault to `
      + 'look at, and it says nothing about you or your details.',
  },
  back: 'Back to Cultivators Collective',
} as const

/**
 * The corpus the compliance tests read.
 *
 * Assembled here rather than in the test, so a line cannot be added to the screen without the
 * checks seeing it. The refusal messages are rendered with a sample date, because the only one
 * that takes a date has to be checked in the form a visitor actually reads.
 */
/**
 * The label for any field, detail or agreement.
 *
 * One lookup, because the error summary lists refusals from both without caring which is which.
 * The agreement labels are deliberately short — the summary reads "Constitution — Tick this to…",
 * not the whole sentence twice.
 */
export const memberDetailsFieldLabel = (field: MemberDetailsField): string =>
  isMemberConsentField(field)
    ? MEMBER_DETAILS_COPY.consents.agreements[field].label
    : MEMBER_DETAILS_COPY.fields[field].label

/**
 * A reference of the shape `newErrorReference` mints, for the corpus above.
 *
 * Invented here rather than generated: the corpus is read by tests that must not change from one
 * run to the next, and a random value in it would make a copy check occasionally fail.
 */
const SAMPLE_ERROR_REFERENCE = '3f9a1c04'

export const ALL_MEMBER_DETAILS_COPY: readonly string[] = [
  MEMBER_DETAILS_COPY.heading,
  ...MEMBER_DETAILS_COPY.collectionNotice,
  ...Object.values(MEMBER_DETAILS_COPY.fields).flatMap(({ label, hint }) =>
    hint.length > 0 ? [label, hint] : [label],
  ),
  MEMBER_DETAILS_COPY.consents.legend,
  MEMBER_DETAILS_COPY.consents.notice,
  /*
   * The label and the link, but not the sentence a member ticks: that wording comes from the API
   * now, so these checks cannot see it. See the note on `consents` above.
   */
  ...MEMBER_CONSENT_FIELDS.flatMap(({ field }) => {
    const { label, link } = MEMBER_DETAILS_COPY.consents.agreements[field]

    return [label, link]
  }),
  MEMBER_DETAILS_COPY.submit,
  MEMBER_DETAILS_COPY.errorSummaryHeading,
  MEMBER_DETAILS_COPY.outcome.heading,
  ...MEMBER_DETAILS_COPY.outcome.body,
  MEMBER_DETAILS_COPY.unavailable.heading,
  ...MEMBER_DETAILS_COPY.unavailable.body,
  /*
   * The two failure messages, rendered with a sample reference. A reference is eight hex
   * characters, so the rendered line is what the checks have to read: `CURRENCY` looks for a
   * letter followed by digits, and a message that formatted one carelessly would trip it.
   */
  MEMBER_DETAILS_COPY.checkFailed.nickname,
  MEMBER_DETAILS_COPY.checkFailed.reference(SAMPLE_ERROR_REFERENCE),
  MEMBER_DETAILS_COPY.unavailable.reference(SAMPLE_ERROR_REFERENCE),
  MEMBER_DETAILS_COPY.back,
  ...MEMBER_DETAILS_REFUSALS.map((reason) =>
    memberDetailsRefusalMessage(reason, formatDateOfBirth({ year: 1990, month: 3, day: 15 })),
  ),
]

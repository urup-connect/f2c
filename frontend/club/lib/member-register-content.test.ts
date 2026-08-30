import { describe, expect, test } from 'vitest'

import {
  CLINICAL_CLAIM,
  CURRENCY,
  ELIGIBILITY_CLAIM,
  THERAPEUTIC_CLAIM,
} from './copy-compliance'
import {
  ALL_MEMBER_REGISTER_COPY,
  MEMBER_IDENTITY,
  MEMBER_MEMBERSHIP,
  MEMBER_RECORD,
  MEMBER_REGISTER,
  MEMBER_STANDING,
} from './member-register-content'

/*
 * The administrator's membership screens.
 *
 * ## The compliance position, and how it differs from the catalogue's
 *
 * `strain-catalogue-content.ts` is out of `CLINICAL_CLAIM` because it has to
 * label the `thc_content` and `cbd_content` columns, and that scope is asserted
 * in its own test file so it cannot spread by drift.
 *
 * **This corpus takes no such scope.** It is held to `CLINICAL_CLAIM` in full,
 * along with the three rules the catalogue also keeps. There is nothing on a
 * membership register that needs to name a cannabinoid, quote an amount or
 * describe who may join — and a rule that is easy to keep should be kept rather
 * than relaxed by association with the file next to it. The first test below is
 * what stops somebody assuming otherwise.
 *
 * `RETAIL_VOICE` is the one pattern this is not held to, and the club area is
 * already exempt for the same reason: an administrative screen has to say
 * "order", "stock" and "delivery" because those are the club's own nouns for its
 * own records.
 */

describe('the corpus', () => {
  test('gathers every line as a string', () => {
    expect(ALL_MEMBER_REGISTER_COPY.length).toBeGreaterThan(60)
    for (const line of ALL_MEMBER_REGISTER_COPY) expect(typeof line).toBe('string')
  })

  test('has no blank line', () => {
    // A key added and left empty renders as a label with no text, which reads as
    // a broken field rather than as an omission.
    for (const line of ALL_MEMBER_REGISTER_COPY) expect(line.trim()).not.toBe('')
  })
})

describe('the compliance rules this corpus is held to', () => {
  test('takes no cannabinoid-vocabulary scope, unlike the catalogue’s copy', () => {
    // The assertion that keeps the two corpora honest. The catalogue's scope is
    // about columns it has to name; nothing here names one, so the full rule
    // applies and this test is what fails if a line ever needs it not to.
    for (const line of ALL_MEMBER_REGISTER_COPY) {
      expect(line, line).not.toMatch(CLINICAL_CLAIM)
    }
  })

  test('makes no therapeutic claim', () => {
    for (const line of ALL_MEMBER_REGISTER_COPY) {
      expect(line, line).not.toMatch(THERAPEUTIC_CLAIM)
    }
  })

  test('names no amount, in any currency', () => {
    // A subscription's amount is on the record and never in the copy: what this
    // screen answers is whether somebody may be here, and the money belongs to
    // permissions this router does not hold.
    for (const line of ALL_MEMBER_REGISTER_COPY) {
      for (const pattern of CURRENCY) expect(line, line).not.toMatch(pattern)
    }
  })

  test('says nothing about who may join', () => {
    for (const line of ALL_MEMBER_REGISTER_COPY) {
      expect(line, line).not.toMatch(ELIGIBILITY_CLAIM)
    }
  })
})

describe('the register', () => {
  test('says that appointing a role is not done here', () => {
    // The first thing an administrator will look for and not find. Saying where
    // it is beats leaving them to hunt for a dropdown.
    expect(MEMBER_REGISTER.standfirst).toMatch(/authority/i)
    expect(MEMBER_REGISTER.standfirst).toMatch(/by hand/i)
  })

  test('warns that a partial identity number matches nothing', () => {
    // The blind index is exact-match only. An administrator who types the first
    // six digits and gets no rows would otherwise conclude the member is absent.
    expect(MEMBER_REGISTER.searchHint).toMatch(/exactly/i)
    expect(MEMBER_REGISTER.searchHint).toMatch(/partial/i)
  })

  test('labels every column it draws', () => {
    for (const label of [
      MEMBER_REGISTER.columnMember,
      MEMBER_REGISTER.columnRole,
      MEMBER_REGISTER.columnStatus,
      MEMBER_REGISTER.columnMembership,
      MEMBER_REGISTER.columnContact,
      MEMBER_REGISTER.columnJoined,
    ]) {
      expect(label.length).toBeGreaterThan(0)
    }
  })

  test('says what a status that blocks a sign-in means', () => {
    // Five of the six do, and nothing about a label like "Pending payment" says
    // which side of the line it is on.
    expect(MEMBER_REGISTER.cannotSignIn).toMatch(/sign in/i)
  })

  test('distinguishes an empty register from an empty filter', () => {
    expect(MEMBER_REGISTER.empty).not.toBe(MEMBER_REGISTER.emptyFiltered)
  })

  test('says a failed read failed, rather than reporting zero', () => {
    expect(MEMBER_REGISTER.loadFailed).toMatch(/could not/i)
  })

  test('explains an erased row rather than showing a blank one', () => {
    expect(MEMBER_REGISTER.erasedBadge).toMatch(/erased/i)
    expect(MEMBER_REGISTER.noContact).toMatch(/erased/i)
  })
})

describe('the record', () => {
  test('says which fields are set elsewhere, and where', () => {
    expect(MEMBER_RECORD.detailsStandfirst).toMatch(/role/i)
    expect(MEMBER_RECORD.detailsStandfirst).toMatch(/date of birth/i)
  })

  test('says a nickname may be left blank, and what happens then', () => {
    expect(MEMBER_RECORD.nicknameHint).toMatch(/blank/i)
    expect(MEMBER_RECORD.nicknameHint).toMatch(/full name/i)
  })

  test('warns what changing an address does', () => {
    // It is the sign-in identifier. An administrator fixing a typo should know
    // they are moving where the codes go.
    expect(MEMBER_RECORD.emailHint).toMatch(/sign-in codes/i)
  })

  test('gives the two read-only cases different words', () => {
    // An erased account and a sharing member are read-only for entirely
    // different reasons, and one message for both would explain neither.
    expect(MEMBER_RECORD.readOnlyErased).not.toBe(MEMBER_RECORD.readOnlySharing)
    expect(MEMBER_RECORD.readOnlyErased).toMatch(/erased/i)
    expect(MEMBER_RECORD.readOnlySharing).toMatch(/cultivator/i)
  })

  test('says why an erased row is still here', () => {
    expect(MEMBER_RECORD.readOnlyErased).toMatch(/history/i)
  })

  test('says the date of birth has not been checked against a document', () => {
    // `date_of_birth_verified_at` is left null by registration on purpose: a
    // number that passes its check digit is not a typo, and nobody has seen an
    // ID. The field the club would rely on later has to say so.
    expect(MEMBER_RECORD.birthUnverified).toMatch(/not yet checked/i)
    expect(MEMBER_RECORD.birthVerified).not.toBe(MEMBER_RECORD.birthUnverified)
  })

  test('says why the save button is inert', () => {
    expect(MEMBER_RECORD.unchanged.length).toBeGreaterThan(0)
  })
})

describe('the subscription card', () => {
  test('says which acts it deliberately does not offer', () => {
    // Cancelling and reversing belong to the platform operator under C2. A card
    // that was simply missing the buttons would read as unfinished.
    expect(MEMBER_MEMBERSHIP.standfirst).toMatch(/cancelling/i)
    expect(MEMBER_MEMBERSHIP.standfirst).toMatch(/platform operator/i)
  })
})

describe('the access card', () => {
  test('says outright that nothing is deleted', () => {
    expect(MEMBER_STANDING.standfirst).toMatch(/nothing is deleted/i)
  })

  test('says that a suspension ends every open session', () => {
    // The consequence an administrator cannot see from the record, and the one
    // that makes a suspension different from a status change.
    expect(MEMBER_STANDING.standfirst).toMatch(/ends every session/i)
  })

  test('says a suspension can be lifted, on the card that lifts it', () => {
    expect(MEMBER_STANDING.standfirst).toMatch(/lifted/i)
  })

  test('says erasure is a separate act done elsewhere', () => {
    expect(MEMBER_STANDING.standfirst).toMatch(/erasing/i)
  })

  test('says why an administrator is not offered self-suspension', () => {
    // A control that is simply missing reads as a screen that failed to draw.
    expect(MEMBER_STANDING.cannotSuspendSelf).toMatch(/sign you out/i)
  })

  test('confirms before suspending, and offers a way out that is not the action', () => {
    expect(MEMBER_STANDING.confirmSuspendHeading.length).toBeGreaterThan(0)
    expect(MEMBER_STANDING.confirmCancel).not.toBe(MEMBER_STANDING.confirmSuspendAction)
  })

  test('separates the standing from the event that produced it', () => {
    // Both appear after a suspension — one is the state and one is what just
    // happened — and the same sentence twice reads as the screen having drawn
    // something twice.
    expect(MEMBER_STANDING.suspended).not.toBe(MEMBER_STANDING.suspendedNow)
    expect(MEMBER_STANDING.suspendedNow).toMatch(/signed out/i)
  })
})

describe('the identity card', () => {
  test('says why the number is masked by default', () => {
    // The reasoning from `design/backend.md` section 10, in words an
    // administrator reads before they press the button rather than after.
    expect(MEMBER_IDENTITY.standfirst).toMatch(/last four/i)
    expect(MEMBER_IDENTITY.standfirst).toMatch(/cache/i)
  })

  test('says the read is recorded, before it is read', () => {
    expect(MEMBER_IDENTITY.standfirst).toMatch(/recorded/i)
    expect(MEMBER_IDENTITY.reasonHint).toMatch(/recorded/i)
  })

  test('says what is recorded alongside the reason', () => {
    expect(MEMBER_IDENTITY.reasonHint).toMatch(/your name/i)
    expect(MEMBER_IDENTITY.reasonHint).toMatch(/the time/i)
  })

  test('distinguishes an absent document from an unreadable one', () => {
    // Unrecoverable data reported as absent is the one outcome worse than the
    // problem itself: nobody would know to look.
    expect(MEMBER_IDENTITY.none).not.toBe(MEMBER_IDENTITY.unreadable)
    expect(MEMBER_IDENTITY.unreadable).toMatch(/somebody has to look/i)
  })

  test('names an auditor whose account is gone, rather than showing a blank', () => {
    expect(MEMBER_IDENTITY.historyUnknown.length).toBeGreaterThan(0)
  })
})

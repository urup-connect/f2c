import { describe, expect, test } from 'vitest'

import { ALL_CLUB_COPY } from './club-content'
import {
  CLINICAL_CLAIM,
  CURRENCY,
  ELIGIBILITY_CLAIM,
  THERAPEUTIC_CLAIM,
} from './copy-compliance'
import {
  ALL_CATALOGUE_COPY,
  CATALOGUE_LIST,
  OFFERS_CARD,
  PAIR_EDITOR,
  RETIRE_CARD,
  STRAIN_FORM,
  TERMS_SCREEN,
} from './strain-catalogue-content'

/*
 * The strain catalogue's administration screens.
 *
 * ## The compliance position, asserted rather than assumed
 *
 * This corpus is **not** in `ALL_CLUB_COPY` and is **not** held to
 * `CLINICAL_CLAIM`. That is a scope statement, not a fourth exemption, and the
 * tests below are what stop it becoming one by drift.
 *
 * `CLINICAL_CLAIM` bans two different things in one pattern: assertions about
 * what cannabis does to a person, and the vocabulary those assertions are built
 * from — `thc`, `cbd`, `potency`, `medic*`. Banning the vocabulary is right for a
 * product surface, where naming a cannabinoid is a step towards claiming
 * something about it. It is meaningless for a form whose only job is to record
 * the figure: `Strain.thc_content` is a column, an administrator has to be told
 * which field writes it, and `app/strains/models.py` already says "Typical THC,
 * as a percentage" in a `help_text` no rule here has ever governed.
 *
 * So this corpus is held to `THERAPEUTIC_CLAIM` instead, which is the assertion
 * half alone. That is the substantive rule and it is not relaxed: an
 * administrator reading "relieves anxiety" in a hint is an administrator who
 * will repeat it to a member.
 *
 * `CURRENCY` and `ELIGIBILITY_CLAIM` are **not** relaxed either, and neither
 * needs to be. This corpus talks about a grow price as a column without ever
 * naming an amount, and it says nothing at all about who may join.
 */

describe('the corpus and the club’s', () => {
  test('are two separate corpora', () => {
    expect(ALL_CATALOGUE_COPY.length).toBeGreaterThan(60)
    expect(ALL_CLUB_COPY.length).toBeGreaterThan(30)
  })

  test('keep the cannabinoid vocabulary out of the club’s corpus', () => {
    /*
     * The whole compliance position, as one assertion. A line that trips
     * `CLINICAL_CLAIM` may live here and must never reach `ALL_CLUB_COPY`, which
     * is held to that rule — so this is what fails if somebody folds the two
     * arrays together, and it fails here rather than as a puzzle over in
     * `club-content.test.ts`.
     *
     * Deliberately not asserted as "the two arrays share nothing". They share
     * "Name", "Remove" and "Saving…", because those are the words for those
     * things on any screen, and a rule that forced one corpus to invent a
     * synonym would be a rule about nothing.
     */
    const club = new Set(ALL_CLUB_COPY)
    const leaked = ALL_CATALOGUE_COPY.filter(
      (line) => CLINICAL_CLAIM.test(line) && club.has(line),
    )

    expect(leaked).toEqual([])
  })

  test('gathers every line as a string', () => {
    for (const line of ALL_CATALOGUE_COPY) expect(typeof line).toBe('string')
  })

  test('has no blank line', () => {
    // A key added and left empty renders as a label with no text, which reads as
    // a broken field rather than as an omission.
    for (const line of ALL_CATALOGUE_COPY) expect(line.trim()).not.toBe('')
  })
})

describe('the compliance rules this corpus is held to', () => {
  test('makes no therapeutic claim', () => {
    // The substantive half of `CLINICAL_CLAIM`, and not relaxed anywhere.
    for (const line of ALL_CATALOGUE_COPY) {
      expect(line, line).not.toMatch(THERAPEUTIC_CLAIM)
    }
  })

  test('names no amount, in any currency', () => {
    // Not relaxed. The corpus talks about a grow price as a column an
    // administrator does not set, and never quotes a figure.
    for (const line of ALL_CATALOGUE_COPY) {
      for (const pattern of CURRENCY) expect(line, line).not.toMatch(pattern)
    }
  })

  test('says nothing about who may join', () => {
    for (const line of ALL_CATALOGUE_COPY) {
      expect(line, line).not.toMatch(ELIGIBILITY_CLAIM)
    }
  })

  test('takes the cannabinoid-vocabulary scope knowingly', () => {
    /*
     * Asserted rather than skipped, so the position is visible: this corpus
     * *does* use the vocabulary `CLINICAL_CLAIM` bans, because the form writes
     * those columns. The day it stops needing to is the day this test should
     * fail and the corpus be folded into `ALL_CLUB_COPY`.
     */
    const clinical = ALL_CATALOGUE_COPY.filter((line) => CLINICAL_CLAIM.test(line))

    expect(clinical.length).toBeGreaterThan(0)
  })

  test('uses that vocabulary only to name a field or a column', () => {
    // The narrow claim behind the scope statement. Every line that trips
    // `CLINICAL_CLAIM` does so on a cannabinoid noun, not on a verb about a
    // person — and `THERAPEUTIC_CLAIM` above is what holds that.
    const clinical = ALL_CATALOGUE_COPY.filter((line) => CLINICAL_CLAIM.test(line))

    for (const line of clinical) {
      expect(line, line).toMatch(/\b(thc|cbd|cbg|cannabinoids?)\b/i)
    }
  })
})

describe('the list screen', () => {
  test('says what the catalogue is, and what it is not', () => {
    // The split the whole module rests on: botanical fact here, commercial offer
    // on a cultivator's listing. An administrator who does not know that will go
    // looking for a price field.
    expect(CATALOGUE_LIST.standfirst).toMatch(/botanical/i)
    expect(CATALOGUE_LIST.standfirst).toMatch(/offer/i)
  })

  test('labels every column it draws', () => {
    for (const label of [
      CATALOGUE_LIST.columnName,
      CATALOGUE_LIST.columnType,
      CATALOGUE_LIST.columnStatus,
      CATALOGUE_LIST.columnReserved,
      CATALOGUE_LIST.columnOffers,
      CATALOGUE_LIST.columnUpdated,
    ]) {
      expect(label.length).toBeGreaterThan(0)
    }
  })

  test('says what an unreserved strain means, rather than showing a dash', () => {
    expect(CATALOGUE_LIST.openToAll).toMatch(/all/i)
  })

  test('distinguishes an empty catalogue from an empty filter', () => {
    // "No strains" beside a filter somebody set is a sentence that sends an
    // administrator looking for data that is there.
    expect(CATALOGUE_LIST.empty).not.toBe(CATALOGUE_LIST.emptyFiltered)
  })

  test('says a failed read failed, rather than reporting zero', () => {
    expect(CATALOGUE_LIST.loadFailed).toMatch(/could not/i)
  })
})

describe('the form', () => {
  test('explains that a new strain starts unpublished', () => {
    expect(STRAIN_FORM.addStandfirst).toMatch(/pending/i)
    expect(STRAIN_FORM.addStandfirst).toMatch(/active/i)
  })

  test('explains what reserving a strain does and does not do', () => {
    // Both halves. `Strain.exclusive_to`'s own comment makes the same point: it
    // governs who may offer the strain, not who may edit it.
    expect(STRAIN_FORM.exclusiveHint).toMatch(/blank/i)
    expect(STRAIN_FORM.exclusiveHint).toMatch(/not make the strain/i)
  })

  test('says blank means unknown rather than zero', () => {
    // The trap `mappingFrom` and `checkStrain` both sit in front of, said in
    // words for whoever is typing.
    expect(STRAIN_FORM.chemicalStandfirst).toMatch(/blank/i)
    expect(STRAIN_FORM.chemicalStandfirst).toMatch(/zero/i)
  })

  test('tells whoever writes a description what not to write', () => {
    // Quoting `Strain.description`'s own help text rather than restating it
    // loosely: describe the plant, claim nothing about what it does for anyone.
    expect(STRAIN_FORM.descriptionHint).toMatch(/claim nothing/i)
  })

  test('warns that a withdrawn term cannot be added', () => {
    // The one vocabulary rule a browser cannot enforce, so the form has to
    // explain it rather than let the API refuse a save that looked fine.
    expect(STRAIN_FORM.sensoryStandfirst).toMatch(/withdrawn/i)
  })

  test('says why the save button is inert', () => {
    expect(STRAIN_FORM.unchanged.length).toBeGreaterThan(0)
  })

  test('distinguishes creating from saving', () => {
    // Two verbs, because they are two acts: one adds a row to the catalogue and
    // the other changes one.
    expect(STRAIN_FORM.create).not.toBe(STRAIN_FORM.save)
  })
})

describe('the offers card', () => {
  test('says why it cannot be edited', () => {
    // Read-only is a decision, and a card that is inert without saying why reads
    // as a card that is broken.
    expect(OFFERS_CARD.standfirst).toMatch(/read-only/i)
  })

  test('names the grower’s terms as theirs', () => {
    expect(OFFERS_CARD.standfirst).toMatch(/theirs to set/i)
  })

  test('labels the plant column, which is the one that matters', () => {
    expect(OFFERS_CARD.columnPlants.length).toBeGreaterThan(0)
  })
})

describe('retirement', () => {
  test('says outright that nothing is deleted', () => {
    expect(RETIRE_CARD.standfirst).toMatch(/never deleted/i)
  })

  test('says why', () => {
    // Members own the plants. That is the reason, and an administrator who is
    // told only "you cannot delete this" will look for a way to.
    expect(RETIRE_CARD.standfirst).toMatch(/owned by members/i)
  })

  test('says what retiring reaches', () => {
    expect(RETIRE_CARD.standfirst).toMatch(/every live offer/i)
  })

  test('says the plants are unaffected', () => {
    // The question anybody about to retire a strain with stock behind it will
    // ask, answered before they have to ask it.
    expect(RETIRE_CARD.plantsWarning).toMatch(/unaffected/i)
  })

  test('says how to undo it', () => {
    // There is no undo endpoint, because the status is a field on the form. That
    // is only obvious to whoever wrote it.
    expect(RETIRE_CARD.reinstate).toMatch(/active/i)
  })

  test('confirms before acting', () => {
    expect(RETIRE_CARD.confirmHeading.length).toBeGreaterThan(0)
    expect(RETIRE_CARD.confirmAction.length).toBeGreaterThan(0)
    expect(RETIRE_CARD.confirmCancel.length).toBeGreaterThan(0)
  })

  test('offers a way out of the confirmation that is not the action', () => {
    expect(RETIRE_CARD.confirmCancel).not.toBe(RETIRE_CARD.confirmAction)
  })
})

describe('the vocabularies screen', () => {
  test('says what a withdrawal does and does not do', () => {
    // Both halves, because either alone misleads: "stops being offered" without
    // "existing strains keep it" reads as a delete.
    expect(TERMS_SCREEN.standfirst).toMatch(/new strains/i)
    expect(TERMS_SCREEN.standfirst).toMatch(/already carries it/i)
  })

  test('says who may ask for a term and who adds it', () => {
    // `member-roles.md` gives a cultivator the request and the administrator the
    // write.
    expect(TERMS_SCREEN.standfirst).toMatch(/cultivator/i)
    expect(TERMS_SCREEN.standfirst).toMatch(/administrator/i)
  })

  test('offers a way back as well as a way to withdraw', () => {
    // Withdrawal has to be reversible from the screen that made it, or the
    // screen is a delete with extra steps.
    expect(TERMS_SCREEN.withdrawLabel.length).toBeGreaterThan(0)
    expect(TERMS_SCREEN.restoreLabel.length).toBeGreaterThan(0)
  })

  test('has a singular and a plural for the usage count', () => {
    // "1 strains" is the kind of thing that makes a screen look unfinished.
    expect(TERMS_SCREEN.usedBy).not.toBe(TERMS_SCREEN.usedByOne)
  })
})

describe('the key/value editor', () => {
  test('labels both columns', () => {
    expect(PAIR_EDITOR.nameColumn.length).toBeGreaterThan(0)
    expect(PAIR_EDITOR.valueColumn.length).toBeGreaterThan(0)
  })

  test('describes the remove control at more length than it labels it', () => {
    // Every row's button says the same word, so a screen reader hearing
    // "Remove" eleven times learns nothing about which row it is on.
    expect(PAIR_EDITOR.removeDescription.length).toBeGreaterThan(
      PAIR_EDITOR.removeLabel.length,
    )
  })
})

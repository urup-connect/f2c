/**
 * What member-facing copy may not say, as patterns.
 *
 * These began inside the landing page's copy test. They moved here when the age gate became the
 * second surface with its own corpus: two copies of the rules would have drifted, and the rules
 * are a product constraint rather than a property of one screen.
 *
 * Which corpus is held to which rule is the screen's own decision, recorded in its design doc.
 *
 * Two exemptions exist, both narrow and both stated where they are taken. The age check is exempt
 * from `ELIGIBILITY_CLAIM`, being the only surface that says anything about who may join — see
 * design/features/age-gate-before-sign-up.md section 6.3. The payment screens are exempt from
 * `CURRENCY`, because they have to name an amount — see design/features/payments.md section 5.
 *
 * A third exemption was reserved here for the payment screens and **is not taken**. They were
 * expected to need `RETAIL_VOICE` as well, on the reasoning that a screen asking to be paid cannot
 * avoid a shop's vocabulary. It turned out they can: "subscription", "payment" and "Payfast" say
 * it without any of these words, so `payment-content.test.ts` holds that corpus to this rule rather
 * than exempting it. The reservation is left recorded because the reasoning that produced it is
 * worth having next to the outcome that disproved it.
 *
 * Nothing is exempt from `CLINICAL_CLAIM`, and a further exemption is the point at which these
 * rules stop meaning anything.
 *
 * ## What these rules are *over*
 *
 * Product surfaces: what a visitor or a member reads. That was implicit while every corpus was one,
 * and the strain catalogue's administration screens made it worth saying. Those screens are
 * back-office tooling — an administrator typing a strain's cannabinoid percentages into a form,
 * behind `platform.manage_strain_catalogue` — and no member ever sees a word of them. They are the
 * same category as `app/club/strains/models.py`, whose `help_text` says "Typical THC, as a percentage"
 * and is held to no rule here, and as the Django admin those screens replace.
 *
 * So `strain-catalogue-content.ts` is not in `ALL_CLUB_COPY`, and that is a **scope** statement
 * rather than a fourth exemption: a field label reading "THC" is not a claim about anything, and a
 * catalogue form that could not name the column it writes would be unusable for the sake of a rule
 * that was never about it. `THERAPEUTIC_CLAIM` below is what that corpus *is* held to, and it is
 * the half of `CLINICAL_CLAIM` that is actually a claim.
 */

/** No medical, therapeutic or dosage claim. Cannabis copy attracts these; none is defensible. */
export const CLINICAL_CLAIM =
  /\b(cure[ds]?|treat(s|ed|ment|ments)?|heal(s|ed|ing)?|health|therap\w*|medic\w+|remed\w+|relief|relieve\w*|symptom\w*|dose|dosage|mg|thc|cbd|potenc\w+|wellness)\b/i

/**
 * A claim about what cannabis *does* to a person. The part of `CLINICAL_CLAIM` that is a claim.
 *
 * `CLINICAL_CLAIM` bans two different things at once, which only became visible when a corpus
 * needed one half without the other. It bans assertions — cures, treats, relieves a symptom, take
 * this dose — and it bans the vocabulary those assertions are built from, `thc` and `cbd` and
 * `potency` among it. Banning the vocabulary is right for a product surface, where naming a
 * cannabinoid at all is a step towards claiming something about it. It is meaningless for a form
 * whose job is to record the figure.
 *
 * This is the assertions alone. Every administrative corpus is held to it, so "back office" is
 * never a licence to write a therapeutic claim into a help text — the words an administrator reads
 * are the words they will repeat to a member.
 *
 * Deliberately narrower than `CLINICAL_CLAIM` and deliberately not a replacement for it: no
 * member-facing corpus is held to this one instead.
 */
export const THERAPEUTIC_CLAIM =
  /\b(cure[ds]?|treat(s|ed|ment|ments)?|heal(s|ed|ing)?|therap\w*|medicinal|medication|remed\w+|relief|relieve\w*|symptom\w*|dosage|\d\s?mg)\b/i

/** A club, not a shop. No transactional voice anywhere in the public product. */
export const RETAIL_VOICE =
  /\b(price[ds]?|pricing|cost[s]?|buy|purchase\w*|shop|store|cart|checkout|order[s]?|deliver(y|ies)|discount\w*|sale[s]?|stock|marketplace|market)\b/i

/** No amounts, in any currency or notation. */
export const CURRENCY: readonly RegExp[] = [/[$€£]/, /\bR\s?\d/, /\bZAR\b/i]

/** Who may join. Legal has not written this, so only the age gate states any part of it. */
export const ELIGIBILITY_CLAIM = /\b(over 18|18\+|21\+|adults? only|eligib\w+|licen[cs]\w+)\b/i

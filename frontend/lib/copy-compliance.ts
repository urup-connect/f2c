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
 * design/features/age-gate-before-sign-up.md section 6.3. The payment screen, when it is built,
 * will be exempt from `CURRENCY` and `RETAIL_VOICE`, because it has to name an amount and ask to be
 * paid — see design/features/membership-payment-status.md section 6.7. Nothing is exempt from
 * `CLINICAL_CLAIM`, and a third exemption is the point at which these rules stop meaning anything.
 */

/** No medical, therapeutic or dosage claim. Cannabis copy attracts these; none is defensible. */
export const CLINICAL_CLAIM =
  /\b(cure[ds]?|treat(s|ed|ment|ments)?|heal(s|ed|ing)?|health|therap\w*|medic\w+|remed\w+|relief|relieve\w*|symptom\w*|dose|dosage|mg|thc|cbd|potenc\w+|wellness)\b/i

/** A club, not a shop. No transactional voice anywhere in the public product. */
export const RETAIL_VOICE =
  /\b(price[ds]?|pricing|cost[s]?|buy|purchase\w*|shop|store|cart|checkout|order[s]?|deliver(y|ies)|discount\w*|sale[s]?|stock|marketplace|market)\b/i

/** No amounts, in any currency or notation. */
export const CURRENCY: readonly RegExp[] = [/[$€£]/, /\bR\s?\d/, /\bZAR\b/i]

/** Who may join. Legal has not written this, so only the age gate states any part of it. */
export const ELIGIBILITY_CLAIM = /\b(over 18|18\+|21\+|adults? only|eligib\w+|licen[cs]\w+)\b/i

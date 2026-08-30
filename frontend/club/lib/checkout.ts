/**
 * Turning Django's answer to a checkout request back into something a page can render.
 *
 * Pure, and separate from the fetch that produces the input, for the same reason
 * `registration.ts` is: the mapping is the part that can be wrong in a way nobody notices. A
 * checkout that fails to parse and is rendered anyway is a form that POSTs an incomplete field set
 * to Payfast, which answers with a generic decline and nothing to debug.
 *
 * Two decisions are recorded here.
 *
 * **The fields are opaque and are passed through untouched.** Payfast signs the checkout over
 * exactly the set Django built, in the values it built them with. So nothing here reorders,
 * re-cases, trims, drops or adds a field — and `readCheckout` refuses a body rather than repairing
 * one. A "helpful" normalisation is the single most likely way for this integration to break.
 *
 * **A checkout that cannot be read is not a checkout.** There is no partial render. The member
 * either gets a form that will work or a screen saying the club could not start the payment,
 * because a form that silently fails at Payfast leaves them believing they have paid.
 */

/** What Django answers with. Mirrors `CheckoutOut` in payments/schemas.py. */
export type Checkout = {
  /** Payfast's payment engine — sandbox or live, decided by Django's configuration. */
  readonly url: string
  /** The signed field set, `signature` included. Rendered as hidden inputs, unchanged. */
  readonly fields: Readonly<Record<string, string>>
}

export type CheckoutOutcome =
  | { readonly status: 'ready'; readonly checkout: Checkout }
  /**
   * The token names nothing payable: unknown, expired, or a subscription already paid or
   * cancelled. Django answers all four identically and so does this — telling them apart would
   * make the endpoint a way to probe whether a token was ever real.
   */
  | { readonly status: 'unavailable' }
  /** The fault is ours: Django unreachable, or an answer this application did not understand. */
  | { readonly status: 'unusable'; readonly reason: string }

/**
 * A checkout token as it appears in a URL or a cookie.
 *
 * 32 bytes of `secrets.token_urlsafe` is 43 characters of `[A-Za-z0-9_-]`. The bound is a range
 * rather than an equality so that raising `CHECKOUT_TOKEN_BYTES` on the Django side does not need a
 * matching deploy here, and an upper bound exists at all so a multi-kilobyte path segment is
 * refused before it reaches the API.
 */
const TOKEN = /^[A-Za-z0-9_-]{32,128}$/

/**
 * The token, or `null` for anything that is not one.
 *
 * Applied to the cookie and to the path segment of an emailed link alike, before either is put in
 * a URL Django will see. It is not a security control — Django looks the token up and is the only
 * thing that decides it is real — it is what stops a hand-typed or doctored value becoming a
 * request, and what keeps the shape of the value in one place.
 */
export const readCheckoutToken = (value: string | undefined | null): string | null => {
  if (typeof value !== 'string') return null

  const trimmed = value.trim()
  return TOKEN.test(trimmed) ? trimmed : null
}

const isStringRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

/**
 * Read a 200 body, or say why it could not be read.
 *
 * Every field value has to be a string, because every one becomes an `<input value>`. A number or
 * a null arriving here would render as `"null"` and break the signature, so the whole body is
 * refused instead — which is the difference between a member seeing an honest failure and Payfast
 * declining a checkout for reasons nobody can see.
 */
export const readCheckout = (body: unknown): CheckoutOutcome => {
  if (!isStringRecord(body)) {
    return { status: 'unusable', reason: 'Checkout answered with something that is not an object.' }
  }

  const { url, fields } = body

  if (typeof url !== 'string' || url === '') {
    return { status: 'unusable', reason: 'Checkout answered with no payment URL.' }
  }

  if (!isStringRecord(fields)) {
    return { status: 'unusable', reason: 'Checkout answered with no fields to post.' }
  }

  const entries = Object.entries(fields)

  if (entries.length === 0) {
    return { status: 'unusable', reason: 'Checkout answered with an empty field set.' }
  }

  if (!entries.every(([, value]) => typeof value === 'string')) {
    return {
      status: 'unusable',
      reason: 'Checkout answered with a field that is not a string.',
    }
  }

  /*
   * The signature is the one field whose absence is silent: every other missing field makes
   * Payfast complain about that field, and a missing signature makes it complain about the
   * signature, which sends whoever is debugging to the wrong module.
   */
  if (typeof fields.signature !== 'string' || fields.signature === '') {
    return { status: 'unusable', reason: 'Checkout answered with no signature.' }
  }

  return {
    status: 'ready',
    checkout: { url, fields: Object.fromEntries(entries) as Record<string, string> },
  }
}

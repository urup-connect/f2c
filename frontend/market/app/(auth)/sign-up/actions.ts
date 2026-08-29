'use server'

import { checkSignUp, readSignUpForm, type SignUpFormState } from '@/lib/sign-up'
import { createAccount } from '@/lib/sign-up-api'

/**
 * Validates a sign-up submission and registers it, answering with what the screen should show.
 *
 * **A server action rather than a `fetch` from the form**, for three reasons that are all the same
 * reason: the registration endpoint is unauthenticated, so the origin calling it should be ours; the
 * form then works without JavaScript; and the rules run on the server, where they cannot be skipped by
 * anybody submitting the form by other means.
 *
 * The rules run here **as well as** in the browser rather than instead of it. Nothing is trusted from
 * the client, and the client still checks so that a refusal does not cost a round trip.
 *
 * `previous` is unused, and it is in the signature because `useActionState` supplies it. Naming it and
 * ignoring it is more honest than a signature that pretends the argument is not there: this form has no
 * state that survives a submission, since every terminal state deliberately keeps nothing typed. See
 * `SignUpFormState`.
 */
export async function signUp(
  previous: SignUpFormState,
  form: FormData,
): Promise<SignUpFormState> {
  void previous

  const values = readSignUpForm(form)
  const checked = checkSignUp(values)

  if (checked.status === 'invalid') {
    return { status: 'invalid', refusals: checked.refusals, values }
  }

  const outcome = await createAccount(checked.submission)

  if (outcome.status === 'accepted') return { status: 'accepted', email: outcome.email }
  if (outcome.status === 'unavailable') return { status: 'unavailable' }

  if (outcome.status === 'refused') {
    /*
     * Refusals from the API come back with the values, because they are field refusals and the form is
     * about to redraw them. This is the one path where the API knows something the rules do not.
     */
    return { status: 'invalid', refusals: outcome.refusals, values }
  }

  /*
   * `unusable` carries a reason, and the reason is deliberately dropped rather than shown. It names a
   * status code or says the API could not be reached, which is written for a log rather than for a
   * customer; the screen says the fault is ours in its own words. Nothing is lost that anybody could
   * act on.
   */
  return { status: 'failed' }
}

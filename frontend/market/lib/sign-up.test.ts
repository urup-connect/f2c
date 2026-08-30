import { describe, expect, test } from 'vitest'
import {
  SIGN_UP_FIELDS,
  SIGN_UP_REFUSALS,
  checkSignUp,
  readSignUpForm,
  readSignUpRefusals,
  signUpRefusalFor,
  type SignUpInput,
} from './sign-up'
import { SIGN_UP_REFUSAL_MESSAGES } from './sign-up-content'

const valid: SignUpInput = {
  firstName: 'Thandiwe',
  lastName: 'Mokoena',
  email: 'Thandiwe@Example.com',
  mobile: '082 123 4567',
}

describe('what sign-up collects', () => {
  test('is four fields and no more', () => {
    // No identity number, no nickname, no consents, no password. Each omission has a reason
    // recorded in lib/sign-up.ts, and all four are the identity split.
    expect(SIGN_UP_FIELDS).toEqual(['firstName', 'lastName', 'email', 'mobile'])
  })
})

describe('checkSignUp', () => {
  test('accepts a full submission and normalises it', () => {
    const checked = checkSignUp(valid)

    expect(checked).toEqual({
      status: 'valid',
      submission: {
        first_name: 'Thandiwe',
        last_name: 'Mokoena',
        // Lower-cased: one address has exactly one stored form.
        email: 'thandiwe@example.com',
        // The stored form, not what was typed.
        mobile: '+27821234567',
      },
    })
  })

  test('accepts a blank mobile number, which is an answer rather than an omission', () => {
    const checked = checkSignUp({ ...valid, mobile: '   ' })

    expect(checked.status).toBe('valid')
    expect(checked.status === 'valid' && checked.submission.mobile).toBe('')
  })

  test('refuses a mobile number that is not one, once something has been typed', () => {
    const checked = checkSignUp({ ...valid, mobile: '086 123 4567' })

    expect(checked.status).toBe('invalid')
    expect(checked.status === 'invalid' && checked.refusals).toEqual([
      { field: 'mobile', reason: 'mobile-not-a-mobile' },
    ])
  })

  test('reports every refusal, in field order, rather than stopping at the first', () => {
    const checked = checkSignUp({ firstName: '', lastName: '9', email: 'not-an-address', mobile: '' })

    expect(checked.status).toBe('invalid')
    expect(checked.status === 'invalid' && checked.refusals).toEqual([
      { field: 'firstName', reason: 'name-missing' },
      { field: 'lastName', reason: 'name-unexpected-characters' },
      { field: 'email', reason: 'email-malformed' },
    ])
  })

  test('never throws, whatever it is given', () => {
    expect(() =>
      checkSignUp({ firstName: '🥕'.repeat(200), lastName: '<b>', email: '@', mobile: '+++' }),
    ).not.toThrow()
  })
})

describe('signUpRefusalFor', () => {
  test('finds the refusal a field has to render', () => {
    const refusals = [{ field: 'email', reason: 'email-malformed' }] as const

    expect(signUpRefusalFor(refusals, 'email')).toBe('email-malformed')
    expect(signUpRefusalFor(refusals, 'firstName')).toBeUndefined()
  })
})

describe('readSignUpForm', () => {
  test('reads the four fields off a form', () => {
    const form = new FormData()
    form.set('firstName', 'Thandiwe')
    form.set('lastName', 'Mokoena')
    form.set('email', 'thandiwe@example.com')
    form.set('mobile', '0821234567')

    expect(readSignUpForm(form)).toEqual({
      firstName: 'Thandiwe',
      lastName: 'Mokoena',
      email: 'thandiwe@example.com',
      mobile: '0821234567',
    })
  })

  test('reads a missing field as blank, so the rules refuse it in our own words', () => {
    expect(readSignUpForm(new FormData())).toEqual({
      firstName: '',
      lastName: '',
      email: '',
      mobile: '',
    })
  })

  test('reads a value that is not a string as blank', () => {
    // What an uploaded file arrives as. A tampered submission is answered like an empty one.
    const form = new FormData()
    form.set('email', new File(['x'], 'x.txt'))

    expect(readSignUpForm(form).email).toBe('')
  })
})

describe('the refusal messages', () => {
  test('every reason in the vocabulary has wording, so none can be added without one', () => {
    for (const reason of SIGN_UP_REFUSALS) {
      expect(SIGN_UP_REFUSAL_MESSAGES[reason]).toBeTruthy()
    }

    // And nothing is left behind: a message with no reason is copy nobody will ever see.
    expect(Object.keys(SIGN_UP_REFUSAL_MESSAGES).sort()).toEqual([...SIGN_UP_REFUSALS].sort())
  })

  test('every reason the form can produce has wording', () => {
    const checked = checkSignUp({ firstName: '', lastName: '', email: '', mobile: '086 123 4567' })

    if (checked.status !== 'invalid') throw new Error('expected refusals')

    for (const { reason } of checked.refusals) {
      expect(SIGN_UP_REFUSAL_MESSAGES[reason]).toBeTruthy()
    }
  })
})

describe('readSignUpRefusals', () => {
  test('reads a refusal the API made against a field this form has', () => {
    expect(readSignUpRefusals({ fields: { email: ['email-malformed'] } })).toEqual([
      { field: 'email', reason: 'email-malformed' },
    ])
  })

  test('maps the wire name back to the form name', () => {
    expect(readSignUpRefusals({ fields: { first_name: ['name-missing'] } })).toEqual([
      { field: 'firstName', reason: 'name-missing' },
    ])
  })

  test('drops a field this form does not have', () => {
    // A message with nowhere to appear is dropped deliberately rather than silently.
    expect(readSignUpRefusals({ fields: { id_number: ['whatever'] } })).toEqual([])
  })

  test('drops a reason it cannot render, rather than putting API text on the page', () => {
    expect(readSignUpRefusals({ fields: { email: ['something-new'] } })).toEqual([])
  })

  test('answers nothing for a body that is not the shape it expects', () => {
    expect(readSignUpRefusals({})).toEqual([])
    expect(readSignUpRefusals({ fields: null })).toEqual([])
    expect(readSignUpRefusals({ fields: { email: 'email-malformed' } })).toEqual([])
  })
})

import { describe, expect, test } from 'vitest'
import {
  PROFILE_FIELDS,
  PROFILE_REFUSALS,
  checkProfile,
  profileHasChanges,
  profileInputFrom,
  profileOnFile,
  profileRefusalFor,
  readProfileForm,
  type ProfileInput,
} from './profile'
import { PROFILE_REFUSAL_MESSAGES } from './store-content'

const typed: ProfileInput = {
  firstName: 'Thandiwe',
  lastName: 'Mokoena',
  mobile: '082 123 4567',
}

const onFile = { first_name: 'Thandiwe', last_name: 'Mokoena', mobile: '+27821234567' }

describe('what a customer may change', () => {
  test('is three fields', () => {
    // The email address is the sign-in identifier; the nickname, date of birth and identity number
    // are club fields and are usually empty here. See lib/profile.ts.
    expect(PROFILE_FIELDS).toEqual(['firstName', 'lastName', 'mobile'])
  })
})

describe('checkProfile', () => {
  test('accepts three good values and normalises them', () => {
    expect(checkProfile(typed)).toEqual({
      status: 'valid',
      submission: { first_name: 'Thandiwe', last_name: 'Mokoena', mobile: '+27821234567' },
    })
  })

  test('collapses whitespace in a name rather than refusing it', () => {
    const checked = checkProfile({ ...typed, firstName: '  Thandiwe   Naledi ' })

    expect(checked.status === 'valid' && checked.submission.first_name).toBe('Thandiwe Naledi')
  })

  test('accepts a blank mobile number and clears the column', () => {
    // Somebody who no longer has the handset they gave should be able to say so, rather than leave
    // the store a wrong number to ring.
    const checked = checkProfile({ ...typed, mobile: '' })

    expect(checked.status === 'valid' && checked.submission.mobile).toBe('')
  })

  test('holds a non-blank mobile number to the whole rule', () => {
    expect(checkProfile({ ...typed, mobile: '080 123 4567' })).toEqual({
      status: 'invalid',
      refusals: [{ field: 'mobile', reason: 'mobile-not-a-mobile' }],
    })
  })

  test('reports both names and the number at once', () => {
    expect(checkProfile({ firstName: '', lastName: '', mobile: '12345' })).toEqual({
      status: 'invalid',
      refusals: [
        { field: 'firstName', reason: 'name-missing' },
        { field: 'lastName', reason: 'name-missing' },
        { field: 'mobile', reason: 'mobile-length' },
      ],
    })
  })
})

describe('profileRefusalFor', () => {
  test('finds the refusal a field renders under itself', () => {
    const refusals = [{ field: 'mobile', reason: 'mobile-length' }] as const

    expect(profileRefusalFor(refusals, 'mobile')).toBe('mobile-length')
    expect(profileRefusalFor(refusals, 'firstName')).toBeUndefined()
  })
})

describe('profileInputFrom', () => {
  test('draws the form from the record, leaving a blank number blank', () => {
    expect(profileInputFrom({ ...onFile, mobile: '' })).toEqual({
      firstName: 'Thandiwe',
      lastName: 'Mokoena',
      mobile: '',
    })
  })
})

describe('profileHasChanges', () => {
  test('is false for a freshly loaded form', () => {
    expect(profileHasChanges(profileInputFrom(onFile), profileOnFile(onFile))).toBe(false)
  })

  test('ignores punctuation the store would not store', () => {
    // A save button that lights up for this is a button promising a change it will not make.
    expect(profileHasChanges({ ...typed, mobile: '+27 82 123 4567' }, profileOnFile(onFile))).toBe(
      false,
    )
    expect(profileHasChanges({ ...typed, lastName: 'Mokoena ' }, profileOnFile(onFile))).toBe(false)
  })

  test('sees a real change', () => {
    expect(profileHasChanges({ ...typed, firstName: 'Naledi' }, profileOnFile(onFile))).toBe(true)
    expect(profileHasChanges({ ...typed, mobile: '' }, profileOnFile(onFile))).toBe(true)
  })

  test('counts a form that does not validate as changed', () => {
    // It cannot be normalised, so the honest answer is "something is different", and pressing save
    // is how the customer learns what.
    expect(profileHasChanges({ ...typed, firstName: '' }, profileOnFile(onFile))).toBe(true)
  })
})

describe('readProfileForm', () => {
  test('reads the three fields, and a missing one as blank', () => {
    const form = new FormData()
    form.set('firstName', 'Thandiwe')

    expect(readProfileForm(form)).toEqual({ firstName: 'Thandiwe', lastName: '', mobile: '' })
  })
})

describe('the refusal messages', () => {
  test('every reason in the vocabulary has wording, and none is left over', () => {
    for (const reason of PROFILE_REFUSALS) {
      expect(PROFILE_REFUSAL_MESSAGES[reason]).toBeTruthy()
    }

    expect(Object.keys(PROFILE_REFUSAL_MESSAGES).sort()).toEqual([...PROFILE_REFUSALS].sort())
  })
})

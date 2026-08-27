import type { Disclosure, Member, MemberRow } from '@/lib/member-register'

/**
 * Register fixtures, shared by the lib tests and the five component tests.
 *
 * Here rather than in `lib/` so they stay out of the coverage report, which is
 * what `test-support/` is for. Each builder takes `Partial<T>` overrides, so a
 * test names the one field it is about and nothing else — which is what stops
 * two fixtures in two files drifting into disagreeing about what a member looks
 * like.
 *
 * The defaults describe an ordinary paying member: active, editable, a
 * subscription in force, and an identity document on file. Every other case is
 * an override, so a test reads as the departure it is testing.
 */

export const disclosure = (overrides: Partial<Disclosure> = {}): Disclosure => ({
  id: 'disclosure-1',
  read_by: 'Registrar',
  reason: 'Verifying against the document on file.',
  created_at: '2026-08-01T09:00:00Z',
  ...overrides,
})

export const memberRow = (overrides: Partial<MemberRow> = {}): MemberRow => ({
  id: 'member-1',
  display_name: 'Thabo',
  first_name: 'Thabo',
  last_name: 'Mahlangu',
  nickname: 'Thabo',
  email: 'thabo@example.com',
  mobile: '+27821234567',
  status: 'active',
  status_label: 'Active',
  role: 'member',
  role_label: 'Member',
  membership: {
    status: 'active',
    status_label: 'Active',
    paid_until: '2026-12-31',
  },
  has_id_number: true,
  erased: false,
  created_at: '2026-01-15T08:00:00Z',
  ...overrides,
})

export const member = (overrides: Partial<Member> = {}): Member => ({
  ...memberRow(),
  id_number_masked: '*********1234',
  editable: true,
  registered_by: null,
  date_of_birth: '1990-03-15',
  date_of_birth_verified_at: null,
  last_login: '2026-08-20T07:30:00Z',
  updated_at: '2026-08-20T07:30:00Z',
  disclosures: [],
  ...overrides,
})

/** An account erased at the member's request: read-only, and no address left. */
export const erasedMember = (overrides: Partial<Member> = {}): Member =>
  member({
    email: null,
    mobile: '',
    status: 'inactive',
    status_label: 'Inactive',
    erased: true,
    editable: false,
    has_id_number: false,
    id_number_masked: '',
    membership: { status: null, status_label: null, paid_until: null },
    ...overrides,
  })

/** A stock-holding identity registered by a cultivator: read-only here, by C14. */
export const sharingMember = (overrides: Partial<Member> = {}): Member =>
  member({
    id: 'member-sharing',
    display_name: 'Held',
    nickname: 'Held',
    email: null,
    mobile: '',
    status: 'sharing',
    status_label: 'Sharing member (no sign-in)',
    role: 'sharing_member',
    role_label: 'Sharing member',
    editable: false,
    registered_by: 'Kloof',
    membership: { status: null, status_label: null, paid_until: null },
    ...overrides,
  })

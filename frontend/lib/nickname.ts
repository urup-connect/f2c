/**
 * The nickname a member is known by, as pure logic.
 *
 * ASCII only, deliberately, and unlike the name fields. A nickname is the one value on the member
 * record that is an identity claim against other members: a Cyrillic "а" inside a name that reads
 * as an existing member's is impersonation, and defending against that properly means folding
 * confusable characters. Restricting the alphabet removes the whole class of problem instead.
 *
 * Uniqueness is decided on the lower-cased form, so `Grower` and `grower` cannot both exist, while
 * the capitalisation a member chose is what other members see.
 *
 * See design/features/member-details-at-sign-up.md section 6.6.
 */

export const NICKNAME_MIN_LENGTH = 3
export const NICKNAME_MAX_LENGTH = 20

export type NicknameRefusal =
  | 'missing'
  | 'length'
  | 'unexpected-characters'
  | 'shape'
  | 'unavailable'

export const NICKNAME_REFUSALS = [
  'missing',
  'length',
  'unexpected-characters',
  'shape',
  'unavailable',
] as const satisfies readonly NicknameRefusal[]

export type NicknameCheck =
  | { readonly status: 'valid'; readonly nickname: string }
  | { readonly status: 'invalid'; readonly reason: NicknameRefusal }

/**
 * Names a member may not wear, because wearing one is a way to be mistaken for the club or for
 * someone acting on its behalf. Held in the comparable form, and a test guards that.
 *
 * The product's own route names are here for the same reason: a member called `verify` inside a
 * sentence about verifying something is a phishing message that writes itself.
 */
export const RESERVED_NICKNAMES = [
  'admin',
  'administrator',
  'moderator',
  'mod',
  'support',
  'help',
  'staff',
  'team',
  'official',
  'security',
  'system',
  'root',
  'club',
  'collective',
  'cultivators',
  'cultivatorscollective',
  'signup',
  'login',
  'verify',
  'api',
] as const

/** Route names carry a hyphen, which the list above cannot hold as one word. */
const RESERVED_WITH_SEPARATORS = ['age-check'] as const

const PERMITTED = /^[A-Za-z0-9_-]+$/

const STARTS_WITH_A_LETTER = /^[A-Za-z]/

const ENDS_WITH_A_SEPARATOR = /[_-]$/

const DOUBLED_SEPARATOR = /[_-]{2}/

const invalid = (reason: NicknameRefusal): NicknameCheck => ({ status: 'invalid', reason })

/** The form uniqueness is decided on. Case folded, ends trimmed, separators left alone. */
export const nicknameKey = (input: string) => input.trim().toLowerCase()

const isReserved = (key: string) =>
  RESERVED_NICKNAMES.some((reserved): boolean => reserved === key) ||
  RESERVED_WITH_SEPARATORS.some((reserved): boolean => reserved === key)

/**
 * The whole rule. Never throws for any input.
 *
 * The alphabet is checked before the length, so an accented or Cyrillic nickname is told what is
 * actually wrong with it rather than being counted. Shape follows, then the reserved list, which
 * is last because a reserved name is a valid nickname that simply belongs to nobody.
 */
export const checkNickname = (input: string): NicknameCheck => {
  const nickname = input.trim()

  if (nickname.length === 0) return invalid('missing')
  if (!PERMITTED.test(nickname)) return invalid('unexpected-characters')

  if (nickname.length < NICKNAME_MIN_LENGTH || nickname.length > NICKNAME_MAX_LENGTH) {
    return invalid('length')
  }

  if (
    !STARTS_WITH_A_LETTER.test(nickname) ||
    ENDS_WITH_A_SEPARATOR.test(nickname) ||
    DOUBLED_SEPARATOR.test(nickname)
  ) {
    return invalid('shape')
  }

  if (isReserved(nicknameKey(nickname))) return invalid('unavailable')

  return { status: 'valid', nickname }
}

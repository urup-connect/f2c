"""South African identity-number checks, used when a member's ID is captured.

A 13-digit RSA ID number is ``YYMMDD SSSS C A Z``: date of birth, a
gender-ordered sequence, a citizenship digit, one legacy digit, and a Luhn
check digit. Two things follow, and both matter here.

First, the number is self-validating: a typo almost always breaks the check
digit, so there is no excuse for storing one that cannot be checked.

Second, the number *contains* the date of birth. That is why
:func:`sa_id_birth_date` exists -- ``User.date_of_birth`` can be filled from the document
itself rather than typed in a second time and disagreeing with it -- and it is
also why the number is encrypted at rest: it is not merely an identifier, it
discloses age, gender and citizenship status to anyone who reads the column.

Members without an RSA ID (a foreign passport, say) are expected: nothing in
the model requires these validators, and the registration flow decides which
document type it is looking at.
"""
import re
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email as django_validate_email

# A person alive today. Used only to resolve the two-digit year, which is
# ambiguous by construction: '27' is 1927 for anyone living, not 2027.
MAX_AGE_YEARS = 120

_DIGITS_ONLY = re.compile(r'[\s-]+')


def normalise_id_number(value):
    """Strip the separators people type. Does not validate."""
    return _DIGITS_ONLY.sub('', str(value or '')).strip()


def luhn_is_valid(digits):
    """Standard Luhn check over the whole string, check digit included."""
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def sa_id_birth_date(value, today=None):
    """The date of birth encoded in an RSA ID number, or ``None``.

    Returns ``None`` rather than raising when the leading six digits are not a
    real date, so callers can validate and extract in one pass.
    """
    digits = normalise_id_number(value)
    if len(digits) != 13 or not digits.isdigit():
        return None

    today = today or date.today()
    year_2, month, day = int(digits[0:2]), int(digits[2:4]), int(digits[4:6])

    # Pick the century that puts the birth date in the past and inside a
    # plausible human lifespan.
    for century in (today.year // 100, today.year // 100 - 1):
        try:
            candidate = date(century * 100 + year_2, month, day)
        except ValueError:
            return None
        if candidate <= today and today.year - candidate.year <= MAX_AGE_YEARS:
            return candidate
    return None


def validate_sa_id_number(value):
    """Raise :class:`ValidationError` unless ``value`` is a well-formed RSA ID.

    Checks structure, that the embedded date is real, the citizenship digit,
    and the Luhn check digit. It cannot confirm the number was ever issued --
    that needs Home Affairs -- so a passing number means "not a typo", not
    "verified". Recording the latter is what ``User.date_of_birth_verified_at`` is for.
    """
    digits = normalise_id_number(value)

    if len(digits) != 13 or not digits.isdigit():
        raise ValidationError(
            'A South African ID number is 13 digits.', code='id_length'
        )
    if sa_id_birth_date(digits) is None:
        raise ValidationError(
            'The first six digits are not a valid date of birth.', code='id_dob'
        )
    if digits[10] not in '01':
        raise ValidationError(
            'The citizenship digit must be 0 (citizen) or 1 (permanent resident).',
            code='id_citizenship',
        )
    if not luhn_is_valid(digits):
        raise ValidationError(
            'That ID number fails its check digit. Please re-enter it.',
            code='id_checksum',
        )
    return digits


# ---------------------------------------------------------------------------
# Contact details and display names
# ---------------------------------------------------------------------------
#
# The frontend owns the fuller version of each rule below, in
# ``frontend/lib/sa-mobile-number.ts``, ``frontend/lib/nickname.ts``,
# ``frontend/lib/person-name.ts`` and ``frontend/lib/email-address.ts``. These
# are the same rules in Python, and they exist because the registration
# endpoint is unauthenticated and reachable without going through the frontend
# at all. A rule that lives only in the browser -- or only in a Next.js server
# action -- is not a rule the database is protected by.
#
# Two rules over one field have to be read together. That is already recorded
# for the identity number in design/features/sign-up.md, risk 5, and it now
# applies to these four as well.

#: The age the club is open from. The frontend's age gate states it to a
#: visitor; this is the same rule applied to an identity document, server-side,
#: where nothing a browser sends can move it.
MINIMUM_MEMBER_AGE_YEARS = 18


def is_at_least(born, years, today=None):
    """Whether someone born on ``born`` has had their ``years``th birthday.

    **Calendar arithmetic, not milliseconds.** Adding eighteen years to a
    datetime invites a time zone, an hour that does not exist across a clock
    change, and a 29 February that silently becomes 1 March in a different
    place from where it was meant. Comparing ``(year + years, month, day)``
    part by part has none of that, and matches ``frontend/lib/age-gate.ts``
    deliberately -- the two rules must agree.

    A 29 February birthday therefore has no birthday at all in a common year
    and waits one more day. That is the conservative side of a legal convention
    this code should not be inventing.

    ``today`` is an argument rather than read from the clock, so a date
    boundary is a test case instead of something that misbehaves only at
    midnight in production. ``born`` of ``None`` is not old enough: an unknown
    date of birth is not a date of birth that passes.
    """
    if born is None:
        return False
    today = today or date.today()
    return (born.year + years, born.month, born.day) <= (
        today.year,
        today.month,
        today.day,
    )


_MOBILE_SEPARATORS = re.compile(r'[\s().-]+')

#: The country code every stored number carries.
MOBILE_COUNTRY_CODE = '27'

#: Nine digits after the trunk zero or the country code.
MOBILE_NATIONAL_LENGTH = 9

#: First digits that carry a handset.
MOBILE_LEADING_DIGITS = ('6', '7', '8')

#: Ranges inside 08 that reach a service rather than a person: toll-free,
#: share-call and VoIP. Written with the trunk zero, as people recognise them.
NON_MOBILE_PREFIXES = ('080', '086', '087', '088', '089')


def normalise_sa_mobile_number(value):
    """The one stored form of a mobile number: ``+27`` and nine digits.

    Returns ``''`` when the value is not one. Punctuation is stripped first, so
    the same handset cannot become two members by being written two ways.

    A slash is not a separator here, deliberately. ``082/123/4567`` is usually
    two numbers, and guessing which one is meant is worse than asking.
    """
    stripped = _MOBILE_SEPARATORS.sub('', str(value or '')).strip()
    had_plus = stripped.startswith('+')
    digits = stripped[1:] if had_plus else stripped

    if not digits.isdigit():
        return ''
    if had_plus and not digits.startswith(MOBILE_COUNTRY_CODE):
        return ''

    if had_plus:
        national = digits[len(MOBILE_COUNTRY_CODE):]
    elif digits.startswith('00' + MOBILE_COUNTRY_CODE):
        national = digits[4:]
    elif (
        digits.startswith(MOBILE_COUNTRY_CODE)
        and len(digits) == len(MOBILE_COUNTRY_CODE) + MOBILE_NATIONAL_LENGTH
    ):
        national = digits[len(MOBILE_COUNTRY_CODE):]
    elif digits.startswith('0'):
        national = digits[1:]
    else:
        national = digits

    if len(national) != MOBILE_NATIONAL_LENGTH:
        return ''
    if national[0] not in MOBILE_LEADING_DIGITS:
        return ''
    if '0' + national[:2] in NON_MOBILE_PREFIXES:
        return ''
    return '+' + MOBILE_COUNTRY_CODE + national


def validate_sa_mobile_number(value):
    """Return the stored form, or raise :class:`ValidationError`.

    The range rule is deliberately permissive -- anything starting 6, 7 or 8,
    less the service ranges. An allow-list of every allocated prefix would be
    more precise today and wrong within a year, and its failure mode is
    refusing a real member's real number, which is worse than accepting one
    that turns out not to be a handset.
    """
    normalised = normalise_sa_mobile_number(value)
    if not normalised:
        raise ValidationError(
            'Enter a South African mobile number, for example 082 123 4567.',
            code='mobile_invalid',
        )
    return normalised


NICKNAME_MIN_LENGTH = 3
NICKNAME_MAX_LENGTH = 20

#: Names a member may not wear, because wearing one is a way to be mistaken
#: for the club or for someone acting on its behalf. The product's own route
#: names are here for the same reason: a member called ``verify``, appearing
#: inside a sentence about verifying something, is a phishing message that
#: writes itself. Held in the comparable form, and mirrors
#: ``RESERVED_NICKNAMES`` in ``frontend/lib/nickname.ts``.
RESERVED_NICKNAMES = frozenset({
    'admin', 'administrator', 'moderator', 'mod', 'support', 'help', 'staff',
    'team', 'official', 'security', 'system', 'root', 'club', 'collective',
    'cultivators', 'cultivatorscollective', 'signup', 'login', 'verify', 'api',
    'age-check',
})

_NICKNAME_PERMITTED = re.compile(r'^[A-Za-z0-9_-]+$')
_NICKNAME_STARTS_WITH_A_LETTER = re.compile(r'^[A-Za-z]')
_NICKNAME_ENDS_WITH_A_SEPARATOR = re.compile(r'[_-]$')
_NICKNAME_DOUBLED_SEPARATOR = re.compile(r'[_-]{2}')


def nickname_key(value):
    """The form uniqueness is decided on: case folded, ends trimmed.

    Separators are left alone. ``grow-er`` and ``grower`` are two nicknames,
    and folding them together would refuse the second for no reason a member
    could see.
    """
    return str(value or '').strip().lower()


def validate_nickname(value):
    """Return the nickname as typed, or raise :class:`ValidationError`.

    ASCII only, and unlike the name fields that restriction is the point. A
    nickname is the one value on the member record that is an identity claim
    against other members: a Cyrillic small a inside a name that reads as an
    existing member's is impersonation, and defending against that properly
    means folding confusable characters across the whole of Unicode.
    Restricting the alphabet removes the class of problem instead.

    Says nothing about whether the nickname is *taken*. That is a database
    question, and ``accounts.UserManager.nickname_is_taken`` answers it.
    """
    nickname = str(value or '').strip()

    if not nickname:
        raise ValidationError('Choose a nickname.', code='nickname_missing')
    # Alphabet before length, so an accented or Cyrillic nickname is told what
    # is actually wrong with it rather than being counted.
    if not _NICKNAME_PERMITTED.match(nickname):
        raise ValidationError(
            'A nickname may use letters, numbers, hyphens and underscores only.',
            code='nickname_characters',
        )
    if not NICKNAME_MIN_LENGTH <= len(nickname) <= NICKNAME_MAX_LENGTH:
        raise ValidationError(
            'A nickname is between {} and {} characters.'.format(
                NICKNAME_MIN_LENGTH, NICKNAME_MAX_LENGTH
            ),
            code='nickname_length',
        )
    if (
        not _NICKNAME_STARTS_WITH_A_LETTER.match(nickname)
        or _NICKNAME_ENDS_WITH_A_SEPARATOR.search(nickname)
        or _NICKNAME_DOUBLED_SEPARATOR.search(nickname)
    ):
        raise ValidationError(
            'A nickname starts with a letter, does not end with a hyphen or '
            'underscore, and does not double them.',
            code='nickname_shape',
        )
    # Last, because a reserved name is a well-formed nickname that simply
    # belongs to nobody.
    if nickname_key(nickname) in RESERVED_NICKNAMES:
        raise ValidationError(
            'That nickname is not available.', code='nickname_unavailable'
        )
    return nickname


PERSON_NAME_MAX_LENGTH = 70

_NAME_WHITESPACE = re.compile(r'\s+')
_NAME_HAS_A_LETTER = re.compile(r'[^\W\d_]', re.UNICODE)
_NAME_FORBIDDEN = re.compile(r'[\d@<>/\\|=+*#$%^~\[\]{}"]')


def normalise_person_name(value):
    """Collapse the whitespace people type. Does not validate.

    Length is measured after this, so three spaces a member did not mean to
    type cannot push an otherwise acceptable name over the limit.
    """
    return _NAME_WHITESPACE.sub(' ', str(value or '')).strip()


def validate_person_name(value):
    """Return the normalised name, or raise :class:`ValidationError`.

    The interesting part of this rule is **what it refuses to refuse.** It does
    not require two names, a vowel, a capital letter, more than one character,
    or the Latin alphabet. Every one of those conventions, applied to South
    African names, rejects people who exist.

    What it does refuse is a value that is not a name at all: digits, markup,
    an email address, or punctuation with no letter anywhere in it.

    ``frontend/lib/person-name.ts`` holds the fuller rule, and is what a member
    actually meets. This is the floor the database is protected by.
    """
    name = normalise_person_name(value)

    if not name:
        raise ValidationError('Enter your name.', code='name_missing')
    if _NAME_FORBIDDEN.search(name) or not _NAME_HAS_A_LETTER.search(name):
        raise ValidationError('That does not look like a name.', code='name_characters')
    # Characters before length: "that is not a name" is the more useful
    # complaint about a long string full of digits.
    if len(name) > PERSON_NAME_MAX_LENGTH:
        raise ValidationError(
            'A name is at most {} characters.'.format(PERSON_NAME_MAX_LENGTH),
            code='name_length',
        )
    return name


EMAIL_MAX_LENGTH = 254


def normalise_email(value):
    """The one stored form of an address: trimmed and lower-cased whole.

    The local part is lower-cased too, not just the domain. Case-sensitive
    local parts are legal and universally ignored by real mail providers;
    honouring them here would let someone register ``Member@example.com``
    alongside ``member@example.com`` and receive the other's sign-in codes.
    Matches ``accounts.User.save``.
    """
    return str(value or '').strip().lower()


def validate_email_address(value):
    """Return the normalised address, or raise :class:`ValidationError`.

    Deliberately not RFC 5322. That grammar admits quoted local parts,
    comments and bracketed IP literals, none of which a member is going to type
    and all of which widen the surface for no benefit. What this catches is a
    typo; nothing here proves the address can receive mail, which only sending
    to it does.
    """
    email = normalise_email(value)

    if not email:
        raise ValidationError('Enter your email address.', code='email_missing')
    if len(email) > EMAIL_MAX_LENGTH:
        raise ValidationError(
            'That address is longer than {} characters.'.format(EMAIL_MAX_LENGTH),
            code='email_length',
        )
    try:
        django_validate_email(email)
    except ValidationError:
        raise ValidationError(
            'That does not look like an email address.', code='email_malformed'
        ) from None
    return email

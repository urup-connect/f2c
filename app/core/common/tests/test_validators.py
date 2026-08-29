"""Tests for the shared validation rules.

The identity-number checks came first, and the rest arrived with registration.
A passing number means "not a typo", not "verified" -- so what is tested there
is that a typo is caught: the check digit, the embedded date, and the length.

The mobile, nickname, name and address rules exist because the registration
endpoint is unauthenticated. Each has a fuller counterpart in the frontend, so
what these assert is mostly the *floor*: that this side is not narrower than the
rule a member actually meets. A Python rule that refuses a name the browser
accepted would refuse a real member with no message they could act on, which is
the failure mode worth a test.
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from app.core.common.tests import VALID_SA_ID
from app.core.common.validators import (
    NON_MOBILE_PREFIXES,
    PERSON_NAME_MAX_LENGTH,
    RESERVED_NICKNAMES,
    is_at_least,
    nickname_key,
    normalise_sa_mobile_number,
    sa_id_birth_date,
    validate_email_address,
    validate_nickname,
    validate_person_name,
    validate_sa_id_number,
    validate_sa_mobile_number,
)


class SaIdValidatorTests(TestCase):
    def test_valid_number_passes_and_yields_birth_date(self):
        self.assertEqual(validate_sa_id_number(VALID_SA_ID), VALID_SA_ID)
        self.assertEqual(sa_id_birth_date(VALID_SA_ID), date(1980, 1, 1))

    def test_separators_are_tolerated(self):
        self.assertEqual(validate_sa_id_number('800101 5009 087'), VALID_SA_ID)

    def test_check_digit_is_enforced(self):
        with self.assertRaises(ValidationError):
            validate_sa_id_number('8001015009088')

    def test_impossible_date_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_sa_id_number('8013015009087')

    def test_wrong_length_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_sa_id_number('80010150090')


class AgeTests(TestCase):
    """Calendar arithmetic, part by part, and the same rule as the age gate.

    ``today`` is always an argument, so a date boundary is a test case rather
    than something that misbehaves only at midnight in production.
    """

    def test_the_birthday_itself_counts(self):
        self.assertTrue(is_at_least(date(2008, 8, 24), 18, date(2026, 8, 24)))

    def test_the_day_before_does_not(self):
        self.assertFalse(is_at_least(date(2008, 8, 25), 18, date(2026, 8, 24)))

    def test_a_29_february_birthday_waits_for_1_march(self):
        """No eighteenth birthday exists in a common year, so it is 1 March.

        The conservative side of a legal convention this code should not be
        inventing, and it matches ``frontend/club/lib/age-gate.ts`` deliberately.
        """
        born = date(2008, 2, 29)

        self.assertFalse(is_at_least(born, 18, date(2026, 2, 28)))
        self.assertTrue(is_at_least(born, 18, date(2026, 3, 1)))

    def test_an_unknown_date_of_birth_is_not_old_enough(self):
        self.assertFalse(is_at_least(None, 18, date(2026, 8, 24)))


class MobileNumberValidatorTests(TestCase):
    def test_every_form_a_member_might_write_reaches_one_value(self):
        for written in (
            '0821234567',
            '082 123 4567',
            '082-123-4567',
            '(082) 123.4567',
            '+27821234567',
            '+27 82 123 4567',
            '0027821234567',
            '27821234567',
        ):
            with self.subTest(written=written):
                self.assertEqual(validate_sa_mobile_number(written), '+27821234567')

    def test_the_service_ranges_are_refused(self):
        """Toll-free, share-call and VoIP reach a service, not a person."""
        for prefix in NON_MOBILE_PREFIXES:
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValidationError):
                    validate_sa_mobile_number(f'{prefix}1234567')

    def test_a_landline_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_sa_mobile_number('021 123 4567')

    def test_the_wrong_length_is_refused(self):
        for written in ('082 123 456', '082 123 45678'):
            with self.subTest(written=written):
                with self.assertRaises(ValidationError):
                    validate_sa_mobile_number(written)

    def test_a_slash_is_not_a_separator(self):
        """`082/123/4567` is usually two numbers, and guessing is worse."""
        with self.assertRaises(ValidationError):
            validate_sa_mobile_number('082/123/4567')

    def test_a_foreign_number_is_refused(self):
        with self.assertRaises(ValidationError):
            validate_sa_mobile_number('+44 7700 900000')

    def test_a_bare_27_only_counts_as_a_country_code_at_the_right_length(self):
        """Otherwise a national number that happens to start 27 loses two digits.

        Eleven digits beginning 27 is the country code and nine digits. Nine
        digits beginning 27 is not, and is refused as not a handset rather than
        quietly truncated into one.
        """
        self.assertEqual(normalise_sa_mobile_number('27821234567'), '+27821234567')
        self.assertEqual(normalise_sa_mobile_number('273456789'), '')

    def test_nothing_is_refused_rather_than_normalised(self):
        for written in ('', '   ', None, 'not a number'):
            with self.subTest(written=written):
                self.assertEqual(normalise_sa_mobile_number(written), '')


class NicknameValidatorTests(TestCase):
    def test_a_plain_nickname_is_accepted_as_typed(self):
        self.assertEqual(validate_nickname('  GrowerOne '), 'GrowerOne')

    def test_the_alphabet_is_ascii_only(self):
        """Deliberately, and unlike the name fields. A Cyrillic look-alike is
        impersonation, and restricting the alphabet removes the whole class."""
        for nickname in ('Grоwer', 'Grower​', 'Gröwer', 'Grower!'):
            with self.subTest(nickname=nickname):
                with self.assertRaises(ValidationError) as refused:
                    validate_nickname(nickname)
                self.assertEqual(refused.exception.code, 'nickname_characters')

    def test_the_alphabet_is_checked_before_the_length(self):
        """So a Cyrillic nickname is told what is wrong rather than counted."""
        with self.assertRaises(ValidationError) as refused:
            validate_nickname('Аб')

        self.assertEqual(refused.exception.code, 'nickname_characters')

    def test_the_length_bounds_hold(self):
        for nickname in ('ab', 'a' * 21):
            with self.subTest(nickname=nickname):
                with self.assertRaises(ValidationError) as refused:
                    validate_nickname(nickname)
                self.assertEqual(refused.exception.code, 'nickname_length')

    def test_the_shape_rules_hold(self):
        for nickname in ('1grower', '_grower', 'grower_', 'grower-', 'gro__wer'):
            with self.subTest(nickname=nickname):
                with self.assertRaises(ValidationError) as refused:
                    validate_nickname(nickname)
                self.assertEqual(refused.exception.code, 'nickname_shape')

    def test_a_reserved_name_is_refused_last(self):
        """A reserved name is a well-formed nickname that belongs to nobody."""
        for nickname in ('admin', 'Support', 'VERIFY', 'age-check'):
            with self.subTest(nickname=nickname):
                with self.assertRaises(ValidationError) as refused:
                    validate_nickname(nickname)
                self.assertEqual(refused.exception.code, 'nickname_unavailable')

    def test_the_reserved_list_is_held_in_the_comparable_form(self):
        """Otherwise an entry with a capital in it would never match anything."""
        for reserved in RESERVED_NICKNAMES:
            with self.subTest(reserved=reserved):
                self.assertEqual(nickname_key(reserved), reserved)

    def test_the_key_folds_case_but_not_separators(self):
        self.assertEqual(nickname_key('  GROWER '), 'grower')
        # `grow-er` and `grower` are two nicknames, not one.
        self.assertNotEqual(nickname_key('grow-er'), nickname_key('grower'))


class PersonNameValidatorTests(TestCase):
    def test_the_names_this_rule_refuses_to_refuse(self):
        """Every convention below, applied to South African names, rejects
        people who exist: two names, a vowel, a capital, more than one
        character, the Latin alphabet."""
        for name in (
            "O'Brien",
            'O’Brien',
            'Van der Merwe',
            'Ngcobo-Zulu',
            'X',
            'Sr.',
            '陳',
            'Nkosinathi',
        ):
            with self.subTest(name=name):
                self.assertEqual(validate_person_name(name), name)

    def test_what_is_not_a_name_at_all(self):
        for name in ('12345', 'member@example.com', '<script>', '---', '   '):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_person_name(name)

    def test_whitespace_is_collapsed_before_the_length_is_counted(self):
        """Three spaces a member did not mean to type must not fail them."""
        self.assertEqual(validate_person_name('  Thandiwe   Nomsa  '), 'Thandiwe Nomsa')

    def test_characters_are_checked_before_the_length(self):
        """"That is not a name" is the more useful complaint about a long
        string of digits."""
        with self.assertRaises(ValidationError) as refused:
            validate_person_name('1' * 200)

        self.assertEqual(refused.exception.code, 'name_characters')

    def test_too_long_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            validate_person_name('a' * (PERSON_NAME_MAX_LENGTH + 1))

        self.assertEqual(refused.exception.code, 'name_length')


class EmailValidatorTests(TestCase):
    def test_the_whole_address_is_lower_cased(self):
        """The local part too. One address must have exactly one stored form,
        or the same person becomes two members."""
        self.assertEqual(
            validate_email_address('  Member@Example.COM '), 'member@example.com'
        )

    def test_a_typo_is_refused(self):
        for email in ('not-an-address', 'member@', '@example.com', 'a b@example.com'):
            with self.subTest(email=email):
                with self.assertRaises(ValidationError):
                    validate_email_address(email)

    def test_a_blank_address_is_refused_as_missing(self):
        with self.assertRaises(ValidationError) as refused:
            validate_email_address('   ')

        self.assertEqual(refused.exception.code, 'email_missing')

    def test_an_absurd_length_is_refused(self):
        with self.assertRaises(ValidationError) as refused:
            validate_email_address('a' * 250 + '@example.com')

        self.assertEqual(refused.exception.code, 'email_length')

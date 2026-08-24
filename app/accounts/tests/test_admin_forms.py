"""Tests for the admin forms: the encrypted identity number, and the clashes.

The identity number field is write-only: staff can set it and can see the last
four digits, but the form never renders the number back. That makes the usual
safety net -- looking at the page to see whether the value took -- unavailable,
which is exactly why it is tested here.

Several rules are enforced in the form rather than left to the model, because a
form error is a better answer than an ``IntegrityError`` page: setting and
clearing an identity number in one submission is contradictory, a 13-digit entry
has to pass the RSA checks, and none of the three identity keys may already
belong to another account. The database constraints behind those last ones are
still the authority; the form only reaches them first.

Which keys need a hand-written check is not arbitrary. ``email`` is
``unique=True`` on the column, so ``ModelForm`` catches it unaided. The identity
number is unique on a blind index Django knows nothing about. The mobile number
and the nickname are unique under *conditional* constraints, which ``ModelForm``
validation does not reach -- verified by ``ContactClashTests`` below, which would
pass with a 500 rather than a form error if the mixin were removed.
"""
from datetime import date

from django.test import TestCase

from app.accounts.forms import UserChangeForm, UserCreationForm
from app.accounts.models import User, UserStatus
from app.common.tests import VALID_SA_ID

# Same date of birth, a different person: differs in the sequence digits.
OTHER_SA_ID = '8001015800006'
PASSWORD = 'Str0ng-Passphrase!'


class CreationFormTests(TestCase):
    def data(self, **overrides):
        fields = {
            'email': 'member@example.com',
            'first_name': 'Craig',
            'last_name': 'Mabaso',
            'nickname': 'Bean',
            'status': UserStatus.PENDING,
            'password1': PASSWORD,
            'password2': PASSWORD,
        }
        fields.update(overrides)
        return fields

    def test_an_account_can_be_created_without_an_id_number(self):
        form = UserCreationForm(data=self.data())

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertFalse(user.has_id_number)

    def test_a_valid_rsa_id_is_captured_and_dates_the_account(self):
        """Captured, not merely stored: the birth date comes off the document."""
        form = UserCreationForm(data=self.data(id_number=VALID_SA_ID))
        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()

        self.assertEqual(user.id_number, VALID_SA_ID)
        self.assertEqual(user.date_of_birth, date(1980, 1, 1))
        self.assertIsNotNone(user.date_of_birth_verified_at)

    def test_the_number_is_encrypted_and_indexed_on_the_way_in(self):
        form = UserCreationForm(data=self.data(id_number=VALID_SA_ID))
        form.is_valid()
        user = form.save()

        stored = User.objects.values_list('id_number_encrypted', flat=True).get(pk=user.pk)
        self.assertNotIn(VALID_SA_ID, stored)
        self.assertEqual(User.objects.by_id_number(VALID_SA_ID).get(), user)

    def test_separators_staff_type_are_tolerated(self):
        form = UserCreationForm(data=self.data(id_number='800101 5009 087'))
        self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(form.save().id_number, VALID_SA_ID)

    def test_a_thirteen_digit_number_that_fails_its_check_digit_is_rejected(self):
        form = UserCreationForm(data=self.data(id_number='8001015009088'))

        self.assertFalse(form.is_valid())
        self.assertEqual(User.objects.count(), 0)

    def test_a_foreign_document_is_taken_at_face_value(self):
        """A passport has no checksum to test, so there is nothing to check."""
        form = UserCreationForm(data=self.data(id_number='A1234567'))
        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()
        self.assertEqual(user.id_number, 'A1234567')
        # No document was read, so nothing may claim the birth date was verified.
        self.assertIsNone(user.date_of_birth)
        self.assertIsNone(user.date_of_birth_verified_at)

    def test_a_number_another_account_holds_is_refused(self):
        existing = User.objects.create_user(email='first@example.com')
        existing.capture_sa_id_number(VALID_SA_ID)
        existing.save()

        form = UserCreationForm(data=self.data(id_number=VALID_SA_ID))

        self.assertFalse(form.is_valid())
        self.assertIn('id_number', form.errors)

    def test_setting_and_clearing_at_once_is_refused(self):
        form = UserCreationForm(
            data=self.data(id_number=VALID_SA_ID, clear_id_number=True)
        )

        self.assertFalse(form.is_valid())

    def test_the_form_never_renders_a_number_back(self):
        """Write-only. The rendered widget must not carry the value."""
        user = User.objects.create_user(email='member@example.com')
        user.capture_sa_id_number(VALID_SA_ID)
        user.save()

        rendered = str(UserChangeForm(instance=user))

        self.assertNotIn(VALID_SA_ID, rendered)


class ChangeFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com',
            first_name='Craig',
            status=UserStatus.ACTIVE,
        )
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

    def data(self, **overrides):
        fields = {
            'email': 'member@example.com',
            'first_name': 'Craig',
            'last_name': '',
            'nickname': '',
            'status': UserStatus.ACTIVE,
            'date_of_birth': '1980-01-01',
        }
        fields.update(overrides)
        return fields

    def submit(self, **overrides):
        form = UserChangeForm(data=self.data(**overrides), instance=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_leaving_the_field_blank_keeps_the_number_on_file(self):
        """The most common submission: an edit to something else entirely."""
        user = self.submit(nickname='Bean')

        self.assertEqual(user.nickname, 'Bean')
        self.assertEqual(user.id_number, VALID_SA_ID)

    def test_a_new_number_replaces_the_old_one(self):
        user = self.submit(id_number=OTHER_SA_ID)

        self.assertEqual(user.id_number, OTHER_SA_ID)
        self.assertEqual(User.objects.by_id_number(VALID_SA_ID).count(), 0)

    def test_clearing_removes_the_number_and_its_index(self):
        user = self.submit(clear_id_number=True)

        self.assertFalse(user.has_id_number)
        self.assertIsNone(user.id_number_hash)

    def test_the_accounts_own_number_is_not_treated_as_a_clash(self):
        """Re-submitting the same number must not collide with itself."""
        form = UserChangeForm(data=self.data(id_number=VALID_SA_ID), instance=self.user)

        self.assertTrue(form.is_valid(), form.errors)

    def test_another_accounts_number_is_still_a_clash(self):
        other = User.objects.create_user(email='other@example.com')
        other.capture_sa_id_number(OTHER_SA_ID)
        other.save()

        form = UserChangeForm(data=self.data(id_number=OTHER_SA_ID), instance=self.user)

        self.assertFalse(form.is_valid())
        self.assertIn('id_number', form.errors)

    def test_is_active_cannot_be_submitted(self):
        """It is derived from status, and a form field would let it drift."""
        self.assertNotIn('is_active', UserChangeForm.base_fields)

    def test_changing_status_still_moves_is_active(self):
        user = self.submit(status=UserStatus.SUSPENDED)
        user.refresh_from_db()

        self.assertFalse(user.is_active)


class MaskingTests(TestCase):
    """What the admin list shows instead of the number itself."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite

        from app.accounts.admin import UserAdmin

        self.admin = UserAdmin(User, AdminSite())
        self.user = User.objects.create_user(email='member@example.com')

    def test_an_account_with_no_number_shows_a_dash(self):
        self.assertEqual(self.admin.id_number_masked(self.user), '--')

    def test_only_the_last_four_digits_are_shown(self):
        self.user.capture_sa_id_number(VALID_SA_ID)

        masked = self.admin.id_number_masked(self.user)

        self.assertEqual(masked, '*********' + VALID_SA_ID[-4:])
        self.assertNotIn(VALID_SA_ID, masked)

    def test_the_mask_hides_the_length_of_nothing_it_should_not(self):
        """Same length as the number, so a passport is not mistaken for an ID."""
        self.user.id_number = 'A1234567'

        self.assertEqual(len(self.admin.id_number_masked(self.user)), 8)

    def test_an_unreadable_row_is_surfaced_rather_than_hidden(self):
        """A row that will not decrypt is a key or integrity problem, not a blank."""
        self.user.id_number_encrypted = 'not-a-ciphertext'

        self.assertEqual(self.admin.id_number_masked(self.user), 'UNREADABLE')


class AdminSearchTests(TestCase):
    """The encrypted column cannot be searched with SQL, so search is extended."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from app.accounts.admin import UserAdmin

        self.admin = UserAdmin(User, AdminSite())
        self.request = RequestFactory().get('/admin/api/user/')
        self.user = User.objects.create_user(
            email='member@example.com', first_name='Craig'
        )
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

    def search(self, term):
        results, _ = self.admin.get_search_results(
            self.request, User.objects.all(), term
        )
        return list(results)

    def test_a_full_id_number_finds_the_account(self):
        self.assertEqual(self.search(VALID_SA_ID), [self.user])

    def test_the_ordinary_fields_still_search(self):
        self.assertEqual(self.search('Craig'), [self.user])

    def test_a_partial_number_finds_nothing(self):
        """A blind index answers equality and nothing else: no browsing by prefix."""
        self.assertEqual(self.search(VALID_SA_ID[:8]), [])

    def test_a_wrong_number_finds_nothing(self):
        self.assertEqual(self.search(OTHER_SA_ID), [])


class ContactClashTests(TestCase):
    """The two identity keys Django's own form validation does not reach.

    ``email`` is ``unique=True`` on the column, so ``ModelForm`` catches a
    clash by itself. The mobile number and the nickname are enforced by partial
    unique constraints instead, and a condition puts them outside what
    ``ModelForm`` validates -- so without the checks in ``ContactClashMixin`` a
    member of staff making an ordinary mistake would get a 500 rather than a
    sentence beside the field.

    The identity number's equivalent is covered by ``CreationFormTests`` and
    ``ChangeFormTests`` above; this is the same rule for the other two.
    """

    def setUp(self):
        self.held = User.objects.create_user(
            email='held@example.com', mobile='0821234567', nickname='Grower'
        )
        self.other = User.objects.create_user(email='other@example.com')

    def data(self, **overrides):
        fields = {
            'email': 'other@example.com',
            'password': self.other.password,
            'first_name': '',
            'last_name': '',
            'nickname': '',
            'mobile': '',
            'status': UserStatus.PENDING,
            'date_of_birth': '',
            'is_staff': '',
            'is_superuser': '',
            'groups': [],
            'user_permissions': [],
            'id_number': '',
            'clear_id_number': '',
        }
        fields.update(overrides)
        return fields

    def form(self, **overrides):
        return UserChangeForm(data=self.data(**overrides), instance=self.other)

    # ------------------------------------------------------------------
    # Mobile number
    # ------------------------------------------------------------------

    def test_a_held_mobile_number_is_refused_against_the_field(self):
        form = self.form(mobile='0821234567')

        self.assertFalse(form.is_valid())
        self.assertIn('mobile', form.errors)

    def test_punctuation_is_not_a_way_round_the_form_either(self):
        """The form compares the normalised value, as the constraint indexes it.

        Comparing the raw text would let every other spelling of the same
        handset past the form and into an IntegrityError.
        """
        for written in ('082 123 4567', '+27821234567', '(082) 123-4567', '0027821234567'):
            with self.subTest(written=written):
                form = self.form(mobile=written)

                self.assertFalse(form.is_valid())
                self.assertIn('mobile', form.errors)

    def test_a_number_that_is_not_a_handset_says_so_instead(self):
        """A different complaint from being taken, and it must not be conflated."""
        form = self.form(mobile='086 123 4567')

        self.assertFalse(form.is_valid())
        self.assertIn('mobile', form.errors)
        self.assertNotIn('already holds', ' '.join(form.errors['mobile']))

    def test_a_free_number_is_accepted_and_stored_normalised(self):
        form = self.form(mobile='083 555 1234')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().mobile, '+27835551234')

    def test_a_member_may_keep_their_own_number(self):
        """Otherwise editing any other field on the page would refuse the save."""
        form = UserChangeForm(
            data=self.data(email='held@example.com', password=self.held.password,
                           mobile='0821234567', nickname='Grower', first_name='Craig'),
            instance=self.held,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_no_number_is_allowed(self):
        form = self.form(mobile='')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().mobile, '')

    # ------------------------------------------------------------------
    # Nickname
    # ------------------------------------------------------------------

    def test_a_held_nickname_is_refused_against_the_field(self):
        form = self.form(nickname='Grower')

        self.assertFalse(form.is_valid())
        self.assertIn('nickname', form.errors)

    def test_case_is_not_a_way_round_the_form_either(self):
        for written in ('GROWER', 'grower', 'GrOwEr'):
            with self.subTest(written=written):
                form = self.form(nickname=written)

                self.assertFalse(form.is_valid())
                self.assertIn('nickname', form.errors)

    def test_a_free_nickname_is_accepted(self):
        form = self.form(nickname='Grower2')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().nickname, 'Grower2')

    def test_a_member_may_keep_their_own_nickname(self):
        form = UserChangeForm(
            data=self.data(email='held@example.com', password=self.held.password,
                           mobile='0821234567', nickname='Grower', last_name='Mabaso'),
            instance=self.held,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_no_nickname_is_allowed(self):
        """Staff have none, and two staff accounts must not collide."""
        form = self.form(nickname='')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().nickname, '')

    # ------------------------------------------------------------------
    # Creating rather than editing
    # ------------------------------------------------------------------

    def test_the_creation_form_refuses_a_held_number_too(self):
        form = UserCreationForm(
            data={
                'email': 'new@example.com',
                'first_name': 'Craig',
                'last_name': 'Mabaso',
                'nickname': 'Grower3',
                'mobile': '082 123 4567',
                'status': UserStatus.PENDING,
                'password1': PASSWORD,
                'password2': PASSWORD,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('mobile', form.errors)

    def test_the_creation_form_refuses_a_held_nickname_too(self):
        form = UserCreationForm(
            data={
                'email': 'new@example.com',
                'first_name': 'Craig',
                'last_name': 'Mabaso',
                'nickname': 'grower',
                'mobile': '083 555 1234',
                'status': UserStatus.PENDING,
                'password1': PASSWORD,
                'password2': PASSWORD,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('nickname', form.errors)

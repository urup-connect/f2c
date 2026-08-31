"""Tests for what a member may change about themselves, and what they may not.

Two properties dominate, and both are the kind that look fine when broken.

The first is that the read-only fields stay read-only. A date of birth and an
identity number came off a document; a payload that can rewrite either has made
``date_of_birth_verified_at`` a claim the record no longer supports. So the
assertions are about fields the endpoint was *not* asked to change and did not.

The second is that the identity number never crosses the wire whole. Every
response is checked for the plaintext, not merely for the masked form being
present -- an extra field added by hand to ``ProfileOut`` would satisfy a
positive assertion and fail these.

``MEDIA_ROOT`` is overridden per class onto a temporary directory. Without it the
suite writes avatars into the developer's own ``media/`` and leaves them there.
"""
import io
import json
import shutil
import tempfile
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from app.core.accounts import profile
from app.core.accounts.models import User, UserStatus
from app.core.common.tests import VALID_SA_ID
from f2c.testing import make_member

STORED_MOBILE = '+27821234567'
OTHER_MOBILE = '+27837654321'


def jpeg_bytes(size=(600, 400)):
    buffer = io.BytesIO()
    Image.new('RGB', size, (120, 160, 90)).save(buffer, format='JPEG')
    return buffer.getvalue()


def active_member(email='member@example.com', mobile=STORED_MOBILE, **extra):
    """An account with an **active club membership**.

    The membership used to be load-bearing: `manage_own_profile` was granted by
    a relationship, so a bare account held no permissions and every test here
    would have got a 403 for the wrong reason. **It is decoration now** — the
    codename is retired and these endpoints ask only for an active account — and
    it is kept because a club member is still a realistic caller and because
    `id_number` and `nickname` on the fixture belong to a membership.

    `StoreCustomerTests` is the class that covers the bare account, and it is
    the one this change exists for.
    """
    user = User.objects.create_user(
        email=email,
        first_name='Thandi',
        last_name='Mokoena',
        mobile=mobile,
        status=UserStatus.ACTIVE,
        **extra,
    )
    # From the address, so a test creating a second member does not collide
    # on the nickname index — which is exactly the rule under test elsewhere.
    return make_member(email, email.split('@')[0], account=user)


class UpdateProfileTests(TestCase):
    def setUp(self):
        self.user = active_member()

    def test_the_three_editable_fields_are_written(self):
        profile.update_profile(
            self.user,
            first_name='  Thandiwe  ',
            last_name='Mokoena-Smith',
            mobile='083 765 4321',
        )
        self.user.refresh_from_db()

        self.assertEqual(self.user.first_name, 'Thandiwe')
        self.assertEqual(self.user.last_name, 'Mokoena-Smith')
        # Normalised on the way in, so the stored form is the only form. That
        # is what stops one handset becoming two members.
        self.assertEqual(self.user.mobile, OTHER_MOBILE)

    def test_a_blank_mobile_number_clears_the_column(self):
        # A contact detail, not a credential. A member who no longer has the
        # handset should be able to say so rather than leave the club a wrong
        # number to ring.
        profile.update_profile(
            self.user, first_name='Thandi', last_name='Mokoena', mobile='  '
        )
        self.user.refresh_from_db()

        self.assertEqual(self.user.mobile, '')

    def test_the_read_only_fields_are_untouched(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()
        born = self.user.date_of_birth
        verified = self.user.date_of_birth_verified_at

        profile.update_profile(
            self.user, first_name='Ann', last_name='Bee', mobile=STORED_MOBILE
        )
        self.user.refresh_from_db()

        self.assertEqual(self.user.date_of_birth, born)
        self.assertEqual(self.user.date_of_birth_verified_at, verified)
        self.assertEqual(self.user.id_number, VALID_SA_ID)
        # Neither is in the editable set, and the set is what the endpoint
        # above is written against.
        self.assertNotIn('date_of_birth', profile.EDITABLE_FIELDS)
        self.assertNotIn('id_number', profile.EDITABLE_FIELDS)

    def test_the_nickname_and_email_are_untouched(self):
        profile.update_profile(
            self.user, first_name='Ann', last_name='Bee', mobile=''
        )
        self.user.refresh_from_db()

        self.assertEqual(self.user.club_nickname, 'member')
        self.assertEqual(self.user.email, 'member@example.com')

    def test_a_number_another_account_holds_is_refused(self):
        active_member(email='other@example.com', mobile=OTHER_MOBILE)

        with self.assertRaises(profile.MobileUnavailable):
            profile.update_profile(
                self.user,
                first_name='Ann',
                last_name='Bee',
                mobile='083 765 4321',
            )

        self.user.refresh_from_db()
        # Nothing partial: the refused number did not take the new names with
        # it into the record.
        self.assertEqual(self.user.first_name, 'Thandi')
        self.assertEqual(self.user.mobile, STORED_MOBILE)

    def test_keeping_your_own_number_is_not_a_collision(self):
        # The obvious regression: excluding the caller's own row is what makes
        # a member able to save the form without changing their number.
        profile.update_profile(
            self.user,
            first_name='Ann',
            last_name='Bee',
            mobile=STORED_MOBILE,
        )
        self.user.refresh_from_db()

        self.assertEqual(self.user.mobile, STORED_MOBILE)

    def test_a_number_written_differently_is_still_the_same_handset(self):
        active_member(email='other@example.com', mobile=OTHER_MOBILE)

        with self.assertRaises(profile.MobileUnavailable):
            profile.update_profile(
                self.user,
                first_name='Ann',
                last_name='Bee',
                # The same handset as `OTHER_MOBILE`, punctuated by hand. A
                # check that compared raw text would let this through and the
                # database would then refuse the write for a reason the member
                # never sees.
                mobile='(083) 765-4321',
            )

    def test_every_bad_field_is_named_rather_than_the_first_one(self):
        with self.assertRaises(ValidationError) as caught:
            profile.update_profile(
                self.user,
                first_name='12345',
                last_name='',
                mobile='0800123456',
            )

        self.assertEqual(
            set(caught.exception.message_dict),
            {'first_name', 'last_name', 'mobile'},
        )

    def test_a_refused_field_writes_nothing_at_all(self):
        with self.assertRaises(ValidationError):
            profile.update_profile(
                self.user,
                first_name='Ann',
                last_name='Bee',
                mobile='0861234567',
            )

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Thandi')

    def test_a_toll_free_number_is_not_a_handset(self):
        with self.assertRaises(ValidationError) as caught:
            profile.update_profile(
                self.user, first_name='Ann', last_name='Bee', mobile='0860001234'
            )

        self.assertIn('mobile', caught.exception.message_dict)

    def test_a_suspended_account_may_not_write(self):
        # The floor under the endpoint rather than a gate anybody meets: a
        # suspended account cannot hold a session, so this is reachable only
        # from the shell or a command. It used to read as "holds no permissions"
        # and now reads `is_active` directly, which is the same fact stated where
        # it is decided -- `is_active` derives from `status` under a check
        # constraint.
        self.user.status = UserStatus.SUSPENDED
        self.user.save()

        with self.assertRaises(PermissionDenied):
            profile.update_profile(
                self.user, first_name='Ann', last_name='Bee', mobile=''
            )


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='avatar-service-'))
class AvatarServiceTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = active_member()

    def test_storing_an_avatar_sets_the_column_and_the_stamp(self):
        profile.set_avatar(self.user, jpeg_bytes())
        self.user.refresh_from_db()

        self.assertTrue(self.user.has_avatar)
        self.assertIsNotNone(self.user.avatar_updated_at)

    def test_the_stored_path_carries_the_account_and_not_the_file_name(self):
        profile.set_avatar(self.user, jpeg_bytes())
        self.user.refresh_from_db()

        self.assertIn(str(self.user.pk), self.user.avatar.name)
        self.assertTrue(self.user.avatar.name.endswith('avatar.jpg'))

    def test_what_is_stored_is_the_re_encoded_square(self):
        profile.set_avatar(self.user, jpeg_bytes(size=(1200, 300)))
        self.user.refresh_from_db()

        with self.user.avatar.open('rb') as handle:
            stored = Image.open(io.BytesIO(handle.read()))

        self.assertEqual(stored.format, 'JPEG')
        self.assertEqual(stored.size, (512, 512))

    def test_a_replacement_keeps_one_file_and_moves_the_stamp(self):
        profile.set_avatar(self.user, jpeg_bytes())
        self.user.refresh_from_db()
        first_path, first_stamp = self.user.avatar.name, self.user.avatar_updated_at

        profile.set_avatar(self.user, jpeg_bytes(size=(800, 800)))
        self.user.refresh_from_db()

        # One path per account, overwritten. A member who replaced their picture
        # has no history the club should be holding.
        self.assertEqual(self.user.avatar.name, first_path)
        self.assertGreaterEqual(self.user.avatar_updated_at, first_stamp)

    def test_a_refused_upload_leaves_the_existing_photograph_alone(self):
        profile.set_avatar(self.user, jpeg_bytes())
        self.user.refresh_from_db()
        stamp = self.user.avatar_updated_at

        with self.assertRaises(ValidationError):
            profile.set_avatar(self.user, b'not an image')

        self.user.refresh_from_db()
        self.assertTrue(self.user.has_avatar)
        self.assertEqual(self.user.avatar_updated_at, stamp)

    def test_clearing_removes_the_stored_file_as_well_as_the_column(self):
        profile.set_avatar(self.user, jpeg_bytes())
        self.user.refresh_from_db()
        storage, name = self.user.avatar.storage, self.user.avatar.name

        profile.clear_avatar(self.user)
        self.user.refresh_from_db()

        self.assertFalse(self.user.has_avatar)
        self.assertIsNone(self.user.avatar_updated_at)
        # The blob goes too. An erasure that unlinks a photograph but leaves it
        # in storage is not an erasure.
        self.assertFalse(storage.exists(name))

    def test_clearing_an_account_with_no_photograph_is_not_an_error(self):
        profile.clear_avatar(self.user)

        self.assertFalse(self.user.has_avatar)

    def test_erasing_the_account_deletes_the_photograph(self):
        profile.set_avatar(self.user, jpeg_bytes())
        self.user.refresh_from_db()
        storage, name = self.user.avatar.storage, self.user.avatar.name

        self.user.soft_delete()

        self.assertFalse(storage.exists(name))
        self.assertFalse(self.user.has_avatar)


class ProfileOfTests(TestCase):
    def setUp(self):
        self.user = active_member()

    def test_the_identity_number_appears_only_masked(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

        payload = profile.profile_of(self.user)

        self.assertTrue(payload['has_id_number'])
        self.assertEqual(payload['id_number_masked'], '*' * 9 + VALID_SA_ID[-4:])
        # The plaintext appears nowhere in the payload, under any key. An extra
        # field added by hand would pass a positive assertion and fail this.
        self.assertNotIn(VALID_SA_ID, json.dumps(payload, default=str))

    def test_an_account_with_no_document_reports_nothing_rather_than_stars(self):
        payload = profile.profile_of(self.user)

        self.assertFalse(payload['has_id_number'])
        self.assertEqual(payload['id_number_masked'], '')

    def test_the_date_of_birth_comes_from_the_document(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

        payload = profile.profile_of(self.user)

        self.assertEqual(payload['date_of_birth'], self.user.date_of_birth)
        self.assertIsNotNone(payload['date_of_birth_verified_at'])

    def test_no_photograph_means_no_address_rather_than_one_that_404s(self):
        payload = profile.profile_of(self.user)

        self.assertFalse(payload['has_avatar'])
        self.assertIsNone(payload['avatar_url'])

    def test_the_avatar_address_carries_a_version(self):
        self.user.avatar = 'avatars/x/avatar.jpg'
        self.user.avatar_updated_at = timezone.now()

        url = profile.avatar_url(self.user)

        self.assertTrue(url.startswith('/api/accounts/me/avatar?v='))
        stamp = int(url.rsplit('=', 1)[1])
        self.assertEqual(stamp, int(self.user.avatar_updated_at.timestamp()))

    def test_the_version_changes_when_the_photograph_does(self):
        # The whole reason the stamp exists: every avatar is written to the same
        # path, so without this a member who has just replaced their picture is
        # shown the cached previous one and concludes the upload failed.
        self.user.avatar = 'avatars/x/avatar.jpg'
        self.user.avatar_updated_at = timezone.now()
        before = profile.avatar_url(self.user)

        self.user.avatar_updated_at = self.user.avatar_updated_at + timedelta(
            seconds=30
        )

        self.assertNotEqual(before, profile.avatar_url(self.user))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='avatar-customer-'))
class StoreCustomerTests(TestCase):
    """A produce-market customer manages their own profile.

    **This is the class the codename was retired for.** A store customer is a
    ``User`` with no ``ClubMembership``, no ``StorefrontStaff`` and no
    ``ProducerMembership`` -- ``design/verticals.md`` section 6 -- so
    ``permissions_for`` returns an empty set, and while the profile endpoints
    asked for ``platform.manage_own_profile`` that empty set refused them their
    own name and photograph.

    Every assertion here is about an account with no relationship at all. If a
    codename comes back to guard these endpoints, this class is what fails.
    """

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.customer = User.objects.create_user(
            email='shopper@example.com',
            first_name='Ayanda',
            last_name='Zulu',
            mobile='+27821234567',
            status=UserStatus.ACTIVE,
        )

    def test_the_customer_really_does_hold_no_permissions(self):
        """The premise, asserted rather than assumed.

        Without this the three tests below could pass because the customer
        quietly acquired a relationship, which is the failure they exist to
        rule out.
        """
        self.assertEqual(self.customer.get_all_permissions(), set())

    def test_they_may_change_their_own_name(self):
        profile.update_profile(
            self.customer, first_name='Ayanda', last_name='Khumalo', mobile=''
        )

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.last_name, 'Khumalo')
        self.assertEqual(self.customer.mobile, '')

    def test_they_may_set_an_avatar(self):
        profile.set_avatar(self.customer, jpeg_bytes())

        self.customer.refresh_from_db()
        self.assertTrue(self.customer.has_avatar)

    def test_they_may_clear_an_avatar(self):
        profile.set_avatar(self.customer, jpeg_bytes())

        profile.clear_avatar(self.customer)

        self.customer.refresh_from_db()
        self.assertFalse(self.customer.has_avatar)

    def test_their_profile_reads_back_with_no_nickname(self):
        """`display_name` falls back and `nickname` is blank, not absent.

        A customer has a name and needs no pseudonym -- the nickname lives on
        `ClubMembership` since C27 -- so the field a club member fills is empty
        here rather than missing, and the screen renders the same shape.
        """
        data = profile.profile_of(self.customer)

        self.assertEqual(data['nickname'], '')
        self.assertEqual(data['id_number_masked'], '')

    def test_a_suspended_customer_may_not_write(self):
        """The floor holds for a customer exactly as it does for a member."""
        self.customer.status = UserStatus.SUSPENDED
        self.customer.save()

        with self.assertRaises(PermissionDenied):
            profile.update_profile(
                self.customer, first_name='Ayanda', last_name='Zulu', mobile=''
            )

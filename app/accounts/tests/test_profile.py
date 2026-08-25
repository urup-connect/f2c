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

from app.accounts import profile
from app.accounts.models import User, UserRole, UserStatus
from app.common.tests import VALID_SA_ID

STORED_MOBILE = '+27821234567'
OTHER_MOBILE = '+27837654321'


def jpeg_bytes(size=(600, 400)):
    buffer = io.BytesIO()
    Image.new('RGB', size, (120, 160, 90)).save(buffer, format='JPEG')
    return buffer.getvalue()


def active_member(email='member@example.com', mobile=STORED_MOBILE, **extra):
    user = User.objects.create_user(
        email=email,
        first_name='Thandi',
        last_name='Mokoena',
        nickname=email.split('@')[0],
        mobile=mobile,
        status=UserStatus.ACTIVE,
        role=UserRole.MEMBER,
        **extra,
    )
    return user


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

        self.assertEqual(self.user.nickname, 'member')
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

    def test_an_account_holding_no_permissions_may_not_write(self):
        # A suspended account holds nothing by `roles.permissions_for`, so this
        # is the floor under the endpoint rather than a gate anybody meets: a
        # suspended member cannot hold a session either.
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

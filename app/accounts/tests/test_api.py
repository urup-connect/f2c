"""Tests for the profile endpoints: the HTTP surface a member's own screen uses.

Three properties dominate here, and each is about the endpoint rather than the
service beneath it.

**Nothing is readable without a session.** Five endpoints, five 401s. Said out
loud because ``GET /me/avatar`` is the only endpoint in the project that answers
with something other than JSON, and a non-JSON response is exactly the kind that
gets wired up outside the authenticated router by accident.

**One account cannot reach another's photograph.** There is no account
identifier in any path here, so the test is that the response follows the session
and nothing else -- two members, two avatars, each getting their own.

**The identity number never crosses the wire whole.** Asserted against the raw
response body, so a field added by hand to ``ProfileOut`` fails it.

The avatar responses are checked for their cache headers as well as their bytes.
``private`` and ``Vary: Cookie`` are what stop an intermediary holding one
member's photograph and handing it to the next caller, and neither is visible in
a body.
"""
import io
import json
import shutil
import tempfile

from django.conf import settings
from django.test import Client, TestCase, override_settings
from PIL import Image

from app.accounts.models import User, UserRole, UserStatus
from app.common.tests import VALID_SA_ID

PROFILE_URL = '/api/accounts/me/profile'
AVATAR_URL = '/api/accounts/me/avatar'

PASSWORD = 'Str0ng-Passphrase!'


def jpeg_bytes(size=(600, 400), colour=(120, 160, 90)):
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, format='JPEG')
    return buffer.getvalue()


def upload(name='face.jpg', data=None, content_type='image/jpeg'):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(
        name, data if data is not None else jpeg_bytes(), content_type
    )


class ProfileApiTestCase(TestCase):
    """A signed-in member, reached the way the frontend reaches them.

    A password is set purely so the test client can log in: members sign in with
    a passkey or an emailed code, neither of which a test client can perform.
    What is under test is what the endpoint does with a session, not how the
    session was obtained.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='member@example.com',
            password=PASSWORD,
            first_name='Thandi',
            last_name='Mokoena',
            nickname='thandi',
            mobile='+27821234567',
            status=UserStatus.ACTIVE,
            role=UserRole.MEMBER,
        )
        self.client = Client()
        self.client.force_login(self.user)


class AuthenticationTests(TestCase):
    def test_every_endpoint_refuses_a_caller_with_no_session(self):
        client = Client()

        self.assertEqual(client.get(PROFILE_URL).status_code, 401)
        self.assertEqual(
            client.put(
                PROFILE_URL, data='{}', content_type='application/json'
            ).status_code,
            401,
        )
        self.assertEqual(client.post(AVATAR_URL).status_code, 401)
        self.assertEqual(client.delete(AVATAR_URL).status_code, 401)
        # The one endpoint that answers with bytes rather than JSON, and the
        # reason this test names all five rather than trusting the router.
        self.assertEqual(client.get(AVATAR_URL).status_code, 401)


class ReadProfileTests(ProfileApiTestCase):
    def test_it_returns_the_record_the_screen_draws(self):
        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['first_name'], 'Thandi')
        self.assertEqual(body['nickname'], 'thandi')
        self.assertEqual(body['mobile'], '+27821234567')
        self.assertEqual(body['email'], 'member@example.com')

    def test_the_identity_number_is_masked_and_the_plaintext_is_absent(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

        response = self.client.get(PROFILE_URL)

        body = response.json()
        self.assertTrue(body['has_id_number'])
        self.assertEqual(body['id_number_masked'], '*' * 9 + VALID_SA_ID[-4:])
        # Against the raw body, not the parsed one: a field added by hand to
        # ProfileOut would satisfy the assertion above and fail this.
        self.assertNotIn(VALID_SA_ID, response.content.decode())

    def test_the_date_of_birth_is_reported_with_whether_it_was_verified(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()

        body = self.client.get(PROFILE_URL).json()

        self.assertEqual(body['date_of_birth'], '1980-01-01')
        self.assertIsNotNone(body['date_of_birth_verified_at'])

    def test_a_member_with_no_document_is_told_so_rather_than_shown_stars(self):
        body = self.client.get(PROFILE_URL).json()

        self.assertFalse(body['has_id_number'])
        self.assertEqual(body['id_number_masked'], '')
        self.assertIsNone(body['date_of_birth'])


class WriteProfileTests(ProfileApiTestCase):
    def put(self, **payload):
        return self.client.put(
            PROFILE_URL, data=json.dumps(payload), content_type='application/json'
        )

    def test_a_saved_form_answers_with_the_record_as_it_now_stands(self):
        response = self.put(
            first_name='Thandiwe', last_name='Mokoena-Smith', mobile='083 765 4321'
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['first_name'], 'Thandiwe')
        # Read back rather than echoed, so the member sees the number the club
        # will ring instead of the punctuation they typed.
        self.assertEqual(body['mobile'], '+27837654321')

    def test_a_number_another_account_holds_is_a_409_that_names_itself(self):
        User.objects.create_user(
            email='other@example.com',
            mobile='+27837654321',
            status=UserStatus.ACTIVE,
            role=UserRole.MEMBER,
        )

        response = self.put(
            first_name='Thandi', last_name='Mokoena', mobile='083 765 4321'
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()['mobile_unavailable'])

    def test_an_unacceptable_field_is_a_422_naming_the_field(self):
        response = self.put(first_name='12345', last_name='', mobile='')

        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(set(body['fields']), {'first_name', 'last_name'})
        self.assertFalse(body['mobile_unavailable'])

    def test_a_refused_write_changes_nothing(self):
        self.put(first_name='', last_name='', mobile='')

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Thandi')

    def test_the_read_only_fields_cannot_be_written_through_this_endpoint(self):
        self.user.capture_sa_id_number(VALID_SA_ID)
        self.user.save()
        born = self.user.date_of_birth

        response = self.client.put(
            PROFILE_URL,
            data=json.dumps(
                {
                    'first_name': 'Thandi',
                    'last_name': 'Mokoena',
                    'mobile': '',
                    # Every field the screen shows and does not let a member
                    # change. django-ninja ignores what ProfileIn does not
                    # declare; this asserts that it stays ignored.
                    'date_of_birth': '1990-05-05',
                    'id_number': '9005054800086',
                    'nickname': 'somebodyelse',
                    'email': 'attacker@example.com',
                    'role': 'admin',
                    'status': 'active',
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.date_of_birth, born)
        self.assertEqual(self.user.id_number, VALID_SA_ID)
        self.assertEqual(self.user.nickname, 'thandi')
        self.assertEqual(self.user.email, 'member@example.com')
        self.assertEqual(self.user.role, UserRole.MEMBER)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='avatar-api-'))
class AvatarApiTests(ProfileApiTestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def test_an_upload_answers_with_an_address_carrying_a_version(self):
        response = self.client.post(AVATAR_URL, {'image': upload()})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['has_avatar'])
        self.assertRegex(body['avatar_url'], r'^/api/accounts/me/avatar\?v=\d+$')

    def test_the_address_changes_when_the_photograph_is_replaced(self):
        first = self.client.post(AVATAR_URL, {'image': upload()}).json()

        # The stamp has whole-second resolution, so a second upload in the same
        # second would produce the same address. Moved by hand rather than by
        # sleeping: what is under test is that the address is built from the
        # stamp, not that the clock advances.
        self.user.refresh_from_db()
        self.user.avatar_updated_at = self.user.avatar_updated_at.replace(
            microsecond=0
        ) - __import__('datetime').timedelta(seconds=5)
        self.user.save()

        second = self.client.get(PROFILE_URL).json()

        self.assertNotEqual(first['avatar_url'], second['avatar_url'])

    def test_a_file_that_is_not_an_image_is_a_422(self):
        response = self.client.post(
            AVATAR_URL, {'image': upload(data=b'a text file', name='face.jpg')}
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn('detail', response.json())

    def test_a_lie_about_the_content_type_does_not_help(self):
        # The declared type is never trusted. What decides is whether the bytes
        # decode, which is the whole reason every upload is re-encoded.
        response = self.client.post(
            AVATAR_URL,
            {'image': upload(data=b'<script>alert(1)</script>', name='x.jpg')},
        )

        self.assertEqual(response.status_code, 422)

    def test_the_stored_photograph_is_streamed_back_as_a_jpeg(self):
        self.client.post(AVATAR_URL, {'image': upload()})

        response = self.client.get(AVATAR_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        streamed = b''.join(response.streaming_content)
        self.assertEqual(Image.open(io.BytesIO(streamed)).size, (512, 512))

    def test_the_response_may_not_be_held_by_a_shared_cache(self):
        # Neither header is visible in a body, and both are what stop an
        # intermediary handing one member's photograph to the next caller.
        self.client.post(AVATAR_URL, {'image': upload()})

        response = self.client.get(AVATAR_URL)

        self.assertIn('private', response['Cache-Control'])
        # `in` rather than equality: corsheaders adds `Origin` to the same
        # header, so the assertion is that Cookie is among what this varies on
        # rather than that it is the only thing.
        self.assertIn('Cookie', response['Vary'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')

    def test_a_member_with_no_photograph_gets_a_404(self):
        self.assertEqual(self.client.get(AVATAR_URL).status_code, 404)

    def test_one_member_cannot_reach_another_members_photograph(self):
        """The response follows the session, and there is no path that says
        otherwise -- no endpoint here takes an account identifier."""
        self.client.post(AVATAR_URL, {'image': upload(data=jpeg_bytes(colour=(255, 0, 0)))})

        other = User.objects.create_user(
            email='other@example.com',
            password=PASSWORD,
            status=UserStatus.ACTIVE,
            role=UserRole.MEMBER,
        )
        other_client = Client()
        other_client.force_login(other)

        # Same URL, different session, and the second member has no photograph.
        self.assertEqual(other_client.get(AVATAR_URL).status_code, 404)

        other_client.post(
            AVATAR_URL, {'image': upload(data=jpeg_bytes(colour=(0, 0, 255)))}
        )

        mine = b''.join(self.client.get(AVATAR_URL).streaming_content)
        theirs = b''.join(other_client.get(AVATAR_URL).streaming_content)
        self.assertNotEqual(mine, theirs)

    def test_deleting_takes_the_photograph_down_and_answers_200(self):
        self.client.post(AVATAR_URL, {'image': upload()})

        response = self.client.delete(AVATAR_URL)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body['has_avatar'])
        self.assertIsNone(body['avatar_url'])
        self.assertEqual(self.client.get(AVATAR_URL).status_code, 404)

    def test_deleting_when_there_is_nothing_to_delete_is_still_200(self):
        # A 404 would have the screen report a failure for having got exactly
        # what it asked for.
        response = self.client.delete(AVATAR_URL)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['has_avatar'])

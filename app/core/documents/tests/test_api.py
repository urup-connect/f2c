"""Tests for the club-document endpoints.

``/current`` is the one the sign-up page depends on, and the important case is
the unhappy one: 503 when a required document has no published revision, rather
than 200 carrying a short list. A caller cannot tell an incomplete list from a
complete one, so the endpoint has to.
"""
import json
from unittest.mock import PropertyMock, patch

from app.core.accounts.models import UserStatus
from app.core.documents.models import DocumentConsent, DocumentVersion

from .support import DocumentsTestCase


class DocumentApiTestCase(DocumentsTestCase):
    def body(self, response):
        return json.loads(response.content)

    def publish_all(self, **extra):
        return {
            slug: self.published(
                document=self.document(slug),
                label=extra.get('label', '1'),
                content=f'{slug} body'.encode(),
            )
            for slug in ('club-rules', 'annexures', 'constitution')
        }

    def signed_in_member(self, email='member@example.com'):
        """An Active member, since only Active accounts can hold a session."""
        member = self.member(email)
        member.status = UserStatus.ACTIVE
        member.save()
        self.client.force_login(member)
        return member


class CurrentDocumentsTests(DocumentApiTestCase):
    def test_it_needs_no_session(self):
        """Sign-up reads this before an account exists."""
        self.publish_all()
        self.assertEqual(self.client.get('/api/documents/current').status_code, 200)

    def test_it_returns_every_document_in_form_order(self):
        self.publish_all()
        payload = self.body(self.client.get('/api/documents/current'))
        self.assertEqual(
            [entry['document'] for entry in payload['documents']],
            ['club-rules', 'annexures', 'constitution'],
        )

    def test_each_entry_carries_the_version_the_url_and_the_wording(self):
        versions = self.publish_all()
        payload = self.body(self.client.get('/api/documents/current'))
        entry = next(
            item for item in payload['documents'] if item['document'] == 'constitution'
        )
        version = versions['constitution']
        self.assertEqual(entry['version'], version.label)
        self.assertEqual(entry['url'], f'http://testserver{version.url}')
        self.assertEqual(entry['consent_text'], version.consent_text)
        self.assertEqual(entry['sha256'], version.sha256)

    def test_the_url_carries_an_origin(self):
        """The frontend is served from its own origin, not Django's.

        The filesystem backend -- local development, and this suite -- addresses
        a revision as ``/media/...``, which a browser resolves against whatever
        served the page. That is the Next.js dev server, where the file does not
        exist, and the symptom is a 404 on a document sitting safely on disk.
        So the endpoint answers with an absolute URL.
        """
        self.publish_all()
        payload = self.body(self.client.get('/api/documents/current'))
        for entry in payload['documents']:
            self.assertTrue(
                entry['url'].startswith('http://testserver/media/'),
                entry['url'],
            )

    def test_a_url_that_already_has_a_host_is_left_alone(self):
        """The CDN's own address, not Django's, once a container is configured."""
        self.publish_all()
        cdn = 'https://cdn.example.com/documents/constitution/1/doc.pdf'
        with patch.object(
            DocumentVersion, 'url', new_callable=PropertyMock, return_value=cdn
        ):
            payload = self.body(self.client.get('/api/documents/current'))
        for entry in payload['documents']:
            self.assertEqual(entry['url'], cdn)

    def test_each_entry_carries_exactly_the_agreed_fields(self):
        """The contract with the frontend, pinned.

        ``frontend/club/lib/club-documents.ts`` narrows this payload by hand and refuses an entry
        missing ``version``, ``url`` or ``consent_text``. A rename here would leave sign-up
        rendering the fallback screen with nothing to say why, so it fails here instead.
        """
        self.publish_all()
        payload = self.body(self.client.get('/api/documents/current'))
        for entry in payload['documents']:
            self.assertEqual(
                sorted(entry),
                [
                    'consent_text',
                    'document',
                    'effective_from',
                    'requires_reacceptance',
                    'sha256',
                    'title',
                    'url',
                    'version',
                ],
            )

    def test_the_version_crosses_the_wire_as_a_string(self):
        """'2.1' and '2026-08' are both legitimate labels. A number is not enough."""
        self.publish_all()
        payload = self.body(self.client.get('/api/documents/current'))
        for entry in payload['documents']:
            self.assertIsInstance(entry['version'], str)

    def test_a_missing_revision_fails_closed(self):
        self.published(document=self.document('club-rules'), content=b'rules')
        response = self.client.get('/api/documents/current')
        self.assertEqual(response.status_code, 503)
        detail = self.body(response)['detail']
        self.assertIn('annexures', detail)
        self.assertIn('constitution', detail)

    def test_nothing_published_fails_closed(self):
        self.assertEqual(self.client.get('/api/documents/current').status_code, 503)

    def test_the_newest_published_revision_is_the_one_returned(self):
        self.publish_all()
        newer = self.published(
            document=self.document('club-rules'), label='2', content=b'rules v2'
        )
        payload = self.body(self.client.get('/api/documents/current'))
        entry = next(
            item for item in payload['documents'] if item['document'] == 'club-rules'
        )
        self.assertEqual(entry['version'], newer.label)


class OutstandingTests(DocumentApiTestCase):
    def test_a_session_is_required(self):
        self.publish_all()
        self.assertEqual(self.client.get('/api/documents/outstanding').status_code, 401)

    def test_a_member_who_has_agreed_owes_nothing(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        from app.core.documents import services

        services.record_consents(member, list(versions.values()))
        payload = self.body(self.client.get('/api/documents/outstanding'))
        self.assertEqual(payload['documents'], [])

    def test_a_material_revision_puts_a_document_back_on_the_list(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        from app.core.documents import services

        services.record_consents(member, list(versions.values()))
        self.published(
            document=self.document('constitution'),
            label='2',
            content=b'constitution v2',
            requires_reacceptance=True,
        )
        payload = self.body(self.client.get('/api/documents/outstanding'))
        self.assertEqual(
            [entry['document'] for entry in payload['documents']], ['constitution']
        )
        self.assertEqual(payload['documents'][0]['version'], '2')


class AcceptTests(DocumentApiTestCase):
    def submission(self, versions, **overrides):
        return {
            'consents': [
                {
                    'document': slug,
                    'version': overrides.get(slug, version.label),
                }
                for slug, version in versions.items()
            ]
        }

    def post(self, payload):
        return self.client.post(
            '/api/documents/accept',
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_a_session_is_required(self):
        versions = self.publish_all()
        self.assertEqual(self.post(self.submission(versions)).status_code, 401)

    def test_it_records_one_agreement_per_document(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        response = self.post(self.submission(versions))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DocumentConsent.objects.filter(user=member).count(), 3)
        self.assertEqual(self.body(response)['outstanding'], [])

    def test_the_agreement_names_the_revision_not_the_document(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        self.post(self.submission(versions))
        consent = DocumentConsent.objects.get(
            user=member, version__document__slug='constitution'
        )
        self.assertEqual(consent.version, versions['constitution'])
        self.assertEqual(consent.file_sha256, versions['constitution'].sha256)

    def test_a_stale_version_is_refused(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        response = self.post(self.submission(versions, **{'annexures': '0'}))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(DocumentConsent.objects.filter(user=member).count(), 0)

    def test_a_partial_submission_is_refused_whole(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        payload = self.submission(versions)
        payload['consents'] = payload['consents'][:2]
        self.assertEqual(self.post(payload).status_code, 409)
        self.assertEqual(DocumentConsent.objects.filter(user=member).count(), 0)

    def test_submitting_twice_records_once(self):
        versions = self.publish_all()
        member = self.signed_in_member()
        self.post(self.submission(versions))
        self.post(self.submission(versions))
        self.assertEqual(DocumentConsent.objects.filter(user=member).count(), 3)

    def test_it_fails_closed_when_a_document_has_no_revision(self):
        versions = self.publish_all()
        self.signed_in_member()
        retired = self.document('annexures')
        # A fourth document nobody has published: the submission cannot be
        # complete, and the endpoint must say so rather than record two thirds.
        self.document('privacy-notice', title='Privacy Notice', position=9)
        response = self.post(self.submission(versions))
        self.assertEqual(response.status_code, 503)
        self.assertIn('privacy-notice', self.body(response)['detail'])
        self.assertIsNone(retired.retired_at)

"""Tests for the admin over documents, revisions and the agreement ledger.

The admin is the whole publishing interface, so what is guarded here is what it
refuses. A published revision must go read-only and lose its delete button, and
the ledger must not be writable at all -- a consent row staff can type into is
not evidence that anybody ticked anything.

Two of these are belt and braces over the model: ``DocumentVersion.save``
already refuses an edit after publish, and ``delete`` already refuses. The admin
checks matter anyway, because a form that offers a field and then throws on save
is a five-hundred error where it should be a greyed-out input.
"""
from django.contrib.admin.sites import AdminSite
from django.urls import reverse

from app.accounts.models import UserStatus
from app.documents.admin import (
    ClubDocumentAdmin,
    DocumentConsentAdmin,
    DocumentVersionAdmin,
)
from app.documents.models import ClubDocument, DocumentConsent, DocumentVersion

from .support import DocumentsTestCase


class AdminTestCase(DocumentsTestCase):
    def setUp(self):
        self.site = AdminSite()
        self.staff = self.member('staff@example.com')
        self.staff.is_staff = True
        self.staff.is_superuser = True
        self.staff.status = UserStatus.ACTIVE
        self.staff.save()
        self.client.force_login(self.staff)

    def request(self):
        """A request object carrying the signed-in staff user."""
        from django.test import RequestFactory

        request = RequestFactory().get('/admin/')
        request.user = self.staff
        return request


class PublishActionTests(AdminTestCase):
    def test_the_action_publishes_a_draft_and_records_who(self):
        draft = self.draft(content=b'rules')
        response = self.client.post(
            reverse('admin:documents_documentversion_changelist'),
            {'action': 'publish_versions', '_selected_action': [str(draft.pk)]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        draft.refresh_from_db()
        self.assertTrue(draft.is_in_force)
        self.assertEqual(draft.published_by, self.staff)

    def test_a_refused_publish_reports_and_leaves_the_draft_alone(self):
        self.published(label='1', content=b'identical')
        duplicate = self.draft(label='2', content=b'identical')
        response = self.client.post(
            reverse('admin:documents_documentversion_changelist'),
            {'action': 'publish_versions', '_selected_action': [str(duplicate.pk)]},
            follow=True,
        )
        self.assertContains(response, 'byte-identical')
        duplicate.refresh_from_db()
        self.assertFalse(duplicate.is_published)


class ReadOnlyAfterPublishTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.admin = DocumentVersionAdmin(DocumentVersion, self.site)

    def test_a_draft_offers_the_substantive_fields(self):
        draft = self.draft(content=b'rules')
        readonly = self.admin.get_readonly_fields(self.request(), draft)
        for field in ('document', 'label', 'file', 'consent_text'):
            self.assertNotIn(field, readonly)

    def test_a_published_revision_offers_none_of_them(self):
        version = self.published(content=b'rules')
        readonly = self.admin.get_readonly_fields(self.request(), version)
        for field in ('document', 'label', 'file', 'consent_text'):
            self.assertIn(field, readonly)

    def test_the_reacceptance_flag_stays_editable(self):
        version = self.published(content=b'rules')
        readonly = self.admin.get_readonly_fields(self.request(), version)
        self.assertNotIn('requires_reacceptance', readonly)
        self.assertNotIn('change_note', readonly)

    def test_a_draft_may_be_deleted_and_a_published_revision_may_not(self):
        draft = self.draft(label='1', content=b'draft')
        version = self.published(label='2', content=b'published')
        request = self.request()
        self.assertTrue(self.admin.has_delete_permission(request, draft))
        self.assertFalse(self.admin.has_delete_permission(request, version))

    def test_the_change_form_loads_for_both(self):
        """A readonly_fields entry that is not a real field breaks this page."""
        draft = self.draft(label='1', content=b'draft')
        version = self.published(label='2', content=b'published')
        for obj in (draft, version):
            response = self.client.get(
                reverse('admin:documents_documentversion_change', args=[obj.pk])
            )
            self.assertEqual(response.status_code, 200)

    def test_the_changelist_loads(self):
        self.published(content=b'rules')
        response = self.client.get(
            reverse('admin:documents_documentversion_changelist')
        )
        self.assertEqual(response.status_code, 200)


class ClubDocumentAdminTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.admin = ClubDocumentAdmin(ClubDocument, self.site)

    def test_the_slug_is_editable_until_a_revision_exists(self):
        document = self.document('club-rules')
        self.assertNotIn('slug', self.admin.get_readonly_fields(self.request(), document))

    def test_the_slug_freezes_once_a_revision_exists(self):
        """A consent record is only as meaningful as the document it names."""
        version = self.draft(content=b'rules')
        self.assertIn(
            'slug', self.admin.get_readonly_fields(self.request(), version.document)
        )

    def test_the_change_form_loads_with_the_revision_inline(self):
        version = self.published(content=b'rules')
        response = self.client.get(
            reverse('admin:documents_clubdocument_change', args=[version.document.pk])
        )
        self.assertEqual(response.status_code, 200)


class ConsentLedgerAdminTests(AdminTestCase):
    def setUp(self):
        super().setUp()
        self.admin = DocumentConsentAdmin(DocumentConsent, self.site)
        version = self.published(content=b'rules')
        self.consent = DocumentConsent.objects.create(
            user=self.member('joiner@example.com'),
            version=version,
            file_sha256=version.sha256,
            consent_text_sha256=version.consent_text_sha256,
        )

    def test_the_ledger_is_read_only(self):
        request = self.request()
        self.assertFalse(self.admin.has_add_permission(request))
        self.assertFalse(self.admin.has_change_permission(request, self.consent))
        self.assertFalse(self.admin.has_delete_permission(request, self.consent))

    def test_the_changelist_and_the_detail_page_load(self):
        for url in (
            reverse('admin:documents_documentconsent_changelist'),
            reverse('admin:documents_documentconsent_change', args=[self.consent.pk]),
        ):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_the_wording_agreed_to_is_shown(self):
        self.assertEqual(
            self.admin.agreed_wording(self.consent), self.consent.version.consent_text
        )

    def test_wording_that_no_longer_matches_is_flagged(self):
        """Impossible while the immutability guard holds, which is why it is surfaced."""
        self.consent.consent_text_sha256 = '0' * 64
        self.assertIn('CHANGED SINCE AGREEMENT', self.admin.agreed_wording(self.consent))

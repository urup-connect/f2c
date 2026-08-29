"""Shared scaffolding for the club-document tests.

Every test here writes a real file, because the digests are the point: a test
that stubs the upload would pass with the hashing broken.
"""
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from app.core.documents.models import Document, DocumentVersion
from app.core.storefronts.models import Storefront
from f2c.testing import make_account

User = get_user_model()

# Not a valid PDF, and it does not need to be: nothing in this app parses one.
PDF_BYTES = b'%PDF-1.7\nclub rules, first revision\n%%EOF\n'


def upload(name='rules.pdf', content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type='application/pdf')


class DocumentsTestCase(TestCase):
    """Files land in a temporary directory that is removed afterwards.

    STORAGES is pinned to the filesystem so the suite behaves the same whether
    or not the developer running it has Azure credentials in their .env.
    """

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='cc-documents-tests-')
        cls._overrides = override_settings(
            MEDIA_ROOT=cls._media,
            MEDIA_URL='media/',
            STORAGES={
                'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {
                    'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'
                },
                'documents': {
                    'BACKEND': 'django.core.files.storage.FileSystemStorage'
                },
            },
        )
        cls._overrides.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._overrides.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def document(self, slug='club-rules', **extra):
        """The seeded document, or a new one. Migration 0002 seeds three."""
        defaults = {'title': slug.replace('-', ' ').title(), 'position': 0}
        defaults.update(extra)
        document, _ = Document.objects.get_or_create(
            storefront=Storefront.CLUB, slug=slug, defaults=defaults
        )
        return document

    def draft(self, document=None, label='1', content=PDF_BYTES, **extra):
        version = DocumentVersion(
            document=document or self.document(),
            label=label,
            consent_text=extra.pop('consent_text', 'I have read and agree to the Club Rules'),
            **extra,
        )
        version.file = upload(f'rules_{label}.pdf', content)
        version.save()
        return version

    def published(self, *args, by=None, **kwargs):
        return self.draft(*args, **kwargs).publish(by=by)

    def member(self, email='member@example.com'):
        # A bare account. A document agreement is a person's, so nothing here
        # needs a membership — and giving it one would hide an endpoint that
        # wrongly required one.
        return make_account(email)

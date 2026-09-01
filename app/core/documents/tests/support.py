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

    **The override goes on unittest's class-cleanup stack, and that is not a
    style choice.** It used to be enabled here and disabled in a matching
    ``tearDownClass``, which looks correct and is not, because
    ``@override_settings`` applied to a *subclass* -- ``PaymentsTestCase`` is the
    one that exists -- is entered by Django through ``enterClassContext`` and so
    is unwound after ``tearDownClass`` has already run. The two mechanisms then
    disable out of order: this override went first while the subclass's was
    still open, and when that one exited it restored the snapshot it had taken
    *while this override was active*. The temporary MEDIA_ROOT and this STORAGES
    dict came back from the dead and stayed for the rest of the process.

    Nothing failed while both storages backends were the same object, which is
    why it sat here unnoticed. It surfaced the day ``STORAGES['staticfiles']``
    became WhiteNoise's manifest backend: whether an admin page rendered
    depended on whether the documents tests had run yet. Registering here puts
    both overrides on one stack, which unwinds last-in-first-out.
    ``f2c.test_runner`` fails the run if anything leaks again.
    """

    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix='cc-documents-tests-')
        # Registered before the override, so it is torn down after it: the
        # settings are restored first and the directory removed second.
        cls.addClassCleanup(shutil.rmtree, cls._media, ignore_errors=True)
        cls.enterClassContext(override_settings(
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
        ))
        super().setUpClass()

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

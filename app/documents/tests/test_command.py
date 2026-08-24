"""Tests for ``manage.py publish_club_document``.

This is the path the initial load takes, so it is worth proving end to end: a file on disk goes in,
and what comes out is a published revision with a digest computed from the real bytes and an address
the CDN would serve. A command that uploaded but left the digest blank would look like it worked.
"""
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import CommandError, call_command

from app.documents.models import DocumentVersion

from .support import PDF_BYTES, DocumentsTestCase


class PublishCommandTests(DocumentsTestCase):
    def setUp(self):
        self._files = TemporaryDirectory(prefix='cc-documents-command-')
        self.addCleanup(self._files.cleanup)
        self.pdf = Path(self._files.name) / 'F2C_Club_Constitution_1.pdf'
        self.pdf.write_bytes(PDF_BYTES)

    def run_command(self, *args, **options):
        out = StringIO()
        call_command('publish_club_document', *args, stdout=out, **options)
        return out.getvalue()

    def publish(self, **options):
        settings = {
            'consent_text': 'I have read and agree to the Constitution',
            **options,
        }
        return self.run_command('constitution', '1', str(self.pdf), **settings)

    def test_it_uploads_digests_and_publishes(self):
        output = self.publish()
        version = DocumentVersion.objects.get()

        self.assertTrue(version.is_in_force)
        self.assertEqual(version.byte_size, len(PDF_BYTES))
        self.assertEqual(len(version.sha256), 64)
        self.assertIn(version.sha256, output)

    def test_the_stored_file_is_the_file_that_went_in(self):
        self.publish()
        with DocumentVersion.objects.get().file.open('rb') as handle:
            self.assertEqual(handle.read(), PDF_BYTES)

    def test_the_address_carries_the_document_and_the_version(self):
        self.publish()
        self.assertIn('/constitution/1/', DocumentVersion.objects.get().file.name)

    def test_draft_leaves_it_unpublished(self):
        self.publish(draft=True)
        self.assertFalse(DocumentVersion.objects.get().is_published)

    def test_material_sets_the_reacceptance_flag(self):
        self.publish(material=True)
        self.assertTrue(DocumentVersion.objects.get().requires_reacceptance)

    def test_an_unknown_document_is_refused_and_names_the_known_ones(self):
        with self.assertRaises(CommandError) as caught:
            self.run_command(
                'club-newsletter', '1', str(self.pdf), consent_text='I agree'
            )
        self.assertIn('constitution', str(caught.exception))

    def test_a_missing_file_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command(
                'constitution', '1', str(self.pdf.parent / 'absent.pdf'),
                consent_text='I agree',
            )

    def test_a_label_that_would_not_be_safe_in_a_path_is_refused_before_uploading(self):
        with self.assertRaises(CommandError):
            self.run_command('constitution', '../2', str(self.pdf), consent_text='I agree')
        self.assertFalse(DocumentVersion.objects.exists())

    def test_republishing_identical_bytes_is_refused(self):
        """The command reports what the model refuses, rather than a traceback."""
        self.publish()
        with self.assertRaises(CommandError) as caught:
            self.run_command(
                'constitution', '2', str(self.pdf),
                consent_text='I have read and agree to the Constitution',
            )
        self.assertIn('byte-identical', str(caught.exception))

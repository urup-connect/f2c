"""Tests for the revision models.

Three things here are worth testing precisely because they fail quietly. A
digest computed from a consumed file handle is a digest of nothing, and the
upload still succeeds. An immutability guard that does not actually fire lets a
published document be edited under agreements that point at it. And a
byte-identical re-publish asks every member to re-read a document that did not
change, which looks like diligence and is the opposite.
"""
import hashlib

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from app.documents.models import ClubDocument, DocumentConsent, DocumentVersion, digest_text

from .support import PDF_BYTES, DocumentsTestCase, upload


class SeedTests(DocumentsTestCase):
    def test_migration_registers_the_three_documents(self):
        self.assertEqual(
            list(ClubDocument.objects.values_list('slug', flat=True)),
            ['club-rules', 'annexures', 'constitution'],
        )

    def test_no_revision_is_seeded(self):
        """Sign-up fails closed until a real file is published. See migration 0002."""
        self.assertFalse(DocumentVersion.objects.exists())


class DigestTests(DocumentsTestCase):
    def test_file_digest_matches_the_uploaded_bytes(self):
        version = self.draft()
        self.assertEqual(version.sha256, hashlib.sha256(PDF_BYTES).hexdigest())
        self.assertEqual(version.byte_size, len(PDF_BYTES))

    def test_the_file_is_written_whole_after_being_hashed(self):
        """The rewind in digest_file(), which is invisible when it is missing."""
        version = self.draft()
        with version.file.open('rb') as handle:
            self.assertEqual(handle.read(), PDF_BYTES)

    def test_consent_wording_is_digested(self):
        version = self.draft(consent_text='I have read and agree to the Club Rules')
        self.assertEqual(
            version.consent_text_sha256,
            digest_text('I have read and agree to the Club Rules'),
        )

    def test_different_files_digest_differently(self):
        first = self.draft(label='1', content=b'one')
        second = self.draft(label='2', content=b'two')
        self.assertNotEqual(first.sha256, second.sha256)


class VersionRulesTests(DocumentsTestCase):
    def test_label_is_unique_per_document(self):
        self.draft(label='1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.draft(label='1')

    def test_the_same_label_is_allowed_on_a_different_document(self):
        self.draft(document=self.document('club-rules'), label='1')
        other = self.draft(document=self.document('annexures'), label='1')
        self.assertEqual(other.label, '1')

    def test_a_label_that_would_not_be_safe_in_a_path_is_refused(self):
        version = DocumentVersion(
            document=self.document(), label='../2', consent_text='agree'
        )
        version.file = upload()
        with self.assertRaises(ValidationError):
            version.full_clean(exclude=['sha256', 'consent_text_sha256'])

    def test_the_version_is_in_the_stored_key(self):
        """What makes a revision a new object rather than an overwrite."""
        version = self.draft(label='3')
        self.assertIn('/club-rules/3/', version.file.name)


class PublishTests(DocumentsTestCase):
    def test_a_draft_is_not_in_force(self):
        version = self.draft()
        self.assertFalse(version.is_published)
        self.assertIsNone(version.document.current_version)

    def test_publishing_puts_it_in_force(self):
        version = self.published()
        self.assertTrue(version.is_in_force)
        self.assertEqual(version.document.current_version, version)

    def test_publishing_records_who_did_it(self):
        staff = self.member('staff@example.com')
        version = self.published(by=staff)
        self.assertEqual(version.published_by, staff)

    def test_a_newer_revision_supersedes_the_older_one(self):
        old = self.published(label='1', content=b'first')
        new = self.published(label='2', content=b'second')
        self.assertEqual(old.document.current_version, new)
        # The old row is still there, which is the whole point.
        self.assertTrue(DocumentVersion.objects.filter(pk=old.pk).exists())

    def test_publishing_twice_is_refused(self):
        version = self.published()
        with self.assertRaises(ValidationError):
            version.publish()

    def test_a_byte_identical_revision_is_refused(self):
        self.published(label='1', content=PDF_BYTES)
        duplicate = self.draft(label='2', content=PDF_BYTES)
        with self.assertRaises(ValidationError) as caught:
            duplicate.publish()
        self.assertIn('byte-identical', ' '.join(caught.exception.messages))

    def test_a_revision_with_no_consent_wording_is_refused(self):
        version = self.draft(consent_text='   ')
        with self.assertRaises(ValidationError):
            version.publish()


class ImmutabilityTests(DocumentsTestCase):
    def test_the_consent_wording_cannot_be_edited_after_publishing(self):
        self.published()
        version = DocumentVersion.objects.get()
        version.consent_text = 'I agree to something else'
        with self.assertRaises(ValidationError) as caught:
            version.save()
        self.assertIn('consent_text', ' '.join(caught.exception.messages))

    def test_the_file_cannot_be_replaced_after_publishing(self):
        self.published()
        version = DocumentVersion.objects.get()
        version.file = upload('replacement.pdf', b'different rules entirely')
        with self.assertRaises(ValidationError):
            version.save()

    def test_the_label_cannot_be_changed_after_publishing(self):
        self.published(label='1')
        version = DocumentVersion.objects.get()
        version.label = '99'
        with self.assertRaises(ValidationError):
            version.save()

    def test_a_draft_can_still_be_edited(self):
        self.draft()
        version = DocumentVersion.objects.get()
        version.consent_text = 'Reworded before anyone saw it'
        version.save()
        self.assertEqual(
            DocumentVersion.objects.get().consent_text,
            'Reworded before anyone saw it',
        )

    def test_the_reacceptance_flag_stays_editable_after_publishing(self):
        """Deliberate: whether a change was material is sometimes decided late."""
        self.published()
        version = DocumentVersion.objects.get()
        version.requires_reacceptance = True
        version.change_note = 'Committee confirmed this is material.'
        version.save()
        self.assertTrue(DocumentVersion.objects.get().requires_reacceptance)

    def test_a_published_revision_cannot_be_deleted(self):
        version = self.published()
        with self.assertRaises(ValidationError):
            version.delete()
        self.assertTrue(DocumentVersion.objects.filter(pk=version.pk).exists())

    def test_a_draft_can_be_deleted(self):
        self.draft().delete()
        self.assertFalse(DocumentVersion.objects.exists())

    def test_the_database_refuses_to_drop_a_revision_someone_agreed_to(self):
        """The backstop for a queryset delete, which bypasses Model.delete."""
        version = self.published()
        DocumentConsent.objects.create(
            user=self.member(),
            version=version,
            file_sha256=version.sha256,
            consent_text_sha256=version.consent_text_sha256,
        )
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            DocumentVersion.objects.filter(pk=version.pk).delete()


class ConsentTests(DocumentsTestCase):
    def test_a_member_agrees_to_a_revision_once(self):
        version = self.published()
        member = self.member()
        fields = {
            'file_sha256': version.sha256,
            'consent_text_sha256': version.consent_text_sha256,
        }
        DocumentConsent.objects.create(user=member, version=version, **fields)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DocumentConsent.objects.create(user=member, version=version, **fields)

    def test_an_intact_file_is_reported_as_intact(self):
        version = self.published()
        consent = DocumentConsent.objects.create(
            user=self.member(),
            version=version,
            file_sha256=version.sha256,
            consent_text_sha256=version.consent_text_sha256,
        )
        self.assertTrue(consent.matches_current_file)

    def test_a_digest_that_no_longer_matches_is_reported(self):
        version = self.published()
        consent = DocumentConsent.objects.create(
            user=self.member(),
            version=version,
            file_sha256='0' * 64,
            consent_text_sha256=version.consent_text_sha256,
        )
        self.assertFalse(consent.matches_current_file)

    def test_erasing_a_member_keeps_their_agreements(self):
        """See DocumentConsent's docstring: the fact survives the personal data."""
        version = self.published()
        member = self.member()
        DocumentConsent.objects.create(
            user=member,
            version=version,
            file_sha256=version.sha256,
            consent_text_sha256=version.consent_text_sha256,
        )
        member.soft_delete()
        self.assertEqual(DocumentConsent.objects.filter(user=member).count(), 1)
        self.assertIsNone(member.email)

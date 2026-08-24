"""Tests for reading the live revisions and writing agreements against them.

The two behaviours worth guarding are both refusals. ``current_revisions``
refusing a partial list is what stops a form collecting an agreement that is
incomplete in a way nobody can see. ``resolve_submitted`` refusing a stale
version is what stops a tick against v1's text being filed as agreement to v2.
"""
from django.core.exceptions import ValidationError

from app.documents import services
from app.documents.models import DocumentConsent

from .support import DocumentsTestCase


class CurrentRevisionsTests(DocumentsTestCase):
    def publish_all(self):
        return [
            self.published(
                document=self.document(slug), label='1', content=f'{slug} v1'.encode()
            )
            for slug in ('club-rules', 'annexures', 'constitution')
        ]

    def test_every_document_at_its_live_revision_in_form_order(self):
        self.publish_all()
        revisions = services.current_revisions()
        self.assertEqual(
            [revision.document.slug for revision in revisions],
            ['club-rules', 'annexures', 'constitution'],
        )

    def test_a_missing_revision_refuses_the_whole_list(self):
        self.published(document=self.document('club-rules'), content=b'rules')
        with self.assertRaises(services.DocumentsNotReady) as caught:
            services.current_revisions()
        self.assertEqual(
            {document.slug for document in caught.exception.documents},
            {'annexures', 'constitution'},
        )

    def test_a_draft_does_not_count_as_published(self):
        self.publish_all()
        self.draft(document=self.document('club-rules'), label='2', content=b'draft')
        revisions = {r.document.slug: r for r in services.current_revisions()}
        self.assertEqual(revisions['club-rules'].label, '1')

    def test_a_retired_document_drops_out_of_signup(self):
        self.publish_all()
        retired = self.document('annexures')
        retired.required_at_signup = False
        retired.save()
        self.assertEqual(
            [revision.document.slug for revision in services.current_revisions()],
            ['club-rules', 'constitution'],
        )


class OutstandingTests(DocumentsTestCase):
    def setUp(self):
        self.rules = self.document('club-rules')
        self.member_account = self.member()
        # One document in scope, so the flag behaviour is what is being tested.
        for slug in ('annexures', 'constitution'):
            document = self.document(slug)
            document.required_at_signup = False
            document.save()

    def test_a_new_member_owes_the_live_revision(self):
        version = self.published(document=self.rules, content=b'v1')
        self.assertEqual(services.outstanding_for(self.member_account), [version])

    def test_a_member_who_agreed_owes_nothing(self):
        version = self.published(document=self.rules, content=b'v1')
        services.record_consents(self.member_account, [version])
        self.assertEqual(services.outstanding_for(self.member_account), [])

    def test_a_typo_fix_does_not_ask_again(self):
        first = self.published(document=self.rules, label='1', content=b'v1')
        services.record_consents(self.member_account, [first])
        self.published(
            document=self.rules, label='2', content=b'v2', requires_reacceptance=False
        )
        self.assertEqual(services.outstanding_for(self.member_account), [])

    def test_a_material_change_asks_again(self):
        first = self.published(document=self.rules, label='1', content=b'v1')
        services.record_consents(self.member_account, [first])
        second = self.published(
            document=self.rules, label='2', content=b'v2', requires_reacceptance=True
        )
        self.assertEqual(services.outstanding_for(self.member_account), [second])

    def test_agreeing_to_the_material_change_clears_it(self):
        first = self.published(document=self.rules, label='1', content=b'v1')
        services.record_consents(self.member_account, [first])
        second = self.published(
            document=self.rules, label='2', content=b'v2', requires_reacceptance=True
        )
        services.record_consents(self.member_account, [second])
        self.assertEqual(services.outstanding_for(self.member_account), [])
        # Both agreements are on file. The first is not rewritten by the second.
        self.assertEqual(
            DocumentConsent.objects.filter(user=self.member_account).count(), 2
        )


class ResolveSubmittedTests(DocumentsTestCase):
    def setUp(self):
        self.versions = {
            slug: self.published(
                document=self.document(slug), label='1', content=f'{slug}'.encode()
            )
            for slug in ('club-rules', 'annexures', 'constitution')
        }

    def submission(self, **overrides):
        entries = [
            {'document': slug, 'version': version.label}
            for slug, version in self.versions.items()
        ]
        for entry in entries:
            if entry['document'] in overrides:
                entry['version'] = overrides[entry['document']]
        return entries

    def test_a_matching_submission_resolves_to_the_live_revisions(self):
        resolved = services.resolve_submitted(self.submission())
        self.assertEqual(
            [revision.document.slug for revision in resolved],
            ['club-rules', 'annexures', 'constitution'],
        )

    def test_a_stale_version_is_refused_rather_than_upgraded(self):
        """The member ticked a box beside text that has since been replaced."""
        with self.assertRaises(ValidationError) as caught:
            services.resolve_submitted(self.submission(**{'club-rules': '0'}))
        self.assertIn('moved to version', ' '.join(caught.exception.messages))

    def test_a_missing_document_is_refused(self):
        submission = [
            entry for entry in self.submission() if entry['document'] != 'annexures'
        ]
        with self.assertRaises(ValidationError) as caught:
            services.resolve_submitted(submission)
        self.assertIn('annexures', ' '.join(caught.exception.messages))

    def test_an_unknown_document_is_refused(self):
        submission = self.submission() + [{'document': 'invented', 'version': '1'}]
        with self.assertRaises(ValidationError):
            services.resolve_submitted(submission)

    def test_the_same_document_twice_is_refused(self):
        submission = self.submission() + [{'document': 'annexures', 'version': '1'}]
        with self.assertRaises(ValidationError):
            services.resolve_submitted(submission)


class RecordConsentsTests(DocumentsTestCase):
    def test_the_digests_are_copied_from_the_revision(self):
        version = self.published(content=b'rules')
        member = self.member()
        (consent,) = services.record_consents(member, [version])
        self.assertEqual(consent.file_sha256, version.sha256)
        self.assertEqual(consent.consent_text_sha256, version.consent_text_sha256)

    def test_recording_twice_keeps_the_original_timestamp(self):
        version = self.published(content=b'rules')
        member = self.member()
        (first,) = services.record_consents(member, [version])
        self.assertEqual(services.record_consents(member, [version]), [])
        self.assertEqual(
            DocumentConsent.objects.get(user=member, version=version).accepted_at,
            first.accepted_at,
        )

    def test_the_source_is_recorded(self):
        version = self.published(content=b'rules')
        (consent,) = services.record_consents(
            self.member(), [version], source=DocumentConsent.Source.REACCEPTANCE
        )
        self.assertEqual(consent.source, DocumentConsent.Source.REACCEPTANCE)

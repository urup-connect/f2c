"""Reading the current revisions, and writing agreements against them.

Everything here is a query or a write over the three models, kept out of
``models.py`` because it spans them. Two rules run through it:

**Fail closed.** ``current_revisions`` is asked for the revisions a joining
member must agree to, and it refuses rather than returning a short list. A
sign-up form that renders four documents when the club has five is a form that
collects an incomplete agreement, and the incompleteness is invisible.

**Nothing is inferred from what the browser sends.** A submission names a
document and a version; both are checked against what is actually in force
before a row is written. The version a member saw and the version in force can
differ, because a revision can be published between the page rendering and the
member submitting.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ClubDocument, DocumentConsent, DocumentVersion


class DocumentsNotReady(Exception):
    """A required document has no revision in force.

    Raised rather than returned, because every caller's correct response is the
    same: refuse. Carries the documents at fault so the message can name them.
    """

    def __init__(self, documents):
        self.documents = list(documents)
        names = ', '.join(document.slug for document in self.documents)
        super().__init__(
            f'No revision is in force for: {names}. Publish one in the admin '
            'before members can agree to it.'
        )


def _latest_by_document(documents):
    """The in-force revision of each of ``documents``, keyed by document id."""
    versions = (
        DocumentVersion.objects.published()
        .filter(document__in=documents)
        .select_related('document')
    )
    latest = {}
    # published() is newest first, so the first row seen for a document wins.
    for version in versions:
        latest.setdefault(version.document_id, version)
    return latest


def current_revisions(*, required_only=True):
    """The revision in force for every document, in form order.

    :raises DocumentsNotReady: if any document in scope has none.
    """
    documents = list(
        ClubDocument.objects.filter(required_at_signup=True)
        if required_only
        else ClubDocument.objects.all()
    )
    latest = _latest_by_document(documents)
    missing = [document for document in documents if document.id not in latest]
    if missing:
        raise DocumentsNotReady(missing)
    return [latest[document.id] for document in documents]


def outstanding_for(user, *, required_only=True):
    """Revisions this member still has to agree to, in form order.

    A document is outstanding when the member has agreed to no revision of it
    at all, or when the revision now in force is marked
    ``requires_reacceptance`` and they have not agreed to that one.

    The flag is what keeps a typo fix from asking every member again while a
    materially changed document does ask them. Consequence worth being explicit
    about: a member who agreed to v1, where v2 was a typo fix and v3 is
    material, is asked for v3 and is never recorded against v2. That is
    correct -- they never read v2 -- and it is why the ledger is keyed on the
    revision rather than on the document.
    """
    documents = list(
        ClubDocument.objects.filter(required_at_signup=True)
        if required_only
        else ClubDocument.objects.all()
    )
    latest = _latest_by_document(documents)
    agreed = set(
        DocumentConsent.objects.filter(user=user).values_list('version_id', flat=True)
    )
    agreed_documents = set(
        DocumentConsent.objects.filter(user=user).values_list(
            'version__document_id', flat=True
        )
    )

    outstanding = []
    for document in documents:
        version = latest.get(document.id)
        if version is None:
            # Nothing to agree to yet. Not this function's problem to refuse:
            # current_revisions() is where a missing revision blocks sign-up.
            continue
        if version.id in agreed:
            continue
        if document.id not in agreed_documents or version.requires_reacceptance:
            outstanding.append(version)
    return outstanding


def resolve_submitted(submitted, *, required_only=True):
    """Match ``{'document': slug, 'version': label}`` entries to live revisions.

    Every required document must appear exactly once, and each named version
    must be the one actually in force. A stale version is refused rather than
    silently upgraded to the current one: the member ticked a box beside the
    text they were shown, and recording that tick against a revision published
    since would attribute an agreement to a document they never saw.

    :raises DocumentsNotReady: if a required document has no revision in force.
    :raises ValidationError: if the submission does not match what is in force.
    """
    revisions = current_revisions(required_only=required_only)
    expected = {revision.document.slug: revision for revision in revisions}

    seen = {}
    for entry in submitted:
        slug = (entry.get('document') or '').strip()
        label = (entry.get('version') or '').strip()
        if slug not in expected:
            raise ValidationError(f'"{slug}" is not a document members agree to.')
        if slug in seen:
            raise ValidationError(f'"{slug}" was submitted more than once.')
        if label != expected[slug].label:
            raise ValidationError(
                f'The {expected[slug].document.title} has moved to version '
                f'{expected[slug].label} since this form was opened. Please read '
                'it again and agree to the current version.'
            )
        seen[slug] = expected[slug]

    absent = [slug for slug in expected if slug not in seen]
    if absent:
        raise ValidationError(
            'No agreement was submitted for: {}.'.format(', '.join(sorted(absent)))
        )

    return [expected[revision.document.slug] for revision in revisions]


@transaction.atomic
def record_consents(user, versions, *, source=DocumentConsent.Source.SIGNUP):
    """Write one agreement per revision, and return the rows written.

    Idempotent per revision: a member who already agreed to a revision keeps
    the original row and its original timestamp. Re-submitting must not restamp
    an agreement to a later moment than the one it was given at.

    The digests are copied from the revision here, at the moment of the write,
    rather than read back later. That copy is the evidence.
    """
    written = []
    for version in versions:
        consent, created = DocumentConsent.objects.get_or_create(
            user=user,
            version=version,
            defaults={
                'file_sha256': version.sha256,
                'consent_text_sha256': version.consent_text_sha256,
                'source': source,
            },
        )
        if created:
            written.append(consent)
    return written

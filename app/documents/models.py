"""Club documents, their revisions, and who agreed to which revision.

Three models, and the split between them is the whole feature.

``ClubDocument`` is a document's identity -- "the constitution" -- and it does
not carry a file. ``DocumentVersion`` is one revision of it: a file, a version
label, and the exact wording of the checkbox shown beside it.
``DocumentConsent`` is one member's agreement to one revision.

A published revision is immutable, and that immutability *is* the audit trail.
Updating a document means publishing a new ``DocumentVersion``; it never means
editing an existing one. So "which text did this member agree to?" always has
an answer, and it is the answer that was true when they ticked the box rather
than whatever the document happens to say today. Looking the version up later
would answer the second question while appearing to answer the first.

Two digests are copied onto every consent row rather than left to be joined
from the revision. A join tells you what the revision says now; the copy tells
you what the member actually agreed to, and a disagreement between the two is
itself the signal that something was tampered with.
"""
import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone

from .storage import document_storage, document_upload_to

# Version labels appear in a URL path (see ``document_upload_to``), so the
# character set is constrained rather than escaped. Dots and dashes are allowed
# because '2.1' and '2026-08' are both reasonable ways to number a revision;
# slashes, spaces and everything else are not.
LABEL_VALIDATOR = RegexValidator(
    regex=r'^[A-Za-z0-9][A-Za-z0-9._-]*$',
    message=(
        'A version label must start with a letter or digit and may contain only '
        'letters, digits, dots, dashes and underscores.'
    ),
)


def digest_text(value):
    """SHA-256 of the consent wording, over its exact bytes."""
    return hashlib.sha256((value or '').encode('utf-8')).hexdigest()


def digest_file(field_file):
    """SHA-256 and byte length of an uploaded file, read in chunks.

    Reads through ``chunks()`` so a large PDF is never held in memory whole, and
    rewinds afterwards: this runs before Django writes the file to storage, and
    a consumed file handle would be written as zero bytes.
    """
    hasher = hashlib.sha256()
    size = 0
    for chunk in field_file.chunks():
        hasher.update(chunk)
        size += len(chunk)
    field_file.seek(0)
    return hasher.hexdigest(), size


class ClubDocument(models.Model):
    """A document a member is asked to agree to, independent of its wording.

    The row is the identity and nothing else: no file, no version. Both live on
    ``DocumentVersion``, which is what makes a revision an addition rather than
    an edit.
    """

    # The identifier the frontend keys its checkboxes on: 'club-rules',
    # 'annexures', 'constitution'. Stable forever -- a consent record is only
    # as meaningful as the document it names, so renaming one would rewrite
    # history. Add a document rather than repurpose one.
    slug = models.SlugField(
        max_length=60,
        unique=True,
        help_text=(
            'Stable identifier used by the sign-up form, e.g. "constitution". '
            'Never change this on a document members have already agreed to.'
        ),
    )
    title = models.CharField(
        max_length=120, help_text='What a member sees, e.g. "Constitution".'
    )
    # Display order on the form. Named `position` rather than `ordering` so it
    # cannot be confused with Meta.ordering below.
    position = models.PositiveSmallIntegerField(
        default=0, help_text='Low numbers first on the sign-up form.'
    )
    # False takes a document out of sign-up without deleting it or its consent
    # history -- which is the only safe way to retire one.
    required_at_signup = models.BooleanField(
        default=True,
        help_text=(
            'Whether joining members must agree to this document. Untick to '
            'retire a document without touching the agreements already given.'
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('position', 'slug')
        verbose_name = 'club document'

    def __str__(self):
        return self.title

    @property
    def current_version(self):
        """The revision in force now, or ``None`` if nothing is published."""
        return self.versions.published().first()


class DocumentVersionQuerySet(models.QuerySet):
    def published(self):
        """Revisions in force, newest first.

        A future ``effective_from`` is not yet in force, which is what lets a
        revision be prepared and dated ahead of a committee decision.
        """
        return self.filter(
            effective_from__isnull=False, effective_from__lte=timezone.now()
        ).order_by('-effective_from', '-pk')

    def drafts(self):
        return self.filter(effective_from__isnull=True)


class DocumentVersion(models.Model):
    """One revision of one document: the file, its label, and its wording.

    Immutable once published. ``save`` refuses a change to any field in
    ``IMMUTABLE_AFTER_PUBLISH``, and ``delete`` refuses outright -- a published
    revision is what a consent record points at, so removing or altering one
    destroys the evidence of an agreement.

    Two fields stay editable on purpose, and both are administrative rather
    than substantive: ``change_note``, which is staff-facing, and
    ``requires_reacceptance``, because whether a change was material enough to
    ask every existing member again is a judgement sometimes made the morning
    after the publish.
    """

    IMMUTABLE_AFTER_PUBLISH = (
        'document',
        'label',
        'file',
        'sha256',
        'consent_text',
        'consent_text_sha256',
        'effective_from',
    )

    # PROTECT, not CASCADE: deleting a document must not silently take its
    # revisions -- and therefore the agreements pointing at them -- with it.
    document = models.ForeignKey(
        ClubDocument, on_delete=models.PROTECT, related_name='versions'
    )
    label = models.CharField(
        max_length=32,
        validators=[LABEL_VALIDATOR],
        help_text=(
            'This revision\'s version, e.g. "2" or "2026-08". Unique per document.'
        ),
    )
    # max_length raised from the 100-character default: the key carries the
    # document slug and the version label as well as the file name.
    file = models.FileField(
        storage=document_storage,
        upload_to=document_upload_to,
        max_length=255,
        help_text='The PDF as members will read it. Uploaded straight to the CDN.',
    )
    # Computed on save from the uploaded bytes, and copied onto every consent
    # row. Never entered by hand.
    sha256 = models.CharField(max_length=64, editable=False, db_index=True)
    byte_size = models.PositiveIntegerField(default=0, editable=False)

    # The sentence shown beside the checkbox, e.g. "I have read and agree to
    # the Constitution". Stored per revision because it is part of what was
    # agreed: the file says what the rules are, this says what the member
    # asserted about them.
    consent_text = models.TextField(
        help_text=(
            'The exact sentence a member ticks, e.g. "I have read and agree to '
            'the Constitution". Recorded against every agreement.'
        )
    )
    consent_text_sha256 = models.CharField(max_length=64, editable=False)

    change_note = models.TextField(
        blank=True,
        help_text='Staff-facing: what changed in this revision, and who decided it.',
    )
    requires_reacceptance = models.BooleanField(
        default=False,
        help_text=(
            'Tick when the change is material. Members who agreed to an earlier '
            'revision will be asked again; leave unticked for a typo fix.'
        ),
    )

    # Null means a draft: uploaded, not yet in force, and offered to nobody.
    # Set by publish() and never by hand, which is why it is not editable -- a
    # date typed into a form is a date that can be backdated past an agreement.
    effective_from = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False,
        related_name='published_document_versions',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentVersionQuerySet.as_manager()

    class Meta:
        ordering = ('document__position', '-effective_from', '-pk')
        constraints = [
            models.UniqueConstraint(
                fields=('document', 'label'),
                name='document_version_label_unique_per_document',
                violation_error_message=(
                    'That version label is already used for this document.'
                ),
            ),
        ]
        verbose_name = 'document version'

    def __str__(self):
        return f'{self.document.title} v{self.label}'

    @classmethod
    def from_db(cls, db, field_names, values, **kwargs):
        """Keep the values as loaded, so ``save`` can see what changed.

        Re-reading the row on every write would be a second query for the same
        information.

        ``**kwargs`` passes through whatever Django's loader adds -- 6.1 sends
        ``fetch_mode`` -- so this override does not have to track that
        signature.
        """
        instance = super().from_db(db, field_names, values, **kwargs)
        instance._loaded_values = dict(zip(field_names, values))
        return instance

    @property
    def is_published(self):
        return self.effective_from is not None

    @property
    def is_in_force(self):
        return self.is_published and self.effective_from <= timezone.now()

    @property
    def url(self):
        """The public address of this revision's file, or ``''`` if none."""
        return self.file.url if self.file else ''

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _file_needs_digesting(self):
        """True for a file whose bytes have not been hashed yet.

        ``_committed`` is False exactly while an uploaded file is waiting to be
        written to storage, which is the one moment its bytes are readable
        without fetching them back from the CDN.
        """
        if not self.file:
            return False
        return not self.sha256 or not getattr(self.file, '_committed', True)

    def _refuse_changes_after_publish(self):
        loaded = getattr(self, '_loaded_values', None)
        if not loaded or loaded.get('effective_from') is None:
            return
        changed = []
        for field in self.IMMUTABLE_AFTER_PUBLISH:
            attname = self._meta.get_field(field).attname
            if attname not in loaded:
                # A deferred field was never loaded, so it cannot have changed.
                continue
            was = loaded[attname]
            now = getattr(self, attname)
            if field == 'file':
                # The instance holds a FieldFile here; the loaded values hold
                # the stored key as a plain string.
                now = self.file.name if self.file else ''
                was = was or ''
            if now != was:
                changed.append(field)
        if changed:
            raise ValidationError(
                'A published revision cannot be changed ({}). Publish a new '
                'version instead -- that is what keeps every past agreement '
                'readable.'.format(', '.join(changed))
            )

    def save(self, *args, **kwargs):
        self.label = (self.label or '').strip()
        self.consent_text_sha256 = digest_text(self.consent_text)
        if self._file_needs_digesting():
            self.sha256, self.byte_size = digest_file(self.file)
        self._refuse_changes_after_publish()
        super().save(*args, **kwargs)
        # Rebase the comparison, so a second save in the same request measures
        # against what is now stored rather than against what was loaded.
        self._loaded_values = {
            field.attname: getattr(self, field.attname)
            for field in self._meta.concrete_fields
        }
        self._loaded_values['file'] = self.file.name if self.file else ''

    def delete(self, *args, **kwargs):
        if self.is_published:
            raise ValidationError(
                'A published revision cannot be deleted. Retire the document or '
                'publish a replacement; the agreements already given point at '
                'this row.'
            )
        return super().delete(*args, **kwargs)

    @transaction.atomic
    def publish(self, by=None, at=None):
        """Put this revision in force. The one write that cannot be undone.

        Refuses a byte-identical re-upload of a revision already published.
        That is nearly always the same PDF uploaded twice, and the cost of
        accepting it is asking every member to agree again to a document that
        did not change.
        """
        if self.is_published:
            raise ValidationError(f'{self} is already published.')
        if not self.file:
            raise ValidationError('A revision needs a file before it can be published.')
        if not (self.consent_text or '').strip():
            raise ValidationError(
                'A revision needs its consent wording before it can be published: '
                'the sentence the member ticks is part of what they agree to.'
            )
        identical = (
            type(self)
            .objects.published()
            .filter(document=self.document, sha256=self.sha256)
            .exclude(pk=self.pk)
            .first()
        )
        if identical:
            raise ValidationError(
                f'This file is byte-identical to {identical}, which is already '
                'published. Publishing it again would ask members to agree to a '
                'document that has not changed.'
            )
        self.effective_from = at or timezone.now()
        self.published_by = by
        self.save(update_fields=['effective_from', 'published_by', 'updated_at'])
        return self


class DocumentConsentQuerySet(models.QuerySet):
    def for_user(self, user):
        return self.filter(user=user).select_related('version', 'version__document')


class DocumentConsent(models.Model):
    """One member's agreement to one revision of one document.

    Append-only. There is no field for withdrawing an agreement, deliberately:
    withdrawal is not the erasure of a fact that was true, and a member who no
    longer accepts the rules is a membership question rather than a consent row
    to overwrite.

    Survives ``User.soft_delete`` along with the rest of the member's row. The
    erasure clears what identifies the person; what they agreed to is the
    collective's own record of a decision, and the row it hangs off carries no
    name, address or identity number once erased.
    """

    class Source(models.TextChoices):
        SIGNUP = 'signup', 'Sign-up'
        REACCEPTANCE = 'reacceptance', 'Re-acceptance'
        ADMIN = 'admin', 'Recorded by staff'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='document_consents',
    )
    # PROTECT: the revision is the whole meaning of this row. Deleting it would
    # leave an agreement to nothing in particular, so the database refuses.
    version = models.ForeignKey(
        DocumentVersion, on_delete=models.PROTECT, related_name='consents'
    )

    # Stamped by the database at the moment of the write. The frontend sends no
    # time: two clocks for one fact eventually disagree.
    accepted_at = models.DateTimeField(auto_now_add=True)

    # Both copied from the revision as it stood at this moment, rather than
    # joined later. See the module docstring.
    file_sha256 = models.CharField(max_length=64, editable=False)
    consent_text_sha256 = models.CharField(max_length=64, editable=False)

    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.SIGNUP
    )

    objects = DocumentConsentQuerySet.as_manager()

    class Meta:
        ordering = ('-accepted_at',)
        constraints = [
            # One agreement per member per revision. A member who submits the
            # form twice has agreed once.
            models.UniqueConstraint(
                fields=('user', 'version'),
                name='document_consent_once_per_version',
                violation_error_message=(
                    'This member has already agreed to that revision.'
                ),
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'version']),
        ]
        verbose_name = 'document agreement'

    def __str__(self):
        return f'{self.user} agreed to {self.version}'

    @property
    def matches_current_file(self):
        """Whether the revision's file still hashes to what was agreed to.

        False is a tamper signal rather than a normal state: a published
        revision's file cannot legitimately change.
        """
        return bool(self.file_sha256) and self.file_sha256 == self.version.sha256

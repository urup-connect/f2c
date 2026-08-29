"""Documents, their revisions, and who agreed to which revision.

Four models, and the split between the first three is the whole feature.

``Document`` is a document's identity -- "the constitution" -- and it does not
carry a file. ``DocumentVersion`` is one revision of it: a file, a version
label, and the exact wording of the checkbox shown beside it.
``DocumentConsent`` is one person's agreement to one revision, and
``ProducerAgreement`` is an organisation's -- see below on why those are two
tables rather than one.

**Every document belongs to exactly one storefront, and none is shared.** Not
the privacy notice, not the terms. That is a product decision recorded in
``design/verticals.md`` section 6, and it is what lets ``slug`` be unique per
storefront rather than globally: the club and the market may each have a
``terms``.

The machinery below is storefront-agnostic and the content never is. Everything
here -- immutable published revisions, the two digests copied onto every
agreement, ``effective_from`` dating, re-acceptance -- serves a produce market's
returns policy exactly as it serves the club's constitution.

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
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.utils import timezone

from app.core.storefronts.models import Storefront

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


class Audience(models.TextChoices):
    """Who a document concerns, and by consequence who may read it.

    ``PUBLIC`` is a page anybody may read and nobody agrees to: a privacy
    notice, terms of use, a data policy. ``CUSTOMER`` is read by anybody and
    agreed to by somebody joining -- the club's rules are read before an account
    exists, which is why ``/documents/current`` is unauthenticated. ``PRODUCER``
    is a farmer agreement, which is neither public nor read at sign-up.

    **Readability is derived from this rather than carried separately.** Public
    and customer documents are served unauthenticated because sign-up already
    has to read them; producer documents are not. A third flag saying the same
    thing would be a second place for the two to disagree.
    """

    PUBLIC = 'public', 'Anyone'
    CUSTOMER = 'customer', 'Members and customers'
    PRODUCER = 'producer', 'Producers'


class Agreement(models.TextChoices):
    """When agreement to a document is collected, if it ever is.

    ``NONE`` is a published page nobody ticks. ``AT_REGISTRATION`` is the club's
    three, and would be the market's customer terms if it wants any.
    ``AT_ONBOARDING`` is a farmer agreement, signed by the organisation.

    ``AT_CHECKOUT`` is the value to add if market terms turn out to be accepted
    at first order rather than at registration. It is not here because it is not
    decided, and an enum value costs nothing to add later -- see
    ``design/verticals.md`` section 6.
    """

    NONE = 'none', 'No agreement needed'
    AT_REGISTRATION = 'at_registration', 'Agreed when joining'
    AT_ONBOARDING = 'at_onboarding', 'Agreed when a producer is onboarded'


class DocumentQuerySet(models.QuerySet):
    def live(self):
        """Documents that have not been retired."""
        return self.filter(retired_at__isnull=True)

    def for_storefront(self, storefront):
        return self.live().filter(storefront=storefront)

    def readable_without_an_account(self, storefront):
        """What an unauthenticated caller may be shown.

        Public and customer documents. A producer agreement is neither, and the
        endpoint that serves this is the only reason the distinction is drawn.
        """
        return self.for_storefront(storefront).filter(
            audience__in=(Audience.PUBLIC, Audience.CUSTOMER)
        )

    def agreed_at_registration(self, storefront):
        return self.for_storefront(storefront).filter(
            agreement=Agreement.AT_REGISTRATION
        )


class Document(models.Model):
    """A document, independent of its wording.

    The row is the identity and nothing else: no file, no version. Both live on
    ``DocumentVersion``, which is what makes a revision an addition rather than
    an edit.
    """

    # Which storefront this belongs to. A column with a check constraint rather
    # than a foreign key, for the reason `storefronts.models` gives: there are
    # exactly two, every row carries exactly one, and a table would buy a join
    # on every scoped query.
    #
    # Non-null, and there is no "both" value. Nothing is shared between the two
    # storefronts by decision, and a nullable column meaning "both" would let
    # two platform-wide documents share a slug -- nulls are distinct under a
    # unique index on every backend here, which is the exact failure
    # `design/backend.md` section 8.2 exists to prevent.
    storefront = models.CharField(
        max_length=16,
        choices=Storefront.choices,
        db_index=True,
        help_text='Which storefront this document belongs to. Never both.',
    )

    audience = models.CharField(
        max_length=16,
        choices=Audience.choices,
        default=Audience.CUSTOMER,
        db_index=True,
    )
    agreement = models.CharField(
        max_length=20,
        choices=Agreement.choices,
        default=Agreement.AT_REGISTRATION,
        db_index=True,
    )

    # Retiring a document is its own field, and **not** `agreement=NONE`.
    # Setting the enum to "no agreement needed" would take a document out of
    # sign-up and publish it as a public page in the same edit -- two different
    # intentions. This takes it out of everything while keeping it and every
    # agreement given to it.
    retired_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            'Set to retire a document without deleting it or the agreements '
            'already given to it. The only safe way to withdraw one.'
        ),
    )

    # The identifier the frontend keys its checkboxes on: 'club-rules',
    # 'annexures', 'constitution'. Stable forever -- a consent record is only
    # as meaningful as the document it names, so renaming one would rewrite
    # history. Add a document rather than repurpose one.
    #
    # Unique **per storefront**, not globally: the club and the market may each
    # have a `terms` and a `privacy-notice`, and they are different documents.
    # A plain two-column unique index, so none of the portability rules in
    # `design/migrations.md` section 2 apply to it.
    slug = models.SlugField(
        max_length=60,
        help_text=(
            'Stable identifier used by the sign-up form, e.g. "constitution". '
            'Never change this on a document people have already agreed to.'
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ('position', 'slug')
        verbose_name = 'document'
        constraints = [
            models.UniqueConstraint(
                fields=('storefront', 'slug'),
                name='document_slug_unique_per_storefront',
                violation_error_message=(
                    'That storefront already has a document with this slug.'
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(storefront__in=Storefront.values),
                name='document_storefront_is_known',
            ),
            models.CheckConstraint(
                condition=models.Q(audience__in=Audience.values),
                name='document_audience_is_known',
            ),
            models.CheckConstraint(
                condition=models.Q(agreement__in=Agreement.values),
                name='document_agreement_is_known',
            ),
            # A public page nobody ticks, and a document agreed to by producers
            # at onboarding, are coherent. A *public* document that also demands
            # agreement is not: there is nobody to demand it of before an
            # account exists, and the sign-up form would ask a visitor to tick a
            # privacy notice it has no way to record.
            models.CheckConstraint(
                condition=(
                    ~models.Q(audience=Audience.PUBLIC)
                    | models.Q(agreement=Agreement.NONE)
                ),
                name='document_public_needs_no_agreement',
                violation_error_message=(
                    'A public document is read, not agreed to. Give it an '
                    'audience of members or producers if agreement is needed.'
                ),
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_retired(self):
        return self.retired_at is not None

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
        Document, on_delete=models.PROTECT, related_name='versions'
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


class ProducerAgreement(models.Model):
    """One producer organisation's agreement to one revision of one document.

    **Not a ``DocumentConsent``, and the difference is the subject.** A consent
    records *a person agreeing to a text*. A farmer agreement is a contract with
    *the organisation*: one person may run two farms, and a farm's agreement has
    to stand when the person who signed it stops being its contact. Recorded
    against the user alone, the agreement would evaporate with that person's
    association.

    The lighter alternative was a nullable ``producer`` column on
    ``DocumentConsent``. It is fewer lines and it loses the structural
    guarantee: nothing in the database could refuse a producer agreement
    recorded with no producer, because a ``CHECK`` cannot reach across to the
    document's audience to know one was needed. This project's convention is to
    make that kind of rule a fact about the database, so this is a second table
    and the duplicated digest logic is the price.

    Everything else is deliberately identical to ``DocumentConsent``:
    append-only, ``PROTECT`` on the revision, and both digests copied at the
    moment of signing rather than joined later.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    producer = models.ForeignKey(
        'producers.Producer',
        on_delete=models.CASCADE,
        related_name='agreements',
    )
    # PROTECT: the revision is the whole meaning of this row. Deleting it would
    # leave an agreement to nothing in particular, so the database refuses. The
    # same call `DocumentConsent.version` makes.
    version = models.ForeignKey(
        DocumentVersion, on_delete=models.PROTECT, related_name='producer_agreements'
    )

    # Who signed, on the organisation's behalf. SET_NULL rather than PROTECT,
    # and this is the whole reason the table exists: the agreement outlives the
    # person, so their erasure must not be blocked by it and must not delete it.
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='producer_agreements_signed',
        help_text='Who ticked, on the organisation’s behalf. Blank once erased.',
    )

    accepted_at = models.DateTimeField(auto_now_add=True)

    # Copied from the revision as it stood at this moment rather than joined
    # later. A join tells you what the revision says now; the copy tells you
    # what was agreed to, and a disagreement between the two is itself the
    # signal that something was tampered with.
    file_sha256 = models.CharField(max_length=64, editable=False)
    consent_text_sha256 = models.CharField(max_length=64, editable=False)

    class Meta:
        ordering = ('-accepted_at',)
        verbose_name = 'producer agreement'
        constraints = [
            # One agreement per producer per revision. A farm that submits the
            # form twice has agreed once. Keyed on the producer and not on the
            # signatory: two primaries signing the same revision is one
            # agreement by one organisation.
            models.UniqueConstraint(
                fields=('producer', 'version'),
                name='producer_agreement_once_per_version',
                violation_error_message=(
                    'This producer has already agreed to that revision.'
                ),
            ),
        ]
        indexes = [
            models.Index(fields=['producer', 'version']),
        ]

    def __str__(self):
        return f'{self.producer} — {self.version}'

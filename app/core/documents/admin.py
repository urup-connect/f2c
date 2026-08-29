"""Admin views over club documents, their revisions, and the agreement ledger.

Publishing a revision is an explicit action rather than a field on a form, for
the same reason erasing a member is: it is irreversible, and a save button that
does something irreversible as a side effect will eventually be pressed by
accident.

Once a revision is published every substantive field goes read-only and the
delete button is withdrawn. Staff who need to change a document publish a new
revision -- which is the mechanism, not an inconvenience around it. The two
fields that stay editable are ``change_note`` and ``requires_reacceptance``,
and ``DocumentVersion`` says why.

The agreement ledger is read-only throughout. A consent is evidence that a
member ticked a box; a row that staff can type in is not evidence of anything.
"""
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import Document, DocumentConsent, DocumentVersion


class DocumentVersionInline(admin.TabularInline):
    """Every revision of a document, oldest to newest, for reading only.

    Uploading happens on the revision's own page rather than here: an inline
    that both lists history and accepts a new file makes it easy to type into
    the wrong row.
    """

    model = DocumentVersion
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ('label', 'in_force', 'requires_reacceptance', 'consents_given', 'effective_from')
    readonly_fields = fields
    ordering = ('-effective_from', '-pk')

    def has_add_permission(self, request, obj):
        return False

    @admin.display(boolean=True, description='In force')
    def in_force(self, obj):
        return obj.is_in_force

    @admin.display(description='Agreements')
    def consents_given(self, obj):
        return obj.consents.count()


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'slug', 'position', 'audience', 'agreement', 'storefront', 'current_label',
        'revisions', 'created_at',
    )
    list_filter = ('audience', 'agreement', 'storefront',)
    search_fields = ('slug', 'title')
    ordering = ('position', 'slug')
    inlines = (DocumentVersionInline,)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('slug', 'title', 'position', 'audience', 'agreement', 'storefront'),
            'description': (
                'The document itself carries no file and no version. Upload a '
                'file by adding a Document version, then publish it.'
            ),
        }),
        ('Record', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        # The slug is what a consent record's meaning hangs off. Editable while
        # the document is new; frozen the moment anything points at it.
        if obj is not None and obj.versions.exists():
            readonly.append('slug')
        return readonly

    @admin.display(description='In force')
    def current_label(self, obj):
        version = obj.current_version
        return f'v{version.label}' if version else '--'

    @admin.display(description='Revisions')
    def revisions(self, obj):
        return obj.versions.count()


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        'document', 'label', 'state', 'requires_reacceptance', 'consents_given',
        'size', 'effective_from', 'published_by',
    )
    list_filter = ('document', 'requires_reacceptance')
    search_fields = ('document__slug', 'document__title', 'label', 'change_note')
    ordering = ('document__position', '-effective_from', '-pk')
    date_hierarchy = 'created_at'
    actions = ('publish_versions',)

    fieldsets = (
        (None, {
            'fields': ('document', 'label', 'file', 'consent_text'),
            'description': (
                'Upload the file and save. Nothing is offered to members until '
                'the revision is published from the changelist.'
            ),
        }),
        ('Publication', {
            'fields': (
                'requires_reacceptance', 'change_note', 'state',
                'effective_from', 'published_by',
            ),
            'description': (
                'Tick "requires reacceptance" when the change is material: '
                'members who agreed to an earlier revision are asked again. '
                'Leave it unticked for a typo fix.'
            ),
        }),
        ('Integrity', {
            'classes': ('collapse',),
            'fields': (
                'file_link', 'sha256', 'consent_text_sha256', 'byte_size',
                'consents_given', 'created_at', 'updated_at',
            ),
            'description': (
                'The digests are computed from the uploaded bytes and copied '
                'onto every agreement, so a change to either can be detected '
                'after the fact.'
            ),
        }),
    )

    # Computed or set by publish(), never typed.
    base_readonly = (
        'state', 'effective_from', 'published_by', 'sha256', 'consent_text_sha256',
        'byte_size', 'consents_given', 'file_link', 'created_at', 'updated_at',
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.base_readonly)
        if obj is not None and obj.is_published:
            # Everything substantive. See the module docstring.
            readonly += ['document', 'label', 'file', 'consent_text']
        return readonly

    def has_delete_permission(self, request, obj=None):
        """Drafts may be deleted; a published revision may not.

        Bulk delete from the changelist goes through the queryset and bypasses
        ``DocumentVersion.delete``, so the check has to exist here as well. The
        real backstop is the database: ``DocumentConsent.version`` is PROTECT.
        """
        if obj is not None and obj.is_published:
            return False
        return super().has_delete_permission(request, obj)

    @admin.display(description='State')
    def state(self, obj):
        if obj is None or not obj.pk:
            return 'Draft'
        if not obj.is_published:
            return 'Draft -- not offered to members'
        if not obj.is_in_force:
            return f'Scheduled for {obj.effective_from:%Y-%m-%d %H:%M}'
        current = obj.document.current_version
        return 'In force' if current and current.pk == obj.pk else 'Superseded'

    @admin.display(description='Agreements')
    def consents_given(self, obj):
        return obj.consents.count() if obj and obj.pk else 0

    @admin.display(description='Size')
    def size(self, obj):
        return f'{obj.byte_size / 1024:.0f} kB' if obj.byte_size else '--'

    @admin.display(description='File')
    def file_link(self, obj):
        if not obj or not obj.file:
            return '--'
        try:
            url = obj.file.url
        except (ValueError, NotImplementedError):
            # No public URL configured for this storage. The key is still worth
            # showing: it is what would be fetched.
            return obj.file.name
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, url)

    @admin.action(description='Publish selected revisions (cannot be undone)')
    def publish_versions(self, request, queryset):
        published, refused = 0, []
        for version in queryset:
            try:
                version.publish(by=request.user)
            except ValidationError as error:
                refused.append(f'{version}: {" ".join(error.messages)}')
            else:
                published += 1
        if published:
            self.message_user(
                request,
                f'{published} revision(s) published and now in force. Joining '
                'members will be asked to agree to them.',
                messages.SUCCESS,
            )
        for message in refused:
            self.message_user(request, message, messages.ERROR)


@admin.register(DocumentConsent)
class DocumentConsentAdmin(admin.ModelAdmin):
    """The ledger. Read-only, and searchable by member or by document."""

    list_display = (
        'user', 'document_title', 'version_label', 'accepted_at', 'source',
        'file_intact',
    )
    list_filter = ('source', 'version__document', 'version__label')
    search_fields = ('user__email', 'user__nickname', 'version__document__slug')
    date_hierarchy = 'accepted_at'
    ordering = ('-accepted_at',)
    fields = (
        'user', 'version', 'accepted_at', 'source', 'file_sha256',
        'consent_text_sha256', 'agreed_wording', 'file_intact',
    )
    readonly_fields = fields
    list_select_related = ('user', 'version', 'version__document')

    def has_add_permission(self, request):
        # An agreement can only come from a member ticking a box.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Erasing a member is a member action and keeps this row; see
        # DocumentConsent's docstring.
        return False

    @admin.display(description='Document', ordering='version__document__position')
    def document_title(self, obj):
        return obj.version.document.title

    @admin.display(description='Version', ordering='version__label')
    def version_label(self, obj):
        return f'v{obj.version.label}'

    @admin.display(description='Wording agreed to')
    def agreed_wording(self, obj):
        """The revision's sentence, flagged if its digest no longer matches.

        A mismatch should be impossible -- a published revision is immutable --
        which is exactly why it is surfaced rather than assumed away.
        """
        wording = obj.version.consent_text
        if obj.consent_text_sha256 != obj.version.consent_text_sha256:
            return f'CHANGED SINCE AGREEMENT. Current text: {wording}'
        return wording

    @admin.display(boolean=True, description='File intact')
    def file_intact(self, obj):
        return obj.matches_current_file

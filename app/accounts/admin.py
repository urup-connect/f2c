"""The admin view over the member record.

Editable, with three deliberate restrictions. ``is_active`` cannot be set
directly because it is derived from ``status``. The ID number is write-only,
masked to its last four digits, because rendering a member's identity number
into an admin page puts it in the browser cache and the proxy logs for no
operational gain. And erasing a member is an explicit action rather than a side
effect of the delete button.

The authentication tables have their own admin in ``authn.admin``, where they
are read-only.
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import ngettext

from app.common import crypto
from app.common.validators import normalise_id_number

from .forms import UserChangeForm, UserCreationForm
from .models import User, UserStatus


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        'email', 'display_name', 'status', 'id_number_masked',
        'date_of_birth_verified_at', 'is_staff', 'created_at',
    )
    list_filter = ('status', 'is_staff', 'is_superuser', 'groups')
    # Not id_number: it is encrypted with a random nonce per row, so no SQL
    # LIKE can reach it. get_search_results() below handles it separately.
    search_fields = ('email', 'first_name', 'last_name', 'nickname', 'mobile')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    readonly_fields = (
        'id', 'is_active', 'id_number_masked', 'email_hash', 'id_number_hash',
        'last_login', 'created_at', 'updated_at', 'deleted_at',
    )

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Identity', {
            'fields': (
                'first_name', 'last_name', 'nickname', 'mobile',
                'date_of_birth', 'date_of_birth_verified_at',
                'id_number_masked', 'id_number', 'clear_id_number',
            ),
        }),
        ('Access', {
            'fields': ('status', 'is_active', 'is_staff', 'is_superuser'),
            'description': (
                'Only an Active account can sign in. is_active is derived from '
                'status and cannot be edited.'
            ),
        }),
        ('Permissions', {
            'classes': ('collapse',),
            'fields': ('groups', 'user_permissions'),
        }),
        ('Record', {
            'classes': ('collapse',),
            'fields': (
                'email_hash', 'id_number_hash', 'last_login',
                'created_at', 'updated_at', 'deleted_at',
            ),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'password1', 'password2',
                'first_name', 'last_name', 'nickname', 'mobile', 'status',
                'id_number',
            ),
        }),
    )

    actions = ('activate_accounts', 'suspend_accounts', 'erase_accounts')

    @admin.display(description='ID number', ordering=None)
    def id_number_masked(self, obj):
        """Enough to confirm which document is on file, and no more."""
        if not obj.has_id_number:
            return '--'
        try:
            number = obj.id_number
        except crypto.DecryptionError:
            # Surfaced rather than hidden: a row that will not decrypt is a
            # key or integrity problem someone has to look at.
            return 'UNREADABLE'
        return f'{"*" * max(0, len(number) - 4)}{number[-4:]}'

    def get_search_results(self, request, queryset, search_term):
        """Extend the search to exact ID numbers via the blind index.

        A full 13-digit term is looked up by keyed digest, which is the only
        way an encrypted column can be searched at all -- and it is exact-match
        only, so it cannot be used to browse.
        """
        results, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )
        digits = normalise_id_number(search_term)
        if len(digits) >= 6 and digits.isdigit():
            results |= self.model.objects.by_id_number(digits)
        return results, may_have_duplicates

    def has_delete_permission(self, request, obj=None):
        """Hard delete is for superusers only.

        Removing the row cascades into everything that references the member.
        The routine answer to "please delete my account" is the Erase action
        below, which keeps the record and destroys the personal data in it.
        """
        return request.user.is_superuser

    @admin.action(description='Activate selected accounts')
    def activate_accounts(self, request, queryset):
        activated, refused = 0, 0
        for user in queryset:
            try:
                user.activate()
            except ValueError:
                refused += 1
            else:
                activated += 1
        if activated:
            self.message_user(
                request,
                ngettext(
                    '%d account activated.', '%d accounts activated.', activated
                ) % activated,
                messages.SUCCESS,
            )
        if refused:
            self.message_user(
                request,
                f'{refused} erased account(s) were skipped: their personal data '
                'is gone and they cannot be reactivated.',
                messages.WARNING,
            )

    @admin.action(description='Suspend selected accounts (reversible)')
    def suspend_accounts(self, request, queryset):
        count = 0
        for user in queryset:
            user.deactivate(UserStatus.SUSPENDED)
            count += 1
        self.message_user(
            request,
            f'{count} account(s) suspended and signed out. Nothing was erased.',
            messages.SUCCESS,
        )

    @admin.action(
        description='Erase selected accounts (deletes personal data, keeps history)'
    )
    def erase_accounts(self, request, queryset):
        """The POPIA erasure route. Superusers only, and it cannot be undone."""
        if not request.user.is_superuser:
            self.message_user(
                request, 'Only a superuser may erase an account.', messages.ERROR
            )
            return
        count = 0
        for user in queryset:
            user.soft_delete()
            count += 1
        self.message_user(
            request,
            f'{count} account(s) erased: name, nickname, email address and ID '
            'number removed, passkeys and sessions revoked, status set to '
            'Inactive. The records they own are untouched.',
            messages.SUCCESS,
        )

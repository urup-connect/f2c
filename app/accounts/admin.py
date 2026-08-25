"""The admin view over the member record.

Editable, with four deliberate restrictions. ``is_active`` cannot be set
directly because it is derived from ``status``. Group membership cannot either,
because it is derived from ``role``. The ID number is write-only, masked to its
last four digits, because rendering a member's identity number into an admin
page puts it in the browser cache and the proxy logs for no operational gain.
And erasing a member is an explicit action rather than a side effect of the
delete button.

``role`` is an ordinary editable field, and it is the one place a cultivator or
an administrator is appointed. What the chosen role permits is shown beside it,
read from ``accounts.roles`` rather than restated here, so the admin cannot
describe a role the application does not implement.

The **Sharing member** panel holds the columns only that role uses: the
cultivator who registered them, and the consent attestation that makes holding
their identity number lawful. It is editable, because until there is an endpoint
this admin is the only interface staff have -- but
``accounts.services.register_sharing_member`` is the route that validates the
identity number, the age rule and the nickname, and the panel says so. The
database refuses an incomplete sharing member either way.

The authentication tables have their own admin in ``authn.admin``, where they
are read-only.
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html, format_html_join
from django.utils.translation import ngettext

from app.common import crypto
from app.common.validators import normalise_id_number

from .forms import UserChangeForm, UserCreationForm
from .models import User, UserStatus
from .roles import ROLE_PERMISSIONS, describe


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        'email', 'display_name', 'role', 'status', 'id_number_masked',
        'date_of_birth_verified_at', 'is_staff', 'created_at',
    )
    # `role` first: "show me the cultivators" is the question this list is asked
    # most often once there is more than one. `groups` stays, even though it now
    # mirrors the role, because a group added by hand for some other purpose is
    # the one thing filtering on role would not surface.
    # `RelatedOnlyFieldListFilter` lists the cultivators who have actually
    # registered somebody, rather than every account in the table.
    list_filter = (
        'role', 'status',
        ('registered_by', admin.RelatedOnlyFieldListFilter),
        'is_staff', 'is_superuser', 'groups',
    )
    # Not id_number: it is encrypted with a random nonce per row, so no SQL
    # LIKE can reach it. get_search_results() below handles it separately.
    search_fields = ('email', 'first_name', 'last_name', 'nickname', 'mobile')
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    readonly_fields = (
        'id', 'is_active', 'role_permissions', 'groups', 'id_number_masked',
        'email_hash', 'id_number_hash', 'avatar', 'avatar_updated_at',
        'last_login', 'created_at', 'updated_at', 'deleted_at',
    )
    # `groups` is read-only above, so it needs no picker. Leaving it in
    # filter_horizontal would only render a widget nobody can use.
    filter_horizontal = ('user_permissions',)
    # Both point back at User, so a plain select would render every account on
    # the platform into the page. `search_fields` above is what makes these
    # searchable.
    autocomplete_fields = ('registered_by', 'sharing_consent_attested_by')

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
            'fields': (
                'role', 'role_permissions', 'status', 'is_active',
                'is_staff', 'is_superuser',
            ),
            'description': (
                'Only an Active account can sign in, and is_active is derived '
                'from status and cannot be edited. Role and staff status are '
                'independent: Role decides what the account may do on the '
                'platform, and Staff status opens this admin site. Granting '
                'one does not grant the other.'
            ),
        }),
        ('Sharing member', {
            'classes': ('collapse',),
            'fields': (
                'registered_by', 'sharing_consent_attested_by',
                'sharing_consent_attested_at', 'sharing_consent_version',
            ),
            'description': (
                'Only for accounts in the Sharing member role, and required '
                'for all of them: the database refuses a sharing member with '
                'no cultivator, no attestation or no nickname. The '
                'attestation is the club’s lawful basis under POPIA for '
                'holding this person’s name and identity number — they '
                'registered no form themselves — so it should record a '
                'confirmation actually given, by whoever gave it. Prefer '
                'accounts.services.register_sharing_member, which validates '
                'the identity number and the age rule as well.'
            ),
        }),
        ('Permissions', {
            'classes': ('collapse',),
            'fields': ('groups', 'user_permissions'),
            'description': (
                'Group membership mirrors the Role above and is maintained '
                'automatically, so it cannot be edited here. To change what a '
                'whole role may do, edit the group itself under '
                'Authentication and Authorisation.'
            ),
        }),
        ('Photograph', {
            'classes': ('collapse',),
            'fields': ('avatar', 'avatar_updated_at'),
            'description': (
                'The member’s own photograph, which they set on their profile '
                'screen. Read-only here: every stored avatar is a 512-pixel '
                'square JPEG that accounts.avatars produced by decoding and '
                're-encoding the upload, which is what strips the EXIF a phone '
                'photograph carries — including where it was taken. A file '
                'placed here by hand would bypass all of that. To remove one, '
                'use the member’s profile screen or accounts.profile.'
            ),
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
                'first_name', 'last_name', 'nickname', 'mobile',
                'role', 'status', 'id_number',
            ),
        }),
    )

    actions = ('activate_accounts', 'suspend_accounts', 'erase_accounts')

    @admin.display(description='What this role may do')
    def role_permissions(self, obj):
        """The catalogue entries the saved role carries, read from the source.

        Rendered from ``accounts.roles`` rather than written out here, so this
        panel cannot describe authority the application does not actually grant.
        It reflects the role **as saved**: a role changed in the form above
        appears here after the save, not before, because the catalogue is keyed
        on what is stored.

        A superuser is called out rather than listed. Django grants a superuser
        every permission before any backend is asked, so printing the role's set
        beside an account that is not bound by it would be a lie of omission.
        """
        if obj is None or obj.pk is None:
            return 'Saved once the account is created.'
        if obj.is_superuser:
            return format_html(
                '<em>{}</em>',
                'Superuser: every action on the platform, whatever the role '
                'says.',
            )
        if not obj.is_active:
            return format_html(
                '<em>{}</em>',
                'None: this account is not Active, so it holds no permissions '
                'at all. The role applies again once it is reactivated.',
            )
        codenames = sorted(ROLE_PERMISSIONS.get(obj.role, ()))
        if not codenames:
            return 'None.'
        return format_html(
            '<ul style="margin:0;padding-left:1.2em">{}</ul>',
            format_html_join(
                '',
                '<li>{}<br><small style="color:var(--body-quiet-color)">{}'
                '</small></li>',
                ((codename, describe(codename)) for codename in codenames),
            ),
        )

    @admin.display(description='ID number', ordering=None)
    def id_number_masked(self, obj):
        """Enough to confirm which document is on file, and no more.

        Delegates to ``User.id_number_masked``, which is
        ``common.validators.mask_id_number``. It was this method's own rule
        until a member became able to see their own number on the profile
        screen; two maskings of one field is one of them eventually showing
        more than the other meant to.
        """
        if not obj.has_id_number:
            return '--'
        try:
            return obj.id_number_masked
        except crypto.DecryptionError:
            # Surfaced rather than hidden: a row that will not decrypt is a
            # key or integrity problem someone has to look at.
            return 'UNREADABLE'

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
            # Two reasons reach here, and `activate()` raises the same
            # exception for both: an erased account has no personal data left
            # to come back to, and a sharing member has nothing to activate
            # because it never signs in. Named together rather than counted
            # separately -- the action's job is to report what it skipped, and
            # the individual reason is on each record.
            self.message_user(
                request,
                f'{refused} account(s) were skipped: an erased account cannot '
                'be reactivated, and a sharing member holds stock without '
                'ever signing in.',
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

"""The admin view over the account: who somebody is, not what they belong to.

Editable, with three deliberate restrictions. ``is_active`` cannot be set
directly because it is derived from ``status``. The ID number is write-only,
masked to its last four digits, because rendering a member's identity number
into an admin page puts it in the browser cache and the proxy logs for no
operational gain. And erasing a member is an explicit action rather than a side
effect of the delete button.

**There is no role field, because there is no role column** -- C28. What an
account may do comes from three relationships, and **none of them is
administered here**: a club membership under Membership, a storefront
appointment under Storefronts, and an appointment to a producer as an inline on
the farm. The Relationships panel links to whichever of the three exist rather
than reproducing them, because C27 split identity from membership precisely so
that one page does not answer for both. The permission set they add up to is
shown read-only, resolved through ``accounts.roles`` rather than restated, so
the admin cannot describe an authority the application does not grant.

**The nickname and the Sharing member panel are gone from this page**, and both
went with a record rather than with a decision. The nickname is a property of
belonging to the club and now lives on ``ClubMembership`` with the unique index
that governs it; a produce-market customer has a name and needs no pseudonym.
The sharing-member columns went further than moving -- C6 decided a placeholder
is not a person, so the names, the identity number and the consent attestation
were deleted outright, and the one column left is the producer whose stock it
holds.

Django's group and user-permission machinery is left as Django ships it. The
groups used to mirror the role column and were maintained by ``save()``; with no
column to mirror, nothing here writes them and nothing here reads them --
``RoleBackend`` answers ``platform.*`` from the relationships above, and
``ModelBackend`` still answers for anything a member of staff hangs on a group
by hand.

The authentication tables have their own admin in ``authn.admin``, where they
are read-only.
"""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import ngettext

from app.core.common import crypto
from app.core.common.validators import normalise_id_number

from . import notifications
from .forms import UserChangeForm, UserCreationForm
from .models import User, UserStatus
from .roles import describe, permissions_for


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        'email', 'display_name', 'status', 'id_number_masked',
        'date_of_birth_verified_at', 'is_staff', 'created_at',
    )
    # **No role filter, because there is no role column** -- C28. "Show me the
    # cultivators" is still the question this list is asked most often, and it
    # is now a join rather than a value: the answer is the Producers admin,
    # where every farm lists the people appointed to it, and the register's own
    # filter (`administration.REGISTER_RELATIONSHIPS`) for the club's screens.
    list_filter = ('status', 'is_staff', 'is_superuser', 'groups')
    # Not id_number: it is encrypted with a random nonce per row, so no SQL
    # LIKE can reach it. get_search_results() below handles it separately.
    # The nickname moved to `ClubMembership` with C27 and is searched through
    # the relation, so staff can still find somebody by the name the club knows
    # them by.
    search_fields = (
        'email', 'first_name', 'last_name', 'mobile',
        'club_membership__nickname',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    readonly_fields = (
        'id', 'is_active', 'platform_permissions', 'relationships',
        'id_number_masked', 'email_hash', 'id_number_hash', 'avatar',
        'avatar_updated_at', 'last_login', 'created_at', 'updated_at',
        'deleted_at',
    )
    # `groups` is editable again. It was read-only while `save()` mirrored the
    # role column into it -- a picker whose value would be overwritten on the
    # next save is worse than no picker. C28 removed the mirroring, so nothing
    # maintains these now and a group is once more only what somebody put in it.
    filter_horizontal = ('groups', 'user_permissions')

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Identity', {
            'fields': (
                'first_name', 'last_name', 'mobile',
                'date_of_birth', 'date_of_birth_verified_at',
                'id_number_masked', 'id_number', 'clear_id_number',
            ),
        }),
        ('Access', {
            'fields': (
                'relationships', 'platform_permissions', 'status', 'is_active',
                'is_staff', 'is_superuser',
            ),
            'description': (
                'Only an Active account can sign in, and is_active is derived '
                'from status and cannot be edited. Signing in is now a '
                'separate question from belonging to the club: an unpaid '
                'member signs in and lands on a screen asking them to pay, and '
                'a produce-market customer has no club membership at all. What '
                'this account may do comes from the relationships listed here, '
                'each of which is granted on its own page. Staff status is '
                'independent of all of them — it opens this admin site and '
                'nothing else.'
            ),
        }),
        ('Permissions', {
            'classes': ('collapse',),
            'fields': ('groups', 'user_permissions'),
            'description': (
                'Django’s own permissions, and nothing on this platform reads '
                'them. They used to mirror the retired Role column and are now '
                'only what somebody puts in them, kept for anything hung on a '
                'group by hand. To change what an administrator or a '
                'cultivator may do, edit the catalogue in accounts.roles — not '
                'this.'
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
                'first_name', 'last_name', 'mobile',
                'status', 'id_number',
            ),
        }),
    )

    actions = ('activate_accounts', 'suspend_accounts', 'erase_accounts')

    def get_queryset(self, request):
        """Join the membership the list and the search both reach for.

        ``display_name`` prefers the club nickname, which C27 moved one table
        away, so every row of this list walks a reverse one-to-one. Unselected
        that is **a query per account** on a page that shows a hundred of them
        — risk 11 in ``design/features/roles-and-permissions.md``, which is
        about exactly this relation being left lazy.
        """
        return super().get_queryset(request).select_related('club_membership')

    @admin.display(description='Belongs to')
    def relationships(self, obj):
        """The three relationships that decide authority, linked not copied.

        Each is granted on its own page and none of them is editable from here
        — that is C27 and C28 in the interface, and reproducing the fields
        would be the split undone. A relationship that does not exist is not
        listed: an account with nothing here is a produce-market customer, and
        saying so is more use than three empty rows.
        """
        # `_state.adding` rather than `pk is None`, which is the obvious test
        # and is wrong on every model here: the primary key is a `UUIDField`
        # with `default=uuid.uuid7`, so an unsaved instance already carries one
        # and the guard would never fire.
        if obj is None or obj._state.adding:
            return 'Saved once the account is created.'

        rows = []
        membership = getattr(obj, 'club_membership', None)
        if membership is not None:
            rows.append((
                'admin:membership_clubmembership_change',
                membership.pk,
                f'Club membership — {membership.get_status_display()}',
            ))
        for appointment in obj.storefront_appointments.all():
            rows.append((
                'admin:storefronts_storefrontstaff_change',
                appointment.pk,
                f'{appointment.get_storefront_display()} — administrator',
            ))
        for appointment in obj.producer_appointments.select_related('producer'):
            rows.append((
                'admin:producers_producer_change',
                appointment.producer_id,
                f'{appointment.producer.trading_name} — '
                f'{appointment.get_role_display().lower()}',
            ))

        if not rows:
            return format_html(
                '<em>{}</em>',
                'Nothing: this account has joined no club, administers no '
                'storefront and is appointed to no producer. On the produce '
                'market that is an ordinary customer.',
            )
        return format_html(
            '<ul style="margin:0;padding-left:1.2em">{}</ul>',
            format_html_join(
                '',
                '<li><a href="{}">{}</a></li>',
                ((reverse(route, args=(pk,)), label) for route, pk, label in rows),
            ),
        )

    @admin.display(description='What this account may do')
    def platform_permissions(self, obj):
        """The catalogue entries these relationships carry, read from the source.

        Rendered from ``accounts.roles`` rather than written out here, so this
        panel cannot describe authority the application does not actually grant.
        It reflects what is **saved**: a relationship added on another page
        appears here once it exists, because the catalogue is keyed on what is
        stored rather than on what is on screen.

        A superuser is called out rather than listed. Django grants a superuser
        every permission before any backend is asked, so printing a resolved set
        beside an account that is not bound by it would be a lie of omission.
        """
        # `_state.adding` rather than `pk is None`, which is the obvious test
        # and is wrong on every model here: the primary key is a `UUIDField`
        # with `default=uuid.uuid7`, so an unsaved instance already carries one
        # and the guard would never fire.
        if obj is None or obj._state.adding:
            return 'Saved once the account is created.'
        if obj.is_superuser:
            return format_html(
                '<em>{}</em>',
                'Superuser: every action on the platform, whatever the '
                'relationships say.',
            )
        if not obj.is_active:
            return format_html(
                '<em>{}</em>',
                'None: this account is not Active, so it holds no permissions '
                'at all. Its relationships apply again once it is reactivated.',
            )
        codenames = sorted(permissions_for(obj))
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
        """``platform.revoke_access``: off the platform, both storefronts.

        Not the same action as the club register's *suspend*, which suspends a
        club **membership** and leaves the account able to use the produce
        market. This one blocks sign-in outright, so the member cannot reach a
        screen that explains it -- ``authn.api._find_user`` filters to Active and
        the endpoints answer a suspended account exactly as they answer a
        stranger. The email is therefore the only channel there is, which is why
        it is sent here rather than offered as an option.
        """
        count = 0
        told = 0
        for user in queryset:
            user.deactivate(UserStatus.SUSPENDED)
            count += 1
            if notifications.email_access_revoked(user):
                told += 1

        untold = count - told
        self.message_user(
            request,
            f'{count} account(s) suspended and signed out, {told} emailed. '
            'Nothing was erased.'
            + (
                f' {untold} hold no email address and were not told.'
                if untold
                else ''
            ),
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
            f'{count} account(s) erased: name, email address and ID '
            'number removed, passkeys and sessions revoked, status set to '
            'Inactive. The records they own are untouched.',
            messages.SUCCESS,
        )

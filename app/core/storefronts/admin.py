"""The admin over who administers a storefront.

The last of the three relationships C28 split the role column into. A club
membership has its own page under Membership, an appointment to a producer is an
inline on the farm it belongs to, and this is the third: the appointment that
makes somebody an administrator of the club or of the produce market.

**This page grants authority, which none of the other two does on its own.**
``accounts.roles.permissions_for`` reads an appointment over the club and
returns the administrator set from it, so adding a row here is the whole of
making somebody a club administrator -- there is no second step and no column to
set on the account. The description on the form says so, because a page whose
only field is a dropdown does not otherwise look like the one that hands over
the register.

**There is no UC tier here** -- C29. The platform operator is ``User.is_staff``,
granted on the account page, and it opens this admin site rather than a
storefront. Somebody who administers the club is not thereby staff, and staff
are not thereby administrators of anything.

**Revocation is the delete button, and that is the mechanism.** The model keeps
no ``revoked_at``: an appointment that has ended is not a fact the platform
reasons about, and Django's ``LogEntry`` already records who removed it and
when. So unlike the member record -- where deleting cascades into everything
somebody grew and erasure is the routine answer -- deleting here is ordinary and
is left available.

``appointed_by`` is provenance rather than meaning, which is why it is
``SET_NULL`` on the model and why it is merely defaulted rather than forced
here: an appointment recorded after the fact was still made by somebody, and a
field that always said "whoever typed it in" would be a worse record than a
blank one.
"""
from django.contrib import admin

from .models import StorefrontStaff


@admin.register(StorefrontStaff)
class StorefrontStaffAdmin(admin.ModelAdmin):
    list_display = ('person', 'storefront', 'appointed_by', 'appointed_at')
    list_filter = ('storefront',)
    search_fields = (
        'user__email', 'user__first_name', 'user__last_name',
        'user__club_membership__nickname',
    )
    ordering = ('storefront', 'appointed_at')
    date_hierarchy = 'appointed_at'
    autocomplete_fields = ('user', 'appointed_by')

    readonly_fields = ('id', 'appointed_at')

    fieldsets = (
        (None, {
            'fields': ('id', 'user', 'storefront'),
            'description': (
                'Adding a row here is the whole of making somebody an '
                'administrator: what an account may do is read from its '
                'relationships, and this is one of them. An appointment over '
                'Cultivators Collective grants the club administrator '
                'permissions in full. It does not grant access to this admin '
                'site — that is Staff status on the account — and it does not '
                'make the person a member of the club.'
            ),
        }),
        ('Provenance', {
            'fields': ('appointed_by', 'appointed_at'),
            'description': (
                'Who granted this, defaulted to you. It is a record of how the '
                'appointment came about and nothing reads it for authority, so '
                'it can be left blank or set to somebody else where an '
                'appointment is being written up after the fact. It clears '
                'itself if that person is later erased.'
            ),
        }),
    )

    def get_queryset(self, request):
        # Both name columns walk to an account, and `person` reads the club
        # nickname off the membership behind it.
        return (
            super().get_queryset(request)
            .select_related('user', 'user__club_membership', 'appointed_by')
        )

    def get_changeform_initial_data(self, request):
        """Default the grantor to whoever is filling the form in.

        The overwhelmingly common case is somebody appointing an administrator
        now, and making them pick themselves out of an autocomplete is a step
        that only ever has one right answer. Defaulted rather than forced, for
        the reason the module docstring gives.
        """
        initial = super().get_changeform_initial_data(request)
        initial.setdefault('appointed_by', request.user.pk)
        return initial

    @admin.display(description='Administrator', ordering='user__email')
    def person(self, obj):
        """What to call the appointee.

        ``display_name`` rather than the email address, because a club
        administrator is very often a member and the club knows them by their
        nickname -- and because a market administrator may have no nickname at
        all, which is what the fallback is for. The relation it reads is
        selected in ``get_queryset``; unselected this is a query per row.
        """
        return obj.user.display_name

    def get_readonly_fields(self, request, obj=None):
        """Who and which storefront are fixed once the appointment exists.

        Moving a saved row from the club to the market reads as a correction
        and is not one: it ends one appointment and begins another, against a
        different set of permissions, while keeping the original
        ``appointed_at`` and leaving a single ``LogEntry`` saying "changed".
        Revoking and appointing says the same thing truthfully. The same
        argument covers the appointee -- an appointment retyped onto somebody
        else is two events, and one of them is somebody quietly losing the
        register.

        ``appointed_by`` stays editable, because it is provenance: an
        appointment written up after the fact is corrected by saying who
        actually made it, which changes nothing about who holds what.
        """
        if obj is None:
            return self.readonly_fields
        return (*self.readonly_fields, 'user', 'storefront')

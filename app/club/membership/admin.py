"""The admin over belonging to the club.

This page did not exist before the split, because none of what is on it was its
own record: the status, the nickname and the sharing-member columns all sat on
``User`` and were administered from the account page. C27 moved them here, and
the account admin was left with a Membership panel it could no longer render and
a nickname field with no column behind it.

**Editable, and the nickname is the reason.** Everything else here has a service
behind it -- registration writes the row, payment activates it,
``lapse_memberships`` lapses it -- but a member who has typed their nickname
wrongly has no screen of their own to fix it on, and until Block 9 gives the
register one this is the only interface staff have. The clash check is the same
one ``administration._validated_nickname`` runs, called rather than restated: a
second copy of "is this taken" is how one of them ends up comparing the raw text
while the index compares the key.

**Suspending is an action, not the status field.** Both routes are here and they
are not equivalent -- ``administration.suspend_member`` refuses an erased
account, refuses a placeholder, refuses the caller's own record and ends every
live session, and a dropdown does none of that. The field stays editable because
staff need to correct a status that is simply wrong, and ``save_model`` below
closes the one gap that leaves: a membership edited out of Active in the form
would otherwise keep a signed-in browser working until its cookie expired.

``registered_by`` points at the **producer**, not at the person who keyed the
placeholder in -- see ``models.ClubMembership``. It is the only field the
Sharing member panel has left; C6 took the names, the identity number and the
attestation with it.
"""
from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils.html import format_html

from . import administration
from .models import ClubMembership, MembershipStatus

#: The statuses that open the club. Anything else and a live session is a
#: browser still working after the membership stopped -- see ``save_model``.
_MAY_USE_THE_CLUB = frozenset({MembershipStatus.ACTIVE})


class ClubMembershipAdminForm(forms.ModelForm):
    """Turns the nickname's unique index into a field error.

    Without it, renaming a member onto a nickname somebody already wears
    returns a 500 to a member of staff who made an ordinary mistake. The rule
    lives in ``administration._validated_nickname`` and is called from here, so
    the admin and the register cannot drift on what "taken" means -- the
    comparison is against ``nickname_key``, and a hand-written ``iexact`` here
    would disagree with the index at the margins the key exists to settle.
    """

    class Meta:
        model = ClubMembership
        fields = '__all__'

    def clean_nickname(self):
        try:
            return administration._validated_nickname(
                self.cleaned_data.get('nickname'), exclude_pk=self.instance.pk
            )
        except ValidationError as error:
            # Re-raised rather than allowed through: the service raises the
            # same exception class the form wants, but on the form it has to be
            # attached to this field to render beside it.
            raise ValidationError(error.messages, code='nickname') from error


@admin.register(ClubMembership)
class ClubMembershipAdmin(admin.ModelAdmin):
    form = ClubMembershipAdminForm

    list_display = (
        'nickname_or_account', 'account_email', 'status', 'registered_by',
        'joined_at', 'activated_at',
    )
    # `status` first: "who has not paid" is what this list is opened for.
    # `registered_by` is limited to the producers that actually hold
    # placeholders rather than listing every farm on the platform.
    list_filter = ('status', ('registered_by', admin.RelatedOnlyFieldListFilter))
    search_fields = (
        'nickname', 'user__email', 'user__first_name', 'user__last_name',
    )
    ordering = ('-joined_at',)
    date_hierarchy = 'joined_at'
    autocomplete_fields = ('user', 'registered_by')

    readonly_fields = (
        'id', 'nickname_key', 'account_link', 'joined_at', 'activated_at',
        'created_at', 'updated_at',
    )

    fieldsets = (
        (None, {'fields': ('id', 'user', 'account_link')}),
        ('The club', {
            'fields': ('status', 'nickname', 'nickname_key', 'activated_at'),
            'description': (
                'Only an Active membership opens the club. The account signs '
                'in either way — an unpaid registrant lands on a screen asking '
                'them to pay — so suspending a membership here does not lock '
                'anybody out of the produce market. Use the Suspend action '
                'rather than this dropdown where you can: it refuses the '
                'records that must not be touched and signs the member out. '
                'nickname_key is derived from the nickname and cannot be set.'
            ),
        }),
        ('Sharing member', {
            'fields': ('registered_by',),
            'description': (
                'A sharing member is a placeholder a producer creates so that '
                'flowering stock can sit in the swap zone — not a person, and '
                'it holds no name, no identity number and no consent (C6). '
                'The producer is the one thing it cannot be without: without '
                'it the row is orphaned stock. Leave this blank for an '
                'ordinary member. The route that creates one is '
                'accounts.services.register_sharing_member.'
            ),
        }),
        ('Record', {
            'classes': ('collapse',),
            'fields': ('joined_at', 'created_at', 'updated_at'),
        }),
    )

    actions = ('suspend_memberships', 'reinstate_memberships')

    def get_queryset(self, request):
        # Every row renders the account's email address and the producer's
        # trading name, so both are joined rather than fetched per row.
        return (
            super().get_queryset(request)
            .select_related('user', 'registered_by')
        )

    @admin.display(description='Nickname', ordering='nickname')
    def nickname_or_account(self, obj):
        """The club's name for this member, or the account behind it.

        ``ClubMembership.__str__`` in a method so the column can be ordered on
        the nickname. A blank nickname is legitimate — a produce customer who
        later joined has a name and no pseudonym — so it falls back rather than
        rendering an empty cell.
        """
        return str(obj)

    @admin.display(description='Account', ordering='user__email')
    def account_email(self, obj):
        """The address on the account, or a dash for a placeholder.

        A placeholder has no email address at all — it never signs in — and
        that is what distinguishes it at a glance from a member whose
        membership merely lapsed.
        """
        return obj.user.email or '—'

    @admin.display(description='The person')
    def account_link(self, obj):
        """A link to the account page rather than a copy of what is on it.

        The identity — name, mobile, identity number, whether they may sign in
        at all — belongs to ``accounts.User`` and is administered there. C27
        split the two records precisely so that one page does not answer for
        both, and mirroring the fields here would be the split undone in the
        interface.
        """
        # `_state.adding` rather than `pk is None`, which is the obvious test
        # and is wrong on every model here: the primary key is a `UUIDField`
        # with `default=uuid.uuid7`, so an unsaved instance already carries one
        # and the guard would never fire.
        if obj is None or obj._state.adding:
            return 'Saved once the membership is created.'
        url = reverse('admin:accounts_user_change', args=(obj.user_id,))
        return format_html('<a href="{}">{}</a>', url, obj.user.display_name)

    def save_model(self, request, obj, form, change):
        """Save, and end the sessions of a membership that just lost the club.

        Not a second copy of ``suspend_member``'s rules — it is the same
        guarantee at the one other place a membership can leave Active. The
        action refuses records and reports skips; this only makes sure that a
        status edited in the form cannot leave a signed-in browser working
        against a club the member no longer belongs to.
        """
        was_live = False
        if change and 'status' in form.changed_data:
            was_live = form.initial.get('status') in _MAY_USE_THE_CLUB

        super().save_model(request, obj, form, change)

        if was_live and obj.status not in _MAY_USE_THE_CLUB:
            obj.user.flush_sessions()

    @admin.action(description='Suspend selected memberships (reversible)')
    def suspend_memberships(self, request, queryset):
        self._apply(request, queryset, administration.suspend_member, 'suspended')

    @admin.action(description='Reinstate selected memberships')
    def reinstate_memberships(self, request, queryset):
        self._apply(request, queryset, administration.reinstate_member, 'reinstated')

    def _apply(self, request, queryset, service, verb):
        """Run one register service over a selection and report what it refused.

        The services take the **account**, not the membership, because that is
        what the register's screens hold — so this walks
        ``membership.user``. Each refusal is reported with the sentence the
        service raised rather than counted: an erased account, a placeholder,
        a membership that was never suspended and the administrator's own
        record are four different refusals, and a count would flatten them into
        a number nobody can act on.

        ``PermissionDenied`` is caught rather than allowed to render Django's
        403 page. A member of staff without the register's permission has done
        nothing wrong; being told so on the page they are already on is a
        better answer than being thrown off it.
        """
        done = 0
        for membership in queryset:
            try:
                service(request.user, membership.user)
            except PermissionDenied as error:
                self.message_user(request, str(error), messages.ERROR)
                return
            except ValidationError as error:
                self.message_user(
                    request,
                    f'{membership}: {" ".join(error.messages)}',
                    messages.WARNING,
                )
            else:
                done += 1

        if done:
            self.message_user(
                request, f'{done} membership(s) {verb}.', messages.SUCCESS
            )

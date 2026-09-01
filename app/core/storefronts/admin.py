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

**The second page here is the send log**, which has nothing to do with
appointments and is here because ``EmailDispatch`` is -- this app owns how a
message leaves and therefore owns the record that it did. It is read-only and it
is where "was the member told?" gets answered.
"""
from django.contrib import admin

from .models import EmailDispatch, StorefrontStaff


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


@admin.register(EmailDispatch)
class EmailDispatchAdmin(admin.ModelAdmin):
    """Every email the platform has sent a member. Read-only throughout.

    **Read-only for the reason the agreement ledger is.** This page is what
    answers "was the member told?", and a row an operator can type into answers
    nothing. There is no add button either: an email exists here because
    ``storefronts.mail`` sent one, and a row written by hand would be a record of
    a message nobody received.

    **Deleting is left available, unlike the consent ledger, and only just.**
    Retention is a schedule rather than a judgement -- ``purge_email_dispatches``
    on a timer, per ``EMAIL_DISPATCH_RETENTION_DAYS`` -- and the delete button is
    for the case the schedule does not cover: a test send, or a batch from a
    misconfigured environment, that should not sit in the report. It is
    superuser-only, because a delete here is the one thing on this page that can
    make the log say something untrue.

    **The two blank columns are the point of the page, not a fault in it.**
    *Delivered* and *Read* sit empty on this deployment: SMTP reports neither,
    and no open beacon is embedded. They read "Not reported" and "Not tracked"
    rather than "No", because an operator deciding whether to phone a member
    needs to know the difference between *we know it did not arrive* and *we
    cannot tell*.
    """

    list_display = (
        'queued_at', 'kind', 'person', 'storefront', 'send_status',
        'delivery_status', 'read_status', 'caused_by',
    )
    list_filter = (
        'kind', 'storefront', 'send_status', 'delivery_status', 'read_status',
        'trigger',
    )
    # The recipient's address is not on this model -- see `EmailDispatch` -- so
    # every search here walks to the account, which is also what makes an erased
    # member unsearchable by an address they no longer hold.
    search_fields = (
        'subject',
        'recipient__email',
        'recipient__first_name',
        'recipient__last_name',
        'recipient__club_membership__nickname',
        'provider_message_id',
    )
    date_hierarchy = 'queued_at'
    ordering = ('-queued_at',)
    list_select_related = (
        'recipient', 'recipient__club_membership', 'triggered_by'
    )

    fieldsets = (
        ('The message', {
            'fields': ('id', 'kind', 'storefront', 'recipient', 'subject'),
            'description': (
                'The subject line is kept; the body is not. A sign-in code and '
                'a payment link both live in the body, and neither belongs in a '
                'table staff can read. The recipient’s address is not stored '
                'either — it is read off the account at the moment of sending, '
                'which is why erasing an account also de-identifies its send '
                'history.'
            ),
        }),
        ('Sent', {
            'fields': ('send_status', 'queued_at', 'sent_at', 'send_error'),
            'description': (
                'Whether the mail server accepted the message. This is the one '
                'stage that is genuinely known. A row still saying “Not handed '
                'over yet” is an attempt that was interrupted — the outcome is '
                'unknown rather than negative.'
            ),
        }),
        ('Delivered', {
            'fields': ('delivery_status', 'delivered_at', 'delivery_detail'),
            'description': (
                'Whether it reached the mailbox. The current mail setup cannot '
                'say: acceptance by a relay is not delivery, and only a provider '
                'that reports events back can close this gap. Expect “Not '
                'reported” on every row until one is configured.'
            ),
        }),
        ('Read', {
            'fields': ('read_status', 'read_at'),
            'description': (
                'Whether it was opened. Deliberately not tracked — that needs an '
                'invisible image in the message, which is not something to put '
                'in a one-time code, and which several mail clients answer '
                'wrongly in both directions.'
            ),
        }),
        ('Provenance', {
            'fields': ('trigger', 'triggered_by', 'provider_message_id'),
            'description': (
                'What set the send off. A blank person against “The recipient” '
                'is not a missing record: a sign-in code is asked for by '
                'somebody who is not signed in yet, so the platform has the '
                'address that was typed and no proof of who typed it.'
            ),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        """Every column, always. Nothing on this page is editable by anybody."""
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        # An email exists here because one was sent. See the class docstring.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    @admin.display(description='Recipient', ordering='recipient__email')
    def person(self, obj):
        """What to call the member, the way `StorefrontStaffAdmin` does.

        ``display_name`` rather than the address: the club knows its members by
        nickname, a market customer may have none, and an erased account has no
        address left to show. The relations are selected in
        ``list_select_related``; unselected this is two queries per row.
        """
        return obj.recipient.display_name

    @admin.display(description='Caused by', ordering='trigger')
    def caused_by(self, obj):
        """One column for the "system or a person" question.

        The two fields answer it together and are useless apart -- a blank
        ``triggered_by`` means different things under each trigger -- so they are
        shown as one phrase rather than as two columns an operator has to
        combine mentally.
        """
        if obj.triggered_by_id is not None:
            return obj.triggered_by.display_name
        return obj.get_trigger_display()

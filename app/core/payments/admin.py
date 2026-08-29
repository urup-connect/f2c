"""The admin view over subscriptions and payments. Read-only, deliberately.

Everything here is written by a Payfast notification, and a payment is a fact
about the outside world rather than a field somebody should be able to correct.
Editing ``paid_until`` by hand would grant a membership nobody paid for and
leave no trace of who did it; editing an amount would make our records disagree
with Payfast's, which is the one thing a reconciliation exists to detect.

So the admin answers questions and takes no actions. **The action staff actually
need is already elsewhere**: *Activate selected accounts* on the member admin,
which is the honest way to let somebody in who paid by EFT or whose notification
never arrived. It changes the account and says nothing about a payment, which is
exactly right -- because no payment happened here.

The one thing this admin is for is answering "why can this member not sign in?"
without opening the Payfast dashboard. Hence the paid-up date on the list, the
payments inline, and the search on the member rather than on a token.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import Payment, Subscription


class PaymentInline(admin.TabularInline):
    """Every movement of money against this subscription, oldest last.

    An inline rather than a link, because the question this admin is opened
    with -- why is this membership not active -- is usually answered by whether
    a payment exists at all.
    """

    model = Payment
    extra = 0
    can_delete = False
    fields = (
        'gateway_payment_id',
        'status',
        'amount_gross',
        'amount_fee',
        'amount_net',
        'covers_until',
        'received_at',
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'member',
        'status',
        'amount',
        'frequency',
        'paid_until',
        'awaiting_payment',
        'created_at',
    )
    list_filter = ('status', 'frequency')
    # The member, never the token. A checkout token is a bearer credential: a
    # searchable one is one that ends up in a screenshot, and knowing it is
    # enough to pay somebody else's subscription. `gateway_token` is Payfast's
    # handle on the mandate and is no more useful here than in the dashboard.
    search_fields = (
        'user__email',
        'user__first_name',
        'user__last_name',
        'user__nickname',
    )
    autocomplete_fields = ('user',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    inlines = (PaymentInline,)

    readonly_fields = (
        'id',
        'user',
        'status',
        'amount',
        'frequency',
        'cycles',
        'paid_until',
        'gateway_token',
        'checkout_expires_at',
        'activated_at',
        'cancelled_at',
        'lapsed_at',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (None, {'fields': ('id', 'user', 'status')}),
        (
            'What was agreed',
            {
                'fields': ('amount', 'frequency', 'cycles'),
                'description': (
                    'Copied onto this row when the member agreed to it. Changing '
                    'the configured price changes what new members are asked '
                    'for and nothing here.'
                ),
            },
        ),
        (
            'Where it stands',
            {
                'fields': (
                    'paid_until',
                    'gateway_token',
                    'checkout_expires_at',
                    'activated_at',
                    'cancelled_at',
                    'lapsed_at',
                ),
                'description': (
                    'Paid until is the date access runs out. Nothing here is '
                    'editable: to let somebody in who paid another way, use '
                    'Activate selected accounts on the member instead.'
                ),
            },
        ),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def has_add_permission(self, request):
        # A subscription is opened by a registration, in the same transaction
        # that writes the member. One added here would have no member behind it
        # and no mandate at Payfast.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Payment rows point here with PROTECT, so a delete would fail anyway --
        # but it should not be offered. A subscription is the history of what a
        # member agreed to pay.
        return False

    @admin.display(description='Member', ordering='user__email')
    def member(self, obj):
        return obj.user.display_name or obj.user.email or str(obj.user_id)

    @admin.display(description='Awaiting payment', boolean=True)
    def awaiting_payment(self, obj):
        """Whether the checkout link still resolves.

        The column that answers "has this person been able to pay yet?". A
        pending subscription with an expired checkout is a member who needs a
        fresh link, which is a different problem from one who never started.
        """
        return obj.checkout_is_usable()


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'gateway_payment_id',
        'member',
        'status',
        'amount_gross',
        'covers_until',
        'received_at',
    )
    list_filter = ('status',)
    search_fields = ('gateway_payment_id', 'subscription__user__email')
    date_hierarchy = 'received_at'
    ordering = ('-received_at',)
    readonly_fields = (
        'subscription',
        'gateway_payment_id',
        'status',
        'amount_gross',
        'amount_fee',
        'amount_net',
        'covers_until',
        'received_at',
        'reconciliation',
    )
    fields = readonly_fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'subscription', 'subscription__user'
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # The record of money that moved. Deleting it does not unmake the
        # payment, it only makes the next reconciliation unexplainable.
        return False

    @admin.display(description='Member', ordering='subscription__user__email')
    def member(self, obj):
        user = obj.subscription.user
        return user.display_name or user.email or str(user.pk)

    @admin.display(description='Reconciliation')
    def reconciliation(self, obj):
        """What to quote to Payfast, and what to check it against.

        Shown because this is the field a dispute is worked from and nothing
        else in the admin holds it: no notification is stored verbatim, so
        Payfast's dashboard is the other half of the record. See
        ``models`` on why.
        """
        return format_html(
            'Payfast payment <code>{}</code> against subscription '
            '<code>{}</code>. Amounts are as Payfast reported them; the fee is '
            'negative in its own figures and is stored unchanged.',
            obj.gateway_payment_id,
            obj.subscription_id,
        )

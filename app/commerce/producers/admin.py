"""The admin over producers and the people appointed to them.

Editable, like the catalogue admins and unlike the payments one: a producer's
public copy is what a grower writes about themselves, and until Block 9 gives
them a screen, staff are the only people who can write it.

Publication is a field rather than an action, which is the one place this
departs from the documents admin. There, publishing a revision is irreversible
and so had to be an explicit action rather than a side effect of a save.
Publishing a producer is neither irreversible nor consequential -- clearing the
tick takes it down again, and nothing agreed to it -- so a checkbox is honest.

**Appointments and storefronts are inlines, not separate pages.** Neither means
anything away from the producer it belongs to: an appointment with no farm is
not an appointment, and "sells into the market" is a sentence about a farm. The
one-to-one to a user is gone, so this page is where a producer's people are
managed -- see ``models.Producer``.

The bank account number is **never rendered**. It is encrypted at rest through
the same helper the identity number uses, and the admin follows the same rule
``design/backend.md`` section 10 sets there: staff may set it and cannot read it
back. Putting it on a page puts it in the browser cache, the proxy logs and
anyone's shoulder view, for no operational gain -- the payout run reads it, and
a person confirming which account is on file has the account name and the bank.
"""
from django import forms
from django.contrib import admin

from .models import Producer, ProducerMembership, ProducerStorefront


class ProducerAdminForm(forms.ModelForm):
    """Adds a write-only field for the encrypted account number.

    ``bank_account_number`` is a property rather than a column, so a
    ``ModelForm`` cannot reach it. This declares it explicitly, leaves it blank
    on every render, and writes it only when something was typed -- so saving
    the form without touching the field keeps whatever is on file rather than
    erasing it. The same shape as the identity-number field on the member admin.
    """

    bank_account_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'autocomplete': 'off'}),
        help_text=(
            'Write-only. Leave blank to keep the number already on file. It is '
            'encrypted at rest and is never shown back.'
        ),
    )

    class Meta:
        model = Producer
        fields = '__all__'

    def save(self, commit=True):
        producer = super().save(commit=False)
        typed = (self.cleaned_data.get('bank_account_number') or '').strip()
        if typed:
            producer.bank_account_number = typed
        if commit:
            producer.save()
            self.save_m2m()
        return producer


class ProducerStorefrontInline(admin.TabularInline):
    model = ProducerStorefront
    extra = 0
    verbose_name = 'storefront'
    verbose_name_plural = 'Sells into'


class ProducerMembershipInline(admin.TabularInline):
    model = ProducerMembership
    extra = 0
    autocomplete_fields = ('user',)
    readonly_fields = ('appointed_at',)
    verbose_name = 'appointment'
    verbose_name_plural = 'Appointed people'
    fields = ('user', 'role', 'appointed_at')


@admin.register(Producer)
class ProducerAdmin(admin.ModelAdmin):
    form = ProducerAdminForm
    inlines = (ProducerMembershipInline, ProducerStorefrontInline)
    list_display = ('trading_name', 'primary_name', 'is_published', 'has_image', 'updated_at')
    list_filter = ('is_published', 'storefronts__storefront')
    search_fields = ('trading_name', 'public_description')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (
            None,
            {
                'fields': ('trading_name', 'is_published'),
                'description': (
                    'The trading name is what members see. Members see this '
                    'producer only once it is published.'
                ),
            },
        ),
        ('Public profile', {'fields': ('public_description', 'image')}),
        (
            'Collection and settlement',
            {
                'classes': ('collapse',),
                'fields': (
                    'collection_address',
                    'bank_account_name',
                    'bank_name',
                    'bank_branch_code',
                    'bank_account_number',
                ),
                'description': (
                    'Members never see any of this. How a producer is actually '
                    'settled is undecided — C10 — so these are the fields the '
                    'brief names and no more. The account number is write-only.'
                ),
            },
        ),
        ('Record', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        # `primary_name` walks the appointments on every row, so they are
        # prefetched rather than fetched per producer.
        return super().get_queryset(request).prefetch_related('appointments__user')

    @admin.display(description='Primary')
    def primary_name(self, obj):
        """Who owns this producer, or a dash.

        None is a legitimate state — a producer created before anybody is
        appointed to it — so this renders a dash rather than raising. It is on
        the list because a producer with no primary is exactly what staff are
        looking for when nobody can appoint anyone.
        """
        appointment = obj.primary
        return appointment.user.display_name if appointment is not None else '—'

    @admin.display(boolean=True, description='Image')
    def has_image(self, obj):
        """Whether a photograph has been uploaded.

        On the list because a published producer with no image is the thing
        staff are looking for when a cultivator's card renders blank, and it is
        not visible from anything else here.
        """
        return bool(obj.image)

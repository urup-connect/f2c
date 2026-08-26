"""The admin over stock: plants, batches, and the ownership history.

The sidebar group is **Stock**, because that is what a cultivator calls the
plants they are holding — `member-roles.md` says "manage plant stocks". The app
and the model are singular and serialised, because a cultivator's stock is a set
of individual plants rather than a quantity of anything; `design/backend.md`
section 3 records why there is no stock model.

This admin is the operator's tool and not the cultivator's screen. Block 3's
capture work — individual entry and the Excel batch upload — is a cultivator
feature behind an endpoint that does not exist yet, so what staff get here is the
ability to answer questions and to make the two corrections the brief names as
administrative: disable a plant, and disable a batch.

Three things are deliberately not editable, and each would break something
quiet if it were:

**The serial.** Allocated from a counter, printed on a certificate of ownership,
and the thing a member's plant is traced by. A typed serial is a certificate that
no longer matches a record.

**The owner.** `Plant.transfer_to` writes it *and* the ownership history in one
transaction. A form field would move a plant without recording the tenure it
ended, and the history is what a certificate is evidence from. The action below
is the route, and it says so.

**The leaf rating.** Derived from the grow price. Unlike most derived columns in
this project it has no check constraint behind it (the model says why), so the
admin not offering it is load-bearing rather than tidy.

**The ownership history is read-only throughout**, including for superusers.
It is the same argument `documents` makes about a consent row: evidence somebody
can retype is not evidence.
"""
from django.contrib import admin, messages
from django.utils import timezone

from .models import Batch, Plant, PlantOwnership, PlantStatus, SerialCounter


class PlantOwnershipInline(admin.TabularInline):
    """Who has held this plant, newest first. Read-only.

    On the plant's own page because "who owns this and how did they get it" is
    the question this admin is opened with — a support query about a certificate,
    or a trace after a swap.
    """

    model = PlantOwnership
    extra = 0
    can_delete = False
    fields = ('owner_name', 'reason', 'acquired_at', 'released_at')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Owner')
    def owner_name(self, obj):
        return obj.owner.display_name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('owner')


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    list_display = (
        'serial',
        'cultivator_plant_id',
        'strain_name',
        'cultivator_name',
        'status',
        'grow_price',
        'leaf_rating',
        'holder',
        'estimated_harvest_date',
        'availability',
    )
    list_filter = (
        'status',
        'listing__strain',
        ('batch', admin.RelatedOnlyFieldListFilter),
        ('owner', admin.EmptyFieldListFilter),
        ('disabled_at', admin.EmptyFieldListFilter),
    )
    # `plant-id-numbers.md` gives the administrator "trace serials and batches",
    # and this is that. Both identifiers, because a member quotes the platform
    # serial off a certificate and a cultivator quotes their own off a pot.
    search_fields = ('serial', 'cultivator_plant_id', 'batch__reference')
    date_hierarchy = 'estimated_harvest_date'
    autocomplete_fields = ('listing',)
    inlines = (PlantOwnershipInline,)
    actions = ('disable_plants',)
    readonly_fields = (
        'id', 'serial', 'leaf_rating', 'harvested_on', 'owner_name',
        'cultivator_pseudonym', 'offered_product_types', 'created_at',
        'updated_at',
    )
    fieldsets = (
        (
            None,
            {
                'fields': ('serial', 'cultivator_plant_id', 'listing', 'batch'),
                'description': (
                    'The listing determines the strain and the finished product '
                    'types the owner may choose from at harvest. The serial is '
                    'allocated by the platform and appears on the certificate '
                    'of ownership.'
                ),
            },
        ),
        (
            'Commercial terms',
            {
                'fields': ('grow_price', 'leaf_rating', 'minimum_yield_grams'),
                'description': (
                    'The leaf rating is the grow price ÷ 1000 to the nearest '
                    '0.5, recalculated on every save. It is swap value, not a '
                    'reputation score, and the swap zone shows it instead of a '
                    'Rand figure.'
                ),
            },
        ),
        (
            'The grow',
            {
                'fields': (
                    'planting_date', 'estimated_bloom_date',
                    'estimated_harvest_date', 'status', 'harvested_on',
                ),
                'description': (
                    'The actual harvest date is set by harvesting the plant, '
                    'not by typing it — the estimate is kept because it is what '
                    'the member bought against.'
                ),
            },
        ),
        (
            'Ownership',
            {
                'fields': ('owner_name', 'cultivator_pseudonym',
                           'offered_product_types', 'disabled_at'),
                'description': (
                    'A blank owner means the cultivator still holds it. '
                    'Ownership is changed by <code>Plant.transfer_to</code>, '
                    'which records the tenure it ends in the same transaction; '
                    'there is deliberately no field for it here.'
                ),
            },
        ),
        ('Record', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('listing__strain', 'listing__cultivator', 'owner', 'batch')
        )

    @admin.display(description='Strain', ordering='listing__strain__name')
    def strain_name(self, obj):
        return obj.listing.strain.name

    @admin.display(description='Cultivator', ordering='listing__cultivator__nickname')
    def cultivator_name(self, obj):
        # `display_name`, never a legal name or an email address. Section 6.6 of
        # `roles-and-permissions.md`.
        return obj.listing.cultivator.display_name

    @admin.display(description='Held by', ordering='owner__nickname')
    def holder(self, obj):
        """The member holding it, or the cultivator.

        Rendered rather than left blank, because an empty column reads as
        missing data where what it means is "still for sale".
        """
        if obj.owner_id is None:
            return '— cultivator —'
        return obj.owner.display_name

    @admin.display(description='Owner')
    def owner_name(self, obj):
        return self.holder(obj)

    @admin.display(description='Available', boolean=True)
    def availability(self, obj):
        return obj.is_available

    @admin.display(description='Product types at harvest')
    def offered_product_types(self, obj):
        """Inherited from the listing. C18, and read-only because of it.

        A blank here is a plant whose owner will have nothing to choose at
        harvest, which is worth being able to see from the record.
        """
        names = [product.name for product in obj.finished_product_types]
        return ', '.join(names) if names else '— none on the listing —'

    @admin.action(description='Withdraw selected plants from sale')
    def disable_plants(self, request, queryset):
        """`platform.disable_plant`, as a batch action.

        Refuses any plant a member holds. Withdrawing stock is taking it off
        sale; taking a plant off somebody who paid for it is a different act with
        a refund attached, and C9 has not decided what that is.
        """
        held = queryset.filter(owner__isnull=False)
        if held.exists():
            self.message_user(
                request,
                f'{held.count()} of the selected plants are held by a member '
                'and were not withdrawn. Withdrawing stock takes it off sale; '
                'removing a plant somebody has paid for is a refund, which this '
                'action does not do.',
                level=messages.WARNING,
            )

        withdrawn = queryset.filter(
            owner__isnull=True, disabled_at__isnull=True
        ).update(disabled_at=timezone.now())
        self.message_user(
            request, f'{withdrawn} plant(s) withdrawn from sale.'
        )


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('reference', 'cultivator_name', 'plant_count', 'disabled_at')
    list_filter = (('disabled_at', admin.EmptyFieldListFilter),)
    search_fields = ('reference', 'cultivator__nickname')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (
            None,
            {
                'fields': ('cultivator', 'reference', 'notes', 'disabled_at'),
                'description': (
                    'Disabling a batch does not withdraw its plants. A '
                    'mis-numbered crop should not void stock a member has '
                    'bought.'
                ),
            },
        ),
        ('Record', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('cultivator')

    @admin.display(description='Cultivator', ordering='cultivator__nickname')
    def cultivator_name(self, obj):
        return obj.cultivator.display_name

    @admin.display(description='Plants')
    def plant_count(self, obj):
        return obj.plants.count()


@admin.register(PlantOwnership)
class PlantOwnershipAdmin(admin.ModelAdmin):
    """The tenure ledger. Read-only throughout, superusers included.

    Searchable by serial and by member, because tracing a plant through its
    owners is what an administrator is given `platform.trace_serials` for. Not
    editable, because it is evidence.
    """

    list_display = ('plant_serial', 'owner_name', 'reason', 'acquired_at', 'released_at')
    list_filter = ('reason', ('released_at', admin.EmptyFieldListFilter))
    search_fields = ('plant__serial', 'owner__nickname')
    date_hierarchy = 'acquired_at'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('plant', 'owner')

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Plant', ordering='plant__serial')
    def plant_serial(self, obj):
        return obj.plant.serial

    @admin.display(description='Owner', ordering='owner__nickname')
    def owner_name(self, obj):
        return obj.owner.display_name


@admin.register(SerialCounter)
class SerialCounterAdmin(admin.ModelAdmin):
    """The serial sequence. Visible, and not editable by anyone.

    It is here so that "what is the next serial" can be answered without a
    shell, and read-only because winding it back reissues numbers that are
    already on certificates in members' hands. Correcting it is a deliberate
    act at the database, not a form somebody can submit.
    """

    list_display = ('name', 'next_value')

    def get_readonly_fields(self, request, obj=None):
        return ('name', 'next_value')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

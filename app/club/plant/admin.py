"""The admin over stock: plants, batches, and the ownership history.

The sidebar group is **Stock**, because that is what a cultivator calls the
plants they are holding — `member-roles.md` says "manage plant stocks". The app
and the model are singular and serialised, because a cultivator's stock is a set
of individual plants rather than a quantity of anything; `design/backend.md`
section 3 records why there is no stock model.

This admin is the operator's tool and not the cultivator's screen. Until Block 9
gives cultivators an endpoint, it is also the only place a plant can be entered by
hand — through `PlantCaptureForm`, which validates through the *same* functions
the Excel upload uses rather than restating any of their rules. For more than a
handful of plants the template is the route: `manage.py plant_template` then
`manage.py upload_plants`.

Beyond that, what staff get here is the ability to answer questions and to make
the two corrections the brief names as administrative: disable a plant, and
disable a batch.

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
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone

from app.club.strains.models import CultivatorStrainListing, ListingStatus

from .models import (
    Batch,
    Plant,
    PlantOwnership,
    PlantStatus,
    SerialCounter,
    allocate_serials,
)
from .services import build_stock_export, prepare_rows
from .spreadsheet import read_row

#: `RowError.key` uses the template's field names. Two of them are not fields on
#: this form: a row names a strain where the form picks the listing that strain
#: belongs to, and the product types are inherited rather than entered.
ERROR_FIELD = {'strain': 'listing', 'finished_product_types': None}


class PlantCaptureForm(forms.ModelForm):
    """Adding one plant, validated by the same code the Excel upload uses.

    ``cultivator-stock-upload.md`` asks for individual capture beside the batch
    upload, and gives one list of requirements for both. This form is the staff
    route to the first of those until Block 9 gives cultivators their own screen.

    **The validation is not reimplemented here.** ``clean`` assembles a row in the
    shape the template reader produces and hands it to ``read_row`` and
    ``prepare_rows`` -- the same two functions an upload goes through -- then maps
    each complaint back onto the field it came from. So the date rules, the
    plant-ID duplicate check and the listing check are the upload's, exactly, and
    there is no second set to drift.

    That matters most for the dates. ``Plant`` carries check constraints for
    bloom-after-planting and harvest-after-planting, and a constraint violation
    reaches the admin as an ``IntegrityError`` -- a 500 page, not a field error.
    Validating here is what turns those into something a person can act on, and
    it also catches harvest-before-bloom, which no constraint expresses.
    """

    class Meta:
        model = Plant
        fields = (
            'listing', 'cultivator_plant_id', 'batch', 'grow_price',
            'minimum_yield_grams', 'planting_date', 'estimated_bloom_date',
            'estimated_harvest_date',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only listings a member can actually buy against. Loading stock into a
        # draft listing puts plants behind a wall, and `prepare_rows` would
        # refuse it anyway -- this stops it being offered in the first place.
        self.fields['listing'].queryset = (
            CultivatorStrainListing.objects
            .filter(status=ListingStatus.LISTED)
            .select_related('strain', 'cultivator')
            .order_by('cultivator__trading_name', 'strain__name')
        )

    def clean(self):
        cleaned = super().clean()
        listing = cleaned.get('listing')
        if listing is None:
            # Every check below is scoped to a cultivator, and without a listing
            # there is no cultivator to scope to. The field already carries its
            # own "this is required".
            return cleaned

        raw = {
            'cultivator_plant_id': cleaned.get('cultivator_plant_id'),
            'strain': listing.strain.name,
            'grow_price': cleaned.get('grow_price'),
            'minimum_yield_grams': cleaned.get('minimum_yield_grams'),
            'planting_date': cleaned.get('planting_date'),
            'estimated_bloom_date': cleaned.get('estimated_bloom_date'),
            'estimated_harvest_date': cleaned.get('estimated_harvest_date'),
            # Inherited from the listing, so there is nothing to confirm.
            'finished_product_types': None,
            # The form picks a Batch row; `_batches_for` resolves a reference
            # string. Left blank so the two do not both try.
            'batch': None,
        }

        row, errors = read_row(raw)
        if row is not None:
            _, prepare_errors = prepare_rows(listing.cultivator, [row])
            errors = list(errors) + list(prepare_errors)

        for error in errors:
            field = ERROR_FIELD.get(error.key, error.key)
            self.add_error(field, error.message)

        return cleaned


class PlantOwnershipInline(admin.TabularInline):
    """Who has held this plant, newest first. Read-only.

    On the plant's own page because "who owns this and how did they get it" is
    the question this admin is opened with — a support query about a certificate,
    or a trace after a swap.
    """

    model = PlantOwnership
    extra = 0
    can_delete = False
    fields = ('holder_name', 'reason', 'acquired_at', 'released_at')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='Held by')
    def holder_name(self, obj):
        """A member's nickname or the farm's trading name.

        Reads the model's property rather than `obj.owner.display_name`, which
        is what it did before C13 and what would now raise on the farm's own
        cultivation tenure -- the first row of every plant's history.
        """
        return obj.holder_name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('owner', 'producer')


@admin.register(Plant)
class PlantAdmin(admin.ModelAdmin):
    # The add form is a different form from the change form, and has to be: on
    # add there is no serial yet and the listing is a choice, while on change the
    # serial is history and the listing is what the plant was sold against.
    add_form = PlantCaptureForm
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
    actions = ('export_stock', 'disable_plants')
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

    def get_form(self, request, obj=None, change=False, **kwargs):
        """The capture form on add, the ordinary one on change."""
        if not change:
            kwargs['form'] = self.add_form
            # `fieldsets` below describes an existing plant, including fields the
            # capture form does not carry. Cleared so the add page renders the
            # capture form's own fields.
            kwargs.setdefault('fields', None)
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    None,
                    {
                        'fields': (
                            'listing', 'cultivator_plant_id', 'batch',
                            'grow_price', 'minimum_yield_grams',
                            'planting_date', 'estimated_bloom_date',
                            'estimated_harvest_date',
                        ),
                        'description': (
                            'For more than a handful of plants use the template '
                            'instead: <code>manage.py plant_template</code> then '
                            '<code>manage.py upload_plants</code>. The serial, '
                            'the leaf rating and the status are allocated by the '
                            'platform and are not asked for here.'
                        ),
                    },
                ),
            )
        return super().get_fieldsets(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # None of the read-only fields exist on the add form -- a serial that has
        # not been allocated and an owner that cannot yet exist have nothing to
        # display -- and listing them would make the add page fail to render.
        if obj is None:
            return ()
        return super().get_readonly_fields(request, obj)

    def save_model(self, request, obj, form, change):
        """Allocate the serial on the way in.

        This is what makes adding through the admin safe at all. ``serial`` is
        ``editable=False``, so it is on no form and was left empty -- and because
        the column is unique but not null, the *first* plant added by hand would
        have saved with a blank serial and the second would have failed on the
        index. A plant with no serial has nothing to put on a certificate of
        ownership and nothing for an administrator to trace.

        The upload allocates a contiguous block for a whole file; one plant takes
        one. Both go through ``allocate_serials``, so both draw on the same
        counter and neither can reissue a number.
        """
        if not change and not obj.serial:
            obj.serial = allocate_serials(1)[0]
        super().save_model(request, obj, form, change)

    @admin.display(description='Strain', ordering='listing__strain__name')
    def strain_name(self, obj):
        return obj.listing.strain.name

    @admin.display(description='Cultivator', ordering='listing__cultivator__trading_name')
    def cultivator_name(self, obj):
        # `display_name`, never a legal name or an email address. Section 6.6 of
        # `roles-and-permissions.md`.
        return obj.listing.cultivator.pseudonym

    @admin.display(
        description='Held by', ordering='owner__club_membership__nickname'
    )
    def holder(self, obj):
        """The member holding it, or the farm.

        Rendered rather than left blank, because an empty column reads as
        missing data where what it means is "still for sale". Since C13 the farm
        is a named holder rather than a dash: it holds an open cultivation
        tenure, so there is a trading name to print.
        """
        if obj.owner_id is None:
            return f'{obj.listing.cultivator.pseudonym} — for sale'
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

    @admin.action(description='Export selected plants to a spreadsheet')
    def export_stock(self, request, queryset):
        """The changelist's own filters, as a file.

        The command exports one cultivator at one scope; this exports whatever
        staff have on screen, which is the case the command cannot cover -- one
        batch, one strain, everything overdue, one member's holdings. Same
        writer, so the columns cannot differ between the two.

        The owner column appears only if some selected plant has an owner, and
        carries a nickname and nothing else. `services.stock_rows` is where that
        is argued.
        """
        plants = (
            queryset
            .select_related('listing__strain', 'listing__cultivator', 'batch', 'owner')
            .prefetch_related('listing__finished_product_types')
            .order_by('estimated_harvest_date', 'serial')
        )
        workbook = build_stock_export(plants, scope_label='Selected in the admin')

        response = HttpResponse(
            content_type=(
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        )
        response['Content-Disposition'] = 'attachment; filename="stock.xlsx"'
        workbook.save(response)
        return response

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
    search_fields = ('reference', 'cultivator__trading_name')
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

    @admin.display(description='Cultivator', ordering='cultivator__trading_name')
    def cultivator_name(self, obj):
        return obj.cultivator.pseudonym

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

    list_display = ('plant_serial', 'holder_name', 'reason', 'acquired_at', 'released_at')
    list_filter = ('reason', ('released_at', admin.EmptyFieldListFilter))
    # The nickname moved to `membership.ClubMembership` with the storefront
    # split (C27), so `owner__nickname` had stopped resolving; the producer's
    # trading name joins it because a farm is a holder here since C13.
    search_fields = (
        'plant__serial',
        'owner__club_membership__nickname',
        'producer__trading_name',
    )
    date_hierarchy = 'acquired_at'

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('plant', 'owner', 'producer')
        )

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

    @admin.display(description='Held by', ordering='owner__club_membership__nickname')
    def holder_name(self, obj):
        """The member, or the farm on a cultivation tenure. See the inline."""
        return obj.holder_name


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

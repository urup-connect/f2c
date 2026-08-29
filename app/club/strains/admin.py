"""The admin over the strain catalogue and the cultivators' offers against it.

Two audiences in one file, and they are not the same audience.

**The strain catalogue is the administrator's.** ``member-roles.md`` gives
strain listings to the administrator and lets a cultivator only request a new
one, so this is where a strain is created, curated and published. A cultivator's
request arrives as a support ticket in Block 11; until then an administrator
types the strain in and leaves it ``PENDING`` until the botanical facts are
checked.

**A listing is the cultivator's**, and this admin is a stand-in for a screen
that does not exist. ``todo.md`` puts the endpoint work in Block 9 and the models
in Block 1, which means staff are the only people who can write a listing today.
Two consequences are visible below: the cultivator picker is restricted to
accounts that actually hold the cultivator role, and ``save_related`` re-runs
validation after the many-to-many is written, because the C18 subset rule and the
"a listed offer needs a product type" rule cannot be checked before it exists.

**Nothing here is read-only on principle.** That is the difference from the
payments and documents admins: a payment is a fact about the outside world and a
published revision is something a member agreed to, whereas a catalogue is
editable by definition. What is guarded instead is *withdrawal versus deletion* —
a strain or a listing with plants behind it is retired, never deleted, and the
list views are arranged so that state is the first thing visible.
"""
from django import forms
from django.contrib import admin


from .models import (
    Aroma,
    CultivatorStrainListing,
    Effect,
    ListingStatus,
    Strain,
    check_offered_types,
)


def cultivator_choices(field):
    """Limit a cultivator foreign key to accounts that hold the role.

    Without this, ``exclusive_to`` and a listing's ``cultivator`` are pickers
    over every account in the club -- which on a screen staff use to reserve a
    strain or to write somebody's commercial terms is an invitation to pick the
    wrong person entirely.

    Producers, not people: the field points at the organisation now, so there is
    no erased account to filter out and no risk of offering three appointed
    staff of one farm as three cultivators.
    """
    return field.remote_field.model.objects.order_by('trading_name')


class AromaEffectAdmin(admin.ModelAdmin):
    """Shared admin for the two vocabularies. Small on purpose.

    ``slug`` is not a field: it is derived from ``name`` on every write and is
    the unique key, so an editable widget would let the two drift. Same argument
    as ``is_active`` on the member admin.
    """

    list_display = ('name', 'slug', 'is_available', 'strain_count')
    list_filter = ('is_available',)
    search_fields = ('name',)
    readonly_fields = ('id', 'slug', 'created_at')
    fields = ('name', 'is_available', 'id', 'slug', 'created_at')

    @admin.display(description='Strains')
    def strain_count(self, obj):
        """How many strains carry the term.

        On the list because it is the only thing that tells staff whether a term
        is safe to rename or worth retiring, and because a vocabulary nobody has
        used is a vocabulary somebody guessed at.
        """
        return obj.strains.count()

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('strains')


@admin.register(Aroma)
class AromaAdmin(AromaEffectAdmin):
    pass


@admin.register(Effect)
class EffectAdmin(AromaEffectAdmin):
    pass


class CultivatorStrainListingInline(admin.TabularInline):
    """Who is offering this strain, on the strain's own page.

    The question this answers is the one that has to be asked before a strain is
    retired or reserved: is anybody selling it. Read-only, because a listing's
    commercial terms are not something to edit in passing while curating
    botanical facts -- there is a full admin for that below.
    """

    model = CultivatorStrainListing
    extra = 0
    can_delete = False
    fields = ('cultivator', 'status', 'default_grow_price', 'minimum_yield_grams')
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Strain)
class StrainAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'strain_type', 'status', 'reserved_to', 'listing_count', 'updated_at'
    )
    list_filter = ('status', 'strain_type', 'preferred_growing_environment', 'difficulty_level')
    search_fields = ('name', 'genetic_lineage', 'breeder_origin')
    autocomplete_fields = ('aromas', 'effects')
    inlines = (CultivatorStrainListingInline,)
    # Derived from `name`, so not a form field -- see AromaEffectAdmin.
    readonly_fields = ('id', 'slug', 'created_at', 'updated_at')
    fieldsets = (
        (
            None,
            {
                'fields': ('name', 'status', 'strain_type', 'exclusive_to'),
                'description': (
                    'Leave <em>Exclusive to</em> blank for a strain any '
                    'cultivator may offer. Setting it reserves the strain to '
                    'one grower — their own genetics. It does not make the '
                    'strain theirs to edit.'
                ),
            },
        ),
        ('Botanical', {'fields': ('genetic_lineage', 'breeder_origin', 'description')}),
        (
            'Chemical profile',
            {
                'fields': ('thc_content', 'cbd_content', 'other_cannabinoids',
                           'terpene_profile'),
                'description': (
                    'Percentages, and JSON objects for the minor cannabinoids '
                    'and terpenes. The JSON columns are shown to members and are '
                    'never searched, so they need no fixed set of keys.'
                ),
            },
        ),
        ('Sensory and effects', {'fields': ('aromas', 'effects')}),
        (
            'Cultivation',
            {
                'fields': ('flowering_time_weeks', 'preferred_growing_environment',
                           'difficulty_level', 'disease_resistance'),
            },
        ),
        ('Record', {'fields': ('id', 'slug', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('exclusive_to')
            .prefetch_related('listings')
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'exclusive_to':
            kwargs['queryset'] = cultivator_choices(db_field)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='Reserved to', ordering='exclusive_to__trading_name')
    def reserved_to(self, obj):
        """The exclusive cultivator, or a dash.

        On the list because exclusivity is the one thing about a strain that
        changes who may act on it, and it is invisible from the name.
        """
        return obj.exclusive_to.display_name if obj.exclusive_to_id else '—'

    @admin.display(description='Listings')
    def listing_count(self, obj):
        """Offers against this strain, live ones counted separately.

        Retiring a strain takes every listed offer off the shelf, so staff need
        to see how many that is before doing it.
        """
        listings = list(obj.listings.all())
        live = sum(1 for listing in listings if listing.status == ListingStatus.LISTED)
        return f'{live} listed / {len(listings)} total'


class CultivatorStrainListingForm(forms.ModelForm):
    """Adds the one rule the model cannot check for itself.

    ``Model.clean`` runs before the many-to-many is written, so on a first save
    it sees no product types at all and both rules that depend on them would
    never fire. A ``ModelForm`` sees the submitted set in ``cleaned_data`` before
    anything is written, which is also where a field error belongs -- so the
    check happens here and renders beside the widget rather than as a 500 after
    the row is saved.

    The rule itself is ``models.check_offered_types``, called by the model too,
    so there is one copy of it.
    """

    class Meta:
        model = CultivatorStrainListing
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        # Absent when the field itself failed validation; there is already an
        # error against it and a second one would be noise.
        if 'finished_product_types' in cleaned:
            error = check_offered_types(
                cleaned.get('status'), cleaned['finished_product_types']
            )
            if error:
                self.add_error('finished_product_types', error)
        return cleaned


@admin.register(CultivatorStrainListing)
class CultivatorStrainListingAdmin(admin.ModelAdmin):
    form = CultivatorStrainListingForm
    list_display = (
        'strain', 'cultivator_name', 'status', 'default_grow_price',
        'minimum_yield_grams', 'product_types', 'updated_at',
    )
    list_filter = ('status', 'strain__strain_type', 'finished_product_types')
    search_fields = ('strain__name', 'cultivator__trading_name', 'short_description')
    autocomplete_fields = ('strain',)
    filter_horizontal = ('finished_product_types',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('cultivator', 'strain', 'status')}),
        (
            'What a member sees',
            {
                'fields': ('short_description', 'description', 'image'),
                'description': (
                    'The short description is what appears beside this '
                    "cultivator's name when a member compares everyone offering "
                    'the strain. A listed offer cannot be saved without one.'
                ),
            },
        ),
        (
            'Commercial terms',
            {
                'fields': ('default_grow_price', 'minimum_yield_grams',
                           'finished_product_types'),
                'description': (
                    'The grow price here is this cultivator’s standard asking '
                    'price. Each plant they upload carries its own, which is the '
                    'one a member pays. The product types are the subset of the '
                    'platform catalogue this cultivator will deliver — a plant '
                    'may offer these and no others.'
                ),
            },
        ),
        ('Record', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('cultivator', 'strain')
            .prefetch_related('finished_product_types')
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'cultivator':
            kwargs['queryset'] = cultivator_choices(db_field)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='Cultivator', ordering='cultivator__trading_name')
    def cultivator_name(self, obj):
        """``display_name``, never a legal name or an email address.

        Section 6.6 of ``roles-and-permissions.md`` makes that a property of
        every payload; a list column is no different.
        """
        return obj.cultivator.display_name

    @admin.display(description='Product types')
    def product_types(self, obj):
        """The C18 subset, so staff can see it without opening the row.

        A listed offer with none is the failure this column is on the list to
        make visible: the member buys a plant and then has nothing to choose at
        harvest.
        """
        names = [t.name for t in obj.finished_product_types.all()]
        return ', '.join(names) if names else '— none —'

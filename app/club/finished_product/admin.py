"""The admin over the finished product type catalogue.

Fully editable, unlike the payments admin beside it, and for the opposite
reason: this *is* where a product type comes from. ``todo.md`` Block 1 asks for
administrator screens for product type CRUD and puts the endpoint work in Block
9, so until then this is the only interface there is.

Two restrictions, both about not losing history.

**Deleting a type is possible but should not be.** A harvest record points at
the type its owner chose, and once Block 6 exists a delete will be refused by the
``PROTECT`` on that foreign key. Until then there is nothing to refuse it, so the
list shows availability prominently and the help text says what to do instead:
clear ``is_available``.

**Repricing is not retroactive.** ``price`` is the current price, and what a
member was charged belongs on the harvest transaction. The list shows whether a
type currently costs anything, because "did the member owe us something for
this choice?" is the question this screen is opened with.
"""
from django.contrib import admin

from .models import FinishedProductType


@admin.register(FinishedProductType)
class FinishedProductTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'price', 'chargeable', 'is_available', 'display_order')
    list_filter = ('is_available',)
    search_fields = ('name', 'code')
    ordering = ('display_order', 'name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (None, {'fields': ('name', 'code', 'description')}),
        (
            'Availability and cost',
            {
                'fields': ('price', 'is_available', 'display_order'),
                'description': (
                    'A price of zero means the choice is free to the member, '
                    'which is the case for pre-rolls and loose cannabis. To stop '
                    'offering a type, clear <em>Is available</em> — never delete '
                    'it, because harvested plants record the type their owner '
                    'chose.'
                ),
            },
        ),
        ('Record', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    @admin.display(boolean=True, description='Costs the member')
    def chargeable(self, obj):
        """``requires_payment``, rendered as a tick.

        A separate column from ``price`` because the harvest flow branches on
        this and a reader should be able to see the branch rather than infer it
        from a decimal.
        """
        return obj.requires_payment

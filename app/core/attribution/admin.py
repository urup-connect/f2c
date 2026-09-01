"""Reading the campaigns, and never editing them.

A touch is a record of what a link said when somebody followed it. Editing one
would be rewriting history to make a report say something else, so the form is
read-only in both directions -- no add, no change -- and what the page is for is
the filters: source, medium, network, storefront, and a date hierarchy over the
conversion.

**Deleting is allowed**, unlike editing, and for one reason: a POPIA deletion
request is answered by hand as often as by the purge. ``Attributed`` points at
this table with ``SET_NULL``, so removing a row leaves the member and loses the
label, which is the right direction for a deletion to run in.

Whose touch it is, is deliberately not a column here. The link runs the other way
-- from ``ClubMembership`` -- and mirroring it would mean this page joining every
model that ever inherits ``Attributed``. "Which members came from this campaign"
is a filter on the members list, where the answer belongs.
"""
from django.contrib import admin

from .models import CampaignTouch


@admin.register(CampaignTouch)
class CampaignTouchAdmin(admin.ModelAdmin):
    list_display = (
        'label', 'storefront', 'click_network', 'referrer', 'landing_path',
        'seen_at', 'recorded_at',
    )
    # `source` and `medium` first: "what is working" is what this list is opened
    # for, and both are folded to lower case on the way in, so the filter shows
    # one entry per channel rather than one per way of typing it.
    list_filter = ('source', 'medium', 'storefront', 'click_network')
    search_fields = ('source', 'medium', 'campaign', 'term', 'content', 'referrer')
    ordering = ('-recorded_at',)
    date_hierarchy = 'recorded_at'

    readonly_fields = (
        'id', 'storefront', 'source', 'medium', 'campaign', 'term', 'content',
        'click_network', 'click_id', 'referrer', 'landing_path', 'seen_at',
        'recorded_at',
    )

    fieldsets = (
        (None, {'fields': ('id', 'storefront')}),
        ('The campaign', {
            'fields': ('source', 'medium', 'campaign', 'term', 'content'),
            'description': (
                'The five standard utm_ parameters, exactly as the link '
                'carried them, lower-cased so that one channel is one row in '
                'every report.'
            ),
        }),
        ('The click', {
            'fields': ('click_network', 'click_id'),
            'description': (
                'What reconciles a signup against ad spend. The id is the ad '
                'network’s own, from gclid, fbclid, msclkid or ttclid.'
            ),
        }),
        ('The arrival', {
            'fields': ('referrer', 'landing_path', 'seen_at', 'recorded_at'),
            'description': (
                'Referring site and landing page are stored without their '
                'query strings. “Seen” is when the visit happened as the '
                'browser reported it, and is empty where that could not be '
                'trusted; “recorded” is when the visitor converted.'
            ),
        }),
    )

    @admin.display(description='Campaign', ordering='source')
    def label(self, obj):
        """``source / medium / campaign``, from the model rather than restated.

        A method so the column can be ordered, and ordered on ``source``, which
        is the dimension anybody scanning this list is grouping by.
        """
        return obj.label

    def has_add_permission(self, request):
        # There is no such thing as a campaign touch somebody types in. It is
        # written by `services.record_touches` at a conversion or it does not
        # exist.
        return False

    def has_change_permission(self, request, obj=None):
        return False

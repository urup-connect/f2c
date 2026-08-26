"""The admin over cultivator profiles.

Editable, like the catalogue admins and unlike the payments one: a profile is
copy a grower writes about themselves, and until Block 9 gives them a screen,
staff are the only people who can write it.

Publication is a field rather than an action, which is the one place this
departs from the documents admin. There, publishing a revision is irreversible
and so had to be an explicit action rather than a side effect of a save.
Publishing a profile is neither irreversible nor consequential -- clearing the
tick takes it down again, and nothing agreed to it -- so a checkbox is honest.

There is no ``pseudonym`` field to edit here. A cultivator's public name is
their nickname on the member admin, which is the only name namespace the club
has; ``models`` sets out why.
"""
from django.contrib import admin

from .models import CultivatorProfile


@admin.register(CultivatorProfile)
class CultivatorProfileAdmin(admin.ModelAdmin):
    list_display = ('pseudonym', 'is_published', 'has_image', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('cultivator__nickname', 'public_description')
    autocomplete_fields = ('cultivator',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        (
            None,
            {
                'fields': ('cultivator', 'is_published'),
                'description': (
                    'The public name shown to members is this account’s '
                    'nickname, edited on the member record. Members see this '
                    'profile only once it is published.'
                ),
            },
        ),
        ('Public profile', {'fields': ('public_description', 'image')}),
        ('Record', {'fields': ('id', 'created_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('cultivator')

    @admin.display(description='Cultivator', ordering='cultivator__nickname')
    def pseudonym(self, obj):
        return obj.pseudonym

    @admin.display(boolean=True, description='Image')
    def has_image(self, obj):
        """Whether a photograph has been uploaded.

        On the list because a published profile with no image is the thing staff
        are looking for when a cultivator's card renders blank, and it is not
        visible from anything else here.
        """
        return bool(obj.image)

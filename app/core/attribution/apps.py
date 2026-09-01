from django.apps import AppConfig


class AttributionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.attribution'
    # Explicit, like every other app here, so the table is `attribution_
    # campaigntouch` rather than carrying the package path -- see the note in
    # settings.INSTALLED_APPS.
    label = 'attribution'
    # What the admin sidebar calls this group. Not 'Attribution', which reads as
    # a legal notion; these are the campaigns that brought people here.
    verbose_name = 'Campaign tracking'

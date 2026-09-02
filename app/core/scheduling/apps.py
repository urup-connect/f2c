from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.scheduling'
    # Explicit, so the table name stays flat -- `scheduling_scheduledrun`, not
    # `core_scheduling_scheduledrun`. Every app under these packages sets it;
    # see `common.apps` for why.
    label = 'scheduling'

from django.apps import AppConfig


class CultivatorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.cultivators'
    # 'Cultivators' in the admin sidebar rather than 'Cultivator profiles':
    # Block 2 puts the farm, its appointed staff and its collection address in
    # this group, and the group name should survive that.
    verbose_name = 'Cultivators'

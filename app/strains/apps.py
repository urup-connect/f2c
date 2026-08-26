from django.apps import AppConfig


class StrainsConfig(AppConfig):
    # Stated rather than inherited. `settings.DEFAULT_AUTO_FIELD` is unset, so
    # the project-wide default is Django's own `AutoField` -- which raises
    # models.W042 on every model in the app and gives a 32-bit key. Every model
    # here declares a UUIDv7 primary key of its own, so this only governs the
    # implicit key on the two many-to-many join tables; it matches
    # `accounts.AccountsConfig` so that nothing in the project has a plain
    # `AutoField` anywhere.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.strains'
    # 'Strains' rather than 'Strains catalogue': this group also holds the
    # cultivators' listings against a strain, and the aroma and effect
    # vocabularies.
    verbose_name = 'Strains'

from django.apps import AppConfig


class PlantConfig(AppConfig):
    # See `strains.StrainsConfig` for why this is stated rather than inherited:
    # `settings.DEFAULT_AUTO_FIELD` is unset, so the project-wide default is
    # Django's own `AutoField`, which raises models.W042 and gives a 32-bit key.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.plant'
    # 'Stock' in the admin sidebar, because that is what a cultivator calls the
    # plants they are holding -- `member-roles.md` says "manage plant stocks".
    # The app is `plant` and the model will be `Plant`, singular and serialised,
    # because a cultivator's stock is a set of individual plants rather than a
    # quantity of anything. `design/backend.md` section 3 records why there is no
    # separate stock app.
    verbose_name = 'Stock'

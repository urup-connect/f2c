from django.apps import AppConfig


class FinishedProductConfig(AppConfig):
    # See `strains.StrainsConfig` for why this is stated rather than inherited.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.finished_product'
    # What this app holds is a catalogue of the forms a harvest can take, not a
    # product. The sidebar should say so.
    verbose_name = 'Finished product types'

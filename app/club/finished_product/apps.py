from django.apps import AppConfig


class FinishedProductConfig(AppConfig):
    # See `strains.StrainsConfig` for why this is stated rather than inherited.
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.club.finished_product'
    # Explicit, so the table names stay flat -- `accounts_user`, not
    # `core_accounts_user`. The apps moved under core/commerce/club in Block
    # 0.5; the label is what keeps that a package move rather than a rename
    # of every table, every migration dependency and `AUTH_USER_MODEL`.
    label = 'finished_product'
    # What this app holds is a catalogue of the forms a harvest can take, not a
    # product. The sidebar should say so.
    verbose_name = 'Finished product types'

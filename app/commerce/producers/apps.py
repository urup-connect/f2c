from django.apps import AppConfig


class CultivatorsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.commerce.producers'
    # Explicit, so the table names stay flat -- `accounts_user`, not
    # `core_accounts_user`. The apps moved under core/commerce/club in Block
    # 0.5; the label is what keeps that a package move rather than a rename
    # of every table, every migration dependency and `AUTH_USER_MODEL`.
    label = 'producers'
    # 'Producers' in the admin sidebar. It was 'Cultivators', chosen so the
    # name would survive Block 2 adding the farm and its staff -- which it did.
    # What it did not survive is the produce market: a farmer growing carrots is
    # the same record, and calling the group Cultivators would file them under
    # the club's word for it.
    verbose_name = 'Producers'

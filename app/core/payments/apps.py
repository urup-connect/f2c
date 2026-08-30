from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.payments'
    # Explicit, so the table names stay flat -- `accounts_user`, not
    # `core_accounts_user`. The apps moved under core/commerce/club in Block
    # 0.5; the label is what keeps that a package move rather than a rename
    # of every table, every migration dependency and `AUTH_USER_MODEL`.
    label = 'payments'
    verbose_name = 'Payments'

    def ready(self):
        # Registers the deploy check in `checks.py`, which warns when the
        # notification endpoint will read the proxy's address instead of
        # Payfast's. `deploy=True`, so importing this costs nothing until
        # `manage.py check --deploy` asks for it.
        from . import checks  # noqa: F401

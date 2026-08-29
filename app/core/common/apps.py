from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.core.common'
    # Explicit, so the table names stay flat -- `accounts_user`, not
    # `core_accounts_user`. The apps moved under core/commerce/club in Block
    # 0.5; the label is what keeps that a package move rather than a rename
    # of every table, every migration dependency and `AUTH_USER_MODEL`.
    label = 'common'

    def ready(self):
        # Registers the database guards in `checks.py`. They are `Tags.database`
        # checks, so importing this costs nothing until something asks for them
        # -- which `migrate` does, and which is the moment that matters. See that
        # module's docstring.
        from . import checks  # noqa: F401

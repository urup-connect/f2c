from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app.common'

    def ready(self):
        # Registers the database guards in `checks.py`. They are `Tags.database`
        # checks, so importing this costs nothing until something asks for them
        # -- which `migrate` does, and which is the moment that matters. See that
        # module's docstring.
        from . import checks  # noqa: F401
